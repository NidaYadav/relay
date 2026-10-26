import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import db, samples
from app.agents.evidence import extract_evidence
from app.agents.orchestrator import process_session


def field(key, label, source="documents", answer_type="text"):
    return {"key": key, "label": label, "source": source, "answer_type": answer_type}


FIELDS = [
    field("applicant_name", "Applicant full name"),
    field("date_of_birth", "Date of birth", answer_type="date"),
    field("monthly_income", "Monthly income before tax"),
    field("household_size", "Number of people in your household", source="person"),
    field("years_known", "How many years have you lived here?", source="person"),
    field("witness_name", "Name of witness who knows you", source="helper"),
]


def finding(key, value, document, quote, page=1, confidence="high", image=False):
    return {
        "field_key": key,
        "value": value,
        "document": document,
        "page": page,
        "quote": quote,
        "confidence": confidence,
        "read_from_image": image,
    }


class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.docs = Path(cls.temp.name)
        with patch.object(samples, "DOCS", cls.docs):
            samples.generate_samples()
        cls.vault = [
            {"filename": path.name, "path": str(path)}
            for path in sorted((cls.docs / "vault").glob("*.pdf"))
        ]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_verified_fabricated_unknown_helper_and_scanned_findings(self):
        model_output = {
            "findings": [
                finding("applicant_name", "Alex Rivera", "identity_card.pdf", "Alex Rivera"),
                finding("date_of_birth", "4 April 1962", "identity_card.pdf", "Born on 4 April 1962"),
                finding(
                    "monthly_income",
                    "NZD 1,840",
                    "bank_statement.pdf",
                    "Monthly income before tax: NZD 1,840",
                    page=3,
                ),
                finding("not_a_question", "x", "identity_card.pdf", "Alex Rivera"),
                finding("witness_name", "Someone", "identity_card.pdf", "Alex Rivera"),
                finding(
                    "household_size",
                    "2",
                    "witness_note_scan.pdf",
                    "I have known Alex Rivera for five years.",
                    image=True,
                ),
                finding(
                    "years_known",
                    "five years",
                    "witness_note_scan.pdf",
                    "I have known Alex Rivera for five years.",
                    image=True,
                ),
                finding("applicant_name", "Duplicate", "identity_card.pdf", "Alex Rivera"),
            ]
        }
        with patch("app.agents.evidence.structured_pdfs", return_value=model_output):
            found = extract_evidence(self.vault, FIELDS)

        self.assertEqual(set(found), {"applicant_name", "date_of_birth", "monthly_income", "years_known"})
        self.assertNotIn("household_size", found)
        name = found["applicant_name"]
        self.assertEqual(name["value"], "Alex Rivera")
        self.assertTrue(name["evidence"]["verified"])
        self.assertEqual(name["evidence"]["title"], "Identity card")
        self.assertIsNotNone(name["evidence"]["rect"])

        self.assertFalse(found["date_of_birth"]["evidence"]["verified"])

        income = found["monthly_income"]["evidence"]
        self.assertTrue(income["verified"])
        self.assertEqual(income["page"], 1)

        scan = found["years_known"]["evidence"]
        self.assertFalse(scan["verified"])
        self.assertTrue(scan["read_from_image"])

    def test_no_documents_or_no_askable_fields_makes_no_api_call(self):
        with patch("app.agents.evidence.structured_pdfs") as call:
            self.assertEqual(extract_evidence([], FIELDS), {})
            self.assertEqual(
                extract_evidence(self.vault, [field("witness_name", "Witness", source="helper")]),
                {},
            )
        call.assert_not_called()

    def test_pipeline_stores_proposed_answers_with_evidence(self):
        task = {
            "task": "Synthetic renewal",
            "issuer": "Example Services",
            "deadline": None,
            "deadline_quote": None,
            "summary": "Renew.",
            "evidence_required": [],
            "sections": [
                {
                    "title": "Part A",
                    "fields": [
                        {
                            "key": "applicant_name",
                            "label": "Applicant full name",
                            "plain_label": "Your name",
                            "help": "",
                            "required": True,
                            "answer_type": "text",
                            "options": [],
                            "answer_source": "documents",
                            "helper_reason": None,
                            "pdf_field": "applicant_name",
                        },
                        {
                            "key": "witness_name",
                            "label": "Witness",
                            "plain_label": "Witness",
                            "help": "",
                            "required": True,
                            "answer_type": "text",
                            "options": [],
                            "answer_source": "helper",
                            "helper_reason": "Another person",
                            "pdf_field": "witness_name",
                        },
                    ],
                }
            ],
        }
        output = {"findings": [finding("applicant_name", "Alex Rivera", "identity_card.pdf", "Alex Rivera")]}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (
                patch.object(db, "DATA_DIR", root),
                patch.object(db, "UPLOADS", root / "uploads"),
                patch.object(db, "DB_PATH", root / "relay.db"),
            ):
                db.init()
                db.execute(
                    "INSERT INTO sessions(id, created_at, status, mode) VALUES ('s1', strftime('%s','now'), 'reading', 'ai')"
                )
                folder = db.UPLOADS / "s1"
                folder.mkdir(parents=True)
                for role, source in (
                    ("form", self.docs / "renewal_form.pdf"),
                    ("evidence", self.docs / "vault" / "identity_card.pdf"),
                ):
                    destination = folder / source.name
                    shutil.copyfile(source, destination)
                    db.execute(
                        "INSERT INTO documents(session_id, role, filename, path, kind) VALUES ('s1', ?, ?, ?, 'PDF')",
                        (role, source.name, str(destination)),
                    )
                with (
                    patch("app.agents.mapper.structured_pdf", return_value=task),
                    patch("app.agents.evidence.structured_pdfs", return_value=output),
                ):
                    process_session("s1")

                self.assertEqual(db.row("SELECT status FROM sessions WHERE id = 's1'")["status"], "ready")
                rows = {
                    row["key"]: row
                    for row in db.rows("SELECT key, value, origin, status, evidence_json FROM fields WHERE session_id = 's1'")
                }
                self.assertEqual(rows["applicant_name"]["value"], "Alex Rivera")
                self.assertEqual(rows["applicant_name"]["status"], "proposed")
                self.assertEqual(rows["applicant_name"]["origin"], "documents")
                self.assertIn('"verified": true', rows["applicant_name"]["evidence_json"])
                self.assertIsNone(rows["witness_name"]["value"])
                self.assertEqual(rows["witness_name"]["status"], "open")


if __name__ == "__main__":
    unittest.main()
