import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf
from openai import APIStatusError

from app import db
from app.agents.intake import inspect_pdf
from app.agents.llm import LLMError, structured_pdf, validate_config
from app.agents.orchestrator import process_session
from app import samples


class SamplePacketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sample_temp = tempfile.TemporaryDirectory()
        cls.docs = Path(cls.sample_temp.name)
        with patch.object(samples, "DOCS", cls.docs):
            samples.generate_samples()

    @classmethod
    def tearDownClass(cls):
        cls.sample_temp.cleanup()

    def test_sample_packet_contains_form_and_vault_pdfs(self):
        self.assertTrue((self.docs / "renewal_form.pdf").is_file())
        vault_files = sorted((self.docs / "vault").glob("*.pdf"))
        self.assertEqual(
            {path.name for path in vault_files},
            {
                "identity_card.pdf",
                "assessment_letter.pdf",
                "bank_statement.pdf",
                "witness_note_scan.pdf",
            },
        )
        for path in [self.docs / "renewal_form.pdf", *vault_files]:
            with pymupdf.open(path) as document:
                self.assertGreater(len(document), 0, path.name)
                self.assertTrue(document[0].get_text("text") or path.name == "witness_note_scan.pdf")

    def test_sample_packet_has_ten_matching_document_answers(self):
        form = inspect_pdf(self.docs / "renewal_form.pdf")
        answer_values = {
            key: answer for key, _, answer in samples.FORM_FIELDS
        }
        supporting_text = "\n".join(
            inspect_pdf(path)["text"] for path in (self.docs / "vault").glob("*.pdf")
        )
        form_text = " ".join(form["text"].split())

        self.assertEqual(len(samples.FORM_FIELDS), 14)
        self.assertEqual(len(samples.DOCUMENT_ANSWER_KEYS), 10)
        self.assertLessEqual(samples.DOCUMENT_ANSWER_KEYS, set(form["field_names"]))
        for key in samples.DOCUMENT_ANSWER_KEYS:
            self.assertTrue(answer_values[key], key)
            self.assertIn(answer_values[key], supporting_text, key)
        self.assertIn("assessment letter", form_text)
        self.assertIn("bank statement", form_text)
        self.assertIn("Review each answer", form_text)

    def test_form_contains_demo_deadline_and_fillable_questions(self):
        form = inspect_pdf(self.docs / "renewal_form.pdf")
        self.assertIn("30 November 2026", form["text"])
        self.assertGreaterEqual(len(form["field_names"]), 12)
        self.assertIn("witness_name", form["field_names"])

    def test_witness_pdf_is_an_image_scan(self):
        scan = inspect_pdf(self.docs / "vault" / "witness_note_scan.pdf")
        self.assertEqual(scan["pages"], 1)
        self.assertTrue(scan["page_details"][0]["scanned"])

    def test_server_requires_api_configuration(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "OPENAI_API_KEY and RELAY_MODEL"):
                validate_config()

    def test_api_authentication_error_is_actionable_without_fallback(self):
        class UnauthorizedStatusError(APIStatusError):
            def __init__(self):
                Exception.__init__(self, "Unauthorized")
                self.status_code = 401

        class FakeResponses:
            def create(self, **_kwargs):
                raise UnauthorizedStatusError()

        class FakeClient:
            responses = FakeResponses()

        with (
            patch.dict(
                os.environ,
                {
                    "OPENAI_API_KEY": "test-placeholder-not-a-credential",
                    "RELAY_MODEL": "test-model",
                },
            ),
            patch("app.agents.llm.OpenAI", return_value=FakeClient()),
        ):
            with self.assertRaisesRegex(LLMError, "rejected the API key"):
                structured_pdf(
                    "system",
                    "prompt",
                    self.docs / "renewal_form.pdf",
                    {"type": "object"},
                    "test_result",
                )

    def test_pipeline_stores_brief_and_fields_with_stubbed_api_result(self):
        task = {
            "task": "Synthetic renewal",
            "issuer": "Example Services",
            "deadline": "30 November 2026",
            "deadline_quote": "Please return this renewal by 30 November 2026.",
            "summary": "Renew your synthetic public support.",
            "evidence_required": ["Assessment letter"],
            "sections": [
                {
                    "title": "Part A — About you",
                    "fields": [
                        {
                            "key": "applicant_name",
                            "label": "Applicant full name",
                            "plain_label": "What is your full name?",
                            "help": "",
                            "required": True,
                            "answer_type": "text",
                            "options": [],
                            "answer_source": "person",
                            "helper_reason": None,
                            "pdf_field": "applicant_name",
                        },
                        {
                            "key": "witness_name",
                            "label": "Witness name",
                            "plain_label": "Who can confirm this?",
                            "help": "",
                            "required": True,
                            "answer_type": "text",
                            "options": [],
                            "answer_source": "helper",
                            "helper_reason": "The form asks for another person's confirmation.",
                            "pdf_field": "witness_name",
                        },
                    ],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (
                patch.object(db, "DATA_DIR", root),
                patch.object(db, "UPLOADS", root / "uploads"),
                patch.object(db, "DB_PATH", root / "relay.db"),
            ):
                db.init()
                session_id = "sample-session"
                db.execute(
                    "INSERT INTO sessions(id, created_at, status, mode) VALUES (?, 1, 'reading', 'ai')",
                    (session_id,),
                )
                folder = db.UPLOADS / session_id
                folder.mkdir(parents=True)
                for role, source_path in (
                    ("form", self.docs / "renewal_form.pdf"),
                    ("evidence", self.docs / "vault" / "assessment_letter.pdf"),
                ):
                    filename = source_path.name
                    source = source_path
                    destination = folder / filename
                    shutil.copyfile(source, destination)
                    db.execute(
                        "INSERT INTO documents(session_id, role, filename, path, kind) VALUES (?, ?, ?, ?, 'PDF')",
                        (session_id, role, filename, str(destination)),
                    )
                with (
                    patch("app.agents.mapper.structured_pdf", return_value=task),
                    patch("app.agents.evidence.structured_pdfs", return_value={"findings": []}),
                ):
                    process_session(session_id)

                session = db.row(
                    "SELECT status, task_json FROM sessions WHERE id = ?",
                    (session_id,),
                )
                self.assertEqual(session["status"], "ready")
                self.assertIn('"deadline": "30 November 2026"', session["task_json"])
                fields = db.rows(
                    "SELECT key, source FROM fields WHERE session_id = ? ORDER BY ord",
                    (session_id,),
                )
                self.assertEqual(fields, [
                    {"key": "applicant_name", "source": "person"},
                    {"key": "witness_name", "source": "helper"},
                ])
                docs = db.rows(
                    "SELECT filename, pages, kind FROM documents WHERE session_id = ? ORDER BY filename",
                    (session_id,),
                )
                self.assertEqual(len(docs), 2)
                self.assertEqual(
                    [(doc["filename"], doc["pages"]) for doc in docs],
                    [("assessment_letter.pdf", 1), ("renewal_form.pdf", 3)],
                )


if __name__ == "__main__":
    unittest.main()
