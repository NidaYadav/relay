import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse

from app import db
from app.agents.relay import (
    HandoffError,
    answer_handoff,
    cancel_handoff,
    create_handoff,
    decide_handoff,
    handoff_summary,
    public_packet,
    send_handoff,
)


def token_of(sent):
    return urlparse(sent["url"]).path.rsplit("/", 1)[-1]


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.patches = [
            patch.object(db, "DATA_DIR", root),
            patch.object(db, "UPLOADS", root / "uploads"),
            patch.object(db, "DB_PATH", root / "relay.db"),
        ]
        for item in self.patches:
            item.start()
        db.init()
        db.execute(
            "INSERT INTO sessions(id, created_at, status, mode) VALUES ('session-a', strftime('%s','now'), 'ready', 'ai')"
        )
        db.execute(
            """
            INSERT INTO documents(session_id, role, filename, kind, pages, path)
            VALUES ('session-a', 'form', 'renewal.pdf', 'fillable PDF', 3, 'local-only-path')
            """
        )
        self.name_field = self._field(1, "witness_name", "Name of witness", "Who can confirm this?", "helper")
        self.years_field = self._field(2, "witness_years", "How long known", "How long have you known them?", "helper")
        self.other_field = self._field(
            3, "name", "Applicant name", "Your name", "person", value="Alex Rivera", origin="user", status="done"
        )

    def _field(self, ord_, key, label, plain, source, value=None, origin=None, status="open"):
        return db.execute(
            """
            INSERT INTO fields(session_id, ord, section, key, label, plain_label, source, value, origin, status)
            VALUES ('session-a', ?, 'Part', ?, ?, ?, ?, ?, ?, ?)
            """,
            (ord_, key, label, plain, source, value, origin, status),
        )

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def _sent_for_both(self):
        preview = create_handoff(
            "session-a",
            [
                {"field_id": self.name_field, "question": "What is the witness's name?"},
                {"field_id": self.years_field, "question": "How long have you known the applicant?"},
            ],
        )
        return preview, token_of(send_handoff("session-a", preview["id"]))

    def test_one_request_carries_two_questions_and_each_gets_its_own_answer(self):
        preview, token = self._sent_for_both()
        self.assertEqual(len(preview["items"]), 2)
        self.assertFalse(preview["leak_detected"])
        self.assertEqual(preview["stays_with_you"]["other_questions"], 1)

        packet = public_packet(token)
        self.assertEqual(
            packet,
            {
                "questions": [
                    {"number": 1, "question": "What is the witness's name?"},
                    {"number": 2, "question": "How long have you known the applicant?"},
                ],
                "crop": None,
            },
        )
        text = json.dumps(packet)
        for hidden in ("Alex Rivera", "local-only-path", "session-a", "field_id"):
            self.assertNotIn(hidden, text)

        answer_handoff(token, {1: "Manan", 2: "Two years"})
        with self.assertRaisesRegex(HandoffError, "no longer works") as raised:
            answer_handoff(token, {1: "A second answer"})
        self.assertEqual(raised.exception.status_code, 410)

        summary = handoff_summary(db.row("SELECT * FROM handoffs WHERE id = ?", (preview["id"],)))
        self.assertEqual([item["answer"] for item in summary["items"]], ["Manan", "Two years"])

        result = decide_handoff("session-a", preview["id"], approve=True)
        self.assertEqual(result, {"status": "approved", "applied": 2})
        rows = {
            row["key"]: row
            for row in db.rows("SELECT key, value, origin, status FROM fields WHERE session_id = 'session-a'")
        }
        self.assertEqual(
            (rows["witness_name"]["value"], rows["witness_name"]["origin"], rows["witness_name"]["status"]),
            ("Manan", "helper", "done"),
        )
        self.assertEqual(rows["witness_years"]["value"], "Two years")
        self.assertEqual(rows["name"]["value"], "Alex Rivera")

    def test_a_partial_answer_only_fills_the_questions_that_were_answered(self):
        preview, token = self._sent_for_both()
        answer_handoff(token, {2: "Two years", 1: "   "})
        self.assertEqual(decide_handoff("session-a", preview["id"], approve=True)["applied"], 1)
        rows = {row["key"]: row for row in db.rows("SELECT key, value, status FROM fields WHERE session_id = 'session-a'")}
        self.assertEqual(rows["witness_years"]["status"], "done")
        self.assertEqual(rows["witness_name"]["status"], "open")
        self.assertIsNone(rows["witness_name"]["value"])

    def test_rejecting_changes_nothing_and_answers_must_exist(self):
        preview, token = self._sent_for_both()
        with self.assertRaisesRegex(HandoffError, "at least one"):
            answer_handoff(token, {1: "  "})
        with self.assertRaisesRegex(HandoffError, "not part of this request"):
            answer_handoff(token, {3: "Nope"})
        answer_handoff(token, {1: "Manan", 2: "Two years"})
        self.assertEqual(decide_handoff("session-a", preview["id"], approve=False), {"status": "rejected", "applied": 0})
        self.assertIsNone(db.row("SELECT value FROM fields WHERE id = ?", (self.name_field,))["value"])

    def test_question_leak_is_blocked_before_link_creation(self):
        preview = create_handoff(
            "session-a",
            [
                {"field_id": self.name_field, "question": "Can Alex Rivera's witness say their name?"},
                {"field_id": self.years_field, "question": "How long have you known them?"},
            ],
        )
        self.assertTrue(preview["leak_detected"])
        self.assertEqual([item["leak"] for item in preview["items"]], [True, False])
        with self.assertRaisesRegex(HandoffError, "may reveal a private answer") as raised:
            send_handoff("session-a", preview["id"])
        self.assertEqual(raised.exception.status_code, 422)

    def test_choosing_questions_is_validated(self):
        with self.assertRaisesRegex(HandoffError, "at least one"):
            create_handoff("session-a", [])
        with self.assertRaisesRegex(HandoffError, "only be sent once"):
            create_handoff(
                "session-a",
                [{"field_id": self.name_field}, {"field_id": self.name_field}],
            )
        with self.assertRaisesRegex(HandoffError, "already answered") as raised:
            create_handoff("session-a", [{"field_id": self.other_field}])
        self.assertEqual(raised.exception.status_code, 409)
        with self.assertRaisesRegex(HandoffError, "not part of this renewal"):
            create_handoff("session-a", [{"field_id": 9999}])

    def test_only_one_open_request_at_a_time_and_new_previews_replace_drafts(self):
        first = create_handoff("session-a", [{"field_id": self.name_field}])
        second = create_handoff("session-a", [{"field_id": self.years_field}])
        self.assertEqual(db.row("SELECT status FROM handoffs WHERE id = ?", (first["id"],))["status"], "cancelled")
        send_handoff("session-a", second["id"])
        third = create_handoff("session-a", [{"field_id": self.name_field}])
        with self.assertRaisesRegex(HandoffError, "already open") as raised:
            send_handoff("session-a", third["id"])
        self.assertEqual(raised.exception.status_code, 409)

    def test_expired_link_returns_only_a_closed_message(self):
        preview, token = self._sent_for_both()
        db.execute("UPDATE handoffs SET expires_at = 0 WHERE id = ?", (preview["id"],))
        for call in (lambda: public_packet(token), lambda: answer_handoff(token, {1: "late"})):
            with self.assertRaisesRegex(HandoffError, "no longer works") as raised:
                call()
            self.assertEqual(raised.exception.status_code, 410)

    def test_cancelled_link_cannot_open_or_submit(self):
        preview, token = self._sent_for_both()
        self.assertEqual(cancel_handoff("session-a", preview["id"]), {"status": "cancelled"})
        with self.assertRaisesRegex(HandoffError, "no longer works"):
            public_packet(token)
        with self.assertRaisesRegex(HandoffError, "no longer works"):
            answer_handoff(token, {1: "A late answer"})

    def test_existing_databases_gain_the_questions_column(self):
        legacy = Path(self.temp.name) / "legacy.db"
        connection = sqlite3.connect(legacy)
        connection.execute(
            "CREATE TABLE handoffs (id INTEGER PRIMARY KEY, session_id TEXT, field_ids_json TEXT NOT NULL, "
            "question TEXT NOT NULL, status TEXT NOT NULL, created_at REAL NOT NULL)"
        )
        connection.commit()
        connection.close()
        with patch.object(db, "DB_PATH", legacy):
            db.init()
            with db.connect() as c:
                columns = {row["name"] for row in c.execute("PRAGMA table_info(handoffs)")}
        self.assertIn("items_json", columns)


if __name__ == "__main__":
    unittest.main()
