import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf
from fastapi.testclient import TestClient

from app import db, samples, vault
from app.main import app


def pdf_bytes(name):
    return (VaultTests.docs / name).read_bytes()


class VaultTests(unittest.TestCase):
    docs = None

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
        self.data_temp = tempfile.TemporaryDirectory()
        root = Path(self.data_temp.name)
        self.patches = [
            patch.object(samples, "DOCS", self.docs),
            patch.object(db, "DATA_DIR", root),
            patch.object(db, "UPLOADS", root / "uploads"),
            patch.object(db, "DB_PATH", root / "relay.db"),
            patch.dict(
                os.environ,
                {"OPENAI_API_KEY": "test-placeholder-not-a-credential", "RELAY_MODEL": "test-model"},
            ),
            patch("app.main.process_session", lambda session_id: None),
        ]
        for item in self.patches:
            item.start()
        self.client = TestClient(app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.data_temp.cleanup()

    def upload(self, *names, extra=()):
        files = [("files", (name, pdf_bytes(f"vault/{name}"), "application/pdf")) for name in names]
        files += [("files", item) for item in extra]
        return self.client.post("/api/vault/documents", files=files)

    def evidence_rows(self, session_id):
        deadline = time.time() + 5
        while time.time() < deadline:
            rows = db.rows(
                "SELECT role, filename, path FROM documents WHERE session_id = ? ORDER BY id",
                (session_id,),
            )
            if rows:
                return rows
        return []

    def test_demo_vault_lists_titles_kinds_and_pages(self):
        listed = {doc["filename"]: doc for doc in vault.list_demo()}
        self.assertEqual(
            set(listed),
            {"identity_card.pdf", "assessment_letter.pdf", "bank_statement.pdf", "witness_note_scan.pdf"},
        )
        self.assertEqual(listed["identity_card.pdf"]["title"], "Identity card")
        self.assertEqual(listed["witness_note_scan.pdf"]["kind"], "PDF with scanned pages")
        self.assertTrue(all(doc["pages"] == 1 for doc in listed.values()))

    def test_a_new_vault_is_empty_and_the_demo_is_listed_separately(self):
        data = self.client.get("/api/vault").json()
        self.assertEqual(data["mine"]["documents"], [])
        self.assertEqual(data["mine"]["usage"]["count"], 0)
        self.assertEqual(len(data["demo"]["documents"]), 4)

    def test_uploaded_pdfs_are_saved_in_the_database_and_listed(self):
        response = self.upload("identity_card.pdf", "bank_statement.pdf")
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual([r["outcome"] for r in data["results"]], ["added", "added"])
        by_name = {doc["filename"]: doc for doc in data["documents"]}
        self.assertEqual(by_name["identity_card.pdf"]["title"], "Identity card")
        self.assertEqual(by_name["bank_statement.pdf"]["pages"], 1)
        self.assertEqual(by_name["bank_statement.pdf"]["size"], len(pdf_bytes("vault/bank_statement.pdf")))
        stored = db.row("SELECT content FROM vault_documents WHERE filename = 'identity_card.pdf'")
        self.assertEqual(stored["content"], pdf_bytes("vault/identity_card.pdf"))
        self.assertEqual(self.client.get("/api/vault").json()["mine"]["usage"]["count"], 2)

    def test_uploading_the_same_filename_replaces_the_copy(self):
        self.upload("identity_card.pdf")
        second = self.upload("identity_card.pdf").json()
        self.assertEqual(second["results"][0]["outcome"], "replaced")
        self.assertEqual(second["usage"]["count"], 1)

    def test_bad_files_are_rejected_with_a_reason_and_good_ones_still_saved(self):
        data = self.upload(
            "identity_card.pdf",
            extra=[
                ("notes.txt", b"hello", "text/plain"),
                ("fake.pdf", b"%PDF-1.4 this is not really a pdf", "application/pdf"),
                ("empty.pdf", b"", "application/pdf"),
            ],
        ).json()
        outcomes = {item["filename"]: item for item in data["results"]}
        self.assertEqual(outcomes["identity_card.pdf"]["outcome"], "added")
        self.assertEqual(outcomes["notes.txt"]["reason"], "Only PDF files can be added.")
        self.assertEqual(outcomes["fake.pdf"]["outcome"], "rejected")
        self.assertEqual(outcomes["empty.pdf"]["reason"], "The file is empty.")
        self.assertEqual([doc["filename"] for doc in data["documents"]], ["identity_card.pdf"])

    def test_password_protected_pdfs_are_rejected(self):
        document = pymupdf.open()
        document.new_page().insert_text((72, 72), "secret")
        locked = document.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="pw", owner_pw="pw")
        data = self.upload(extra=[("locked.pdf", locked, "application/pdf")]).json()
        self.assertEqual(data["results"][0]["outcome"], "rejected")
        self.assertIn("password-protected", data["results"][0]["reason"])

    def test_limits_on_document_count_and_total_size(self):
        with patch.object(vault, "MAX_VAULT_DOCUMENTS", 1):
            self.upload("identity_card.pdf")
            data = self.upload("bank_statement.pdf").json()
        self.assertIn("at most 1 documents", data["results"][0]["reason"])
        with patch.object(vault, "MAX_VAULT_BYTES", 100):
            data = self.upload("assessment_letter.pdf").json()
        self.assertIn("vault is full", data["results"][0]["reason"])
        with patch.object(vault, "MAX_FILE_BYTES", 100):
            data = self.upload("assessment_letter.pdf").json()
        self.assertIn("larger than", data["results"][0]["reason"])

    def test_documents_can_be_deleted(self):
        listed = self.upload("identity_card.pdf", "bank_statement.pdf").json()["documents"]
        first = next(doc for doc in listed if doc["filename"] == "identity_card.pdf")
        self.assertEqual(self.client.delete(f"/api/vault/documents/{first['id']}").status_code, 200)
        remaining = self.client.get("/api/vault").json()["mine"]["documents"]
        self.assertEqual([doc["filename"] for doc in remaining], ["bank_statement.pdf"])
        self.assertEqual(self.client.delete(f"/api/vault/documents/{first['id']}").status_code, 404)

    def test_main_flow_snapshots_the_database_vault(self):
        self.upload("identity_card.pdf", "bank_statement.pdf")
        form = pdf_bytes("renewal_form.pdf")
        response = self.client.post(
            "/api/sessions", files={"form_file": ("my_form.pdf", form, "application/pdf")}
        )
        self.assertEqual(response.status_code, 200, response.text)
        rows = self.evidence_rows(response.json()["session_id"])
        self.assertEqual(
            [(row["role"], row["filename"]) for row in rows],
            [("form", "my_form.pdf"), ("evidence", "bank_statement.pdf"), ("evidence", "identity_card.pdf")],
        )
        copied = {row["filename"]: Path(row["path"]).read_bytes() for row in rows}
        self.assertEqual(copied["identity_card.pdf"], pdf_bytes("vault/identity_card.pdf"))

    def test_sample_flow_reads_the_demo_folder_not_the_database_vault(self):
        self.upload("witness_note_scan.pdf")
        response = self.client.post("/api/sessions", data={"sample": "true"})
        self.assertEqual(response.status_code, 200, response.text)
        rows = self.evidence_rows(response.json()["session_id"])
        self.assertEqual(rows[0]["filename"], "renewal_form.pdf")
        self.assertEqual(
            sorted(row["filename"] for row in rows[1:]),
            ["assessment_letter.pdf", "bank_statement.pdf", "identity_card.pdf", "witness_note_scan.pdf"],
        )

    def test_empty_vault_is_reported_and_form_is_still_read(self):
        form = pdf_bytes("renewal_form.pdf")
        response = self.client.post(
            "/api/sessions", files={"form_file": ("my_form.pdf", form, "application/pdf")}
        )
        self.assertEqual(response.status_code, 200, response.text)
        session_id = response.json()["session_id"]
        rows = self.evidence_rows(session_id)
        messages = [e["message"] for e in self.client.get(f"/api/sessions/{session_id}").json()["events"]]
        self.assertEqual([row["role"] for row in rows], ["form"])
        self.assertIn("Your vault has no PDFs, so every question will be asked of you.", messages)

    def test_forgetting_a_session_keeps_the_vault(self):
        self.upload("identity_card.pdf")
        form = pdf_bytes("renewal_form.pdf")
        session_id = self.client.post(
            "/api/sessions", files={"form_file": ("my_form.pdf", form, "application/pdf")}
        ).json()["session_id"]
        self.evidence_rows(session_id)
        self.assertEqual(self.client.delete(f"/api/sessions/{session_id}").status_code, 200)
        self.assertEqual(len(self.client.get("/api/vault").json()["mine"]["documents"]), 1)

    def test_non_pdf_form_is_rejected_and_pages_are_served(self):
        response = self.client.post(
            "/api/sessions", files={"form_file": ("form.txt", b"hello", "text/plain")}
        )
        self.assertEqual(response.status_code, 415)
        self.assertEqual(self.client.get("/vault").status_code, 200)
        self.assertIn("Add documents", self.client.get("/vault").text)


if __name__ == "__main__":
    unittest.main()
