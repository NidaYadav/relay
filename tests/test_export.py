import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf
from fastapi.testclient import TestClient

from app import db, samples
from app.main import app


class ExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs_temp = tempfile.TemporaryDirectory()
        cls.docs = Path(cls.docs_temp.name)
        with patch.object(samples, "DOCS", cls.docs):
            samples.generate_samples()

    @classmethod
    def tearDownClass(cls):
        cls.docs_temp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.patches = [
            patch.object(db, "DATA_DIR", root),
            patch.object(db, "UPLOADS", root / "uploads"),
            patch.object(db, "DB_PATH", root / "relay.db"),
            patch.dict(
                os.environ,
                {"OPENAI_API_KEY": "test-placeholder-not-a-credential", "RELAY_MODEL": "test-model"},
            ),
        ]
        for item in self.patches:
            item.start()
        self.client = TestClient(app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def make_session(self, status="ready"):
        db.execute(
            "INSERT INTO sessions(id, created_at, status, mode, task_json) VALUES ('s1', strftime('%s','now'), ?, 'ai', ?)",
            (status, '{"task": "Synthetic renewal"}'),
        )
        folder = db.UPLOADS / "s1"
        folder.mkdir(parents=True)
        destination = folder / "form.pdf"
        shutil.copyfile(self.docs / "renewal_form.pdf", destination)
        db.execute(
            "INSERT INTO documents(session_id, role, filename, path, kind, pages) VALUES ('s1', 'form', 'form.pdf', ?, 'fillable PDF', 3)",
            (str(destination),),
        )
        rows = [
            (1, "Part A", "applicant_name", "Applicant full name", "Alex Rivera", "documents", "proposed",
             '{"title": "Identity card", "page": 1, "verified": true, "read_from_image": false}'),
            (2, "Part A", "date_of_birth", "Date of birth", "3 March 1961", "documents", "proposed",
             '{"title": "Identity card", "page": 1, "verified": false, "read_from_image": false}'),
            (3, "Part B", "household_size", "Number of people in your household", "2", "user", "done", None),
            (4, "Part C", "witness_name", "Name of witness who knows you", "Sam Taylor", "helper", "done", None),
            (5, "Part C", "witness_duration", "How long has the witness known you?", None, None, "open", None),
        ]
        for ord_, section, key, label, value, origin, status_, evidence in rows:
            db.execute(
                """
                INSERT INTO fields(session_id, ord, section, key, label, pdf_field, value, origin, status, evidence_json, source)
                VALUES ('s1', ?, ?, ?, ?, ?, ?, ?, ?, ?, 'person')
                """,
                (ord_, section, key, label, key, value, origin, status_, evidence),
            )

    def test_export_fills_the_form_and_lists_each_question_with_its_answer(self):
        self.make_session()
        response = self.client.get("/api/sessions/s1/export.pdf")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/pdf")

        with pymupdf.open(stream=response.content, filetype="pdf") as document:
            values = {
                widget.field_name: widget.field_value
                for page in document
                for widget in (page.widgets() or [])
            }
            text = " ".join("\n".join(page.get_text("text") for page in document).split())
        self.assertEqual(values["applicant_name"], "Alex Rivera")
        self.assertEqual(values["household_size"], "2")
        self.assertEqual(values["witness_name"], "Sam Taylor")
        self.assertEqual(values["witness_duration"], "")

        for expected in (
            "Questions and answers",
            "4 of 5 questions have an answer.",
            "Applicant full name",
            "Alex Rivera",
            "Your vault: Identity card, page 1 - not yet reviewed",
            "not found in the document text, please check",
            "Number of people in your household",
            "Your helper, approved by you",
            "Not answered",
        ):
            self.assertIn(expected, text)

    def test_export_waits_until_the_session_is_ready(self):
        self.make_session(status="reading")
        self.assertEqual(self.client.get("/api/sessions/s1/export.pdf").status_code, 409)
        self.assertEqual(self.client.get("/api/sessions/missing/export.pdf").status_code, 404)

    def test_export_explains_when_the_stored_form_is_gone(self):
        self.make_session()
        for path in (db.UPLOADS / "s1").glob("*.pdf"):
            path.unlink()
        response = self.client.get("/api/sessions/s1/export.pdf")
        self.assertEqual(response.status_code, 410)
        self.assertIn("no longer stored", response.json()["detail"])

    def test_forget_removes_rows_and_files(self):
        self.make_session()
        folder = db.UPLOADS / "s1"
        self.assertTrue(folder.exists())
        self.assertEqual(self.client.delete("/api/sessions/s1").status_code, 200)
        self.assertFalse(folder.exists())
        self.assertEqual(self.client.get("/api/sessions/s1").status_code, 404)
        self.assertEqual(self.client.get("/api/sessions/s1/export.pdf").status_code, 404)
        self.assertEqual(db.rows("SELECT id FROM fields WHERE session_id = 's1'"), [])
        self.assertEqual(self.client.delete("/api/sessions/s1").status_code, 404)


if __name__ == "__main__":
    unittest.main()
