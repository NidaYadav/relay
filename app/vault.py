"""The vault: PDFs Relay reads for every form.

The person's own vault lives in the SQLite database. The demo vault is a folder
of synthetic PDFs in docs/vault/ that the sample run reads directly.
"""
import time
from pathlib import Path

from app import db, samples
from app.agents.intake import classify, inspect_pdf, inspect_pdf_bytes

MAX_VAULT_DOCUMENTS = 20
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_VAULT_BYTES = 100 * 1024 * 1024


class VaultError(ValueError):
    pass


def demo_vault_dir() -> Path:
    return samples.DOCS / "vault"


def vault_files(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    files = [
        path
        for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() == ".pdf"
    ]
    return sorted(files, key=lambda path: path.name.casefold())[:MAX_VAULT_DOCUMENTS]


def _title(details: dict, filename: str) -> str:
    return details["title"] or Path(filename).stem.replace("_", " ")


def describe(path: Path) -> dict:
    try:
        details = inspect_pdf(path)
        return {
            "filename": path.name,
            "title": _title(details, path.name),
            "kind": classify(details),
            "pages": details["pages"],
        }
    except ValueError:
        return {
            "filename": path.name,
            "title": path.stem.replace("_", " "),
            "kind": "unreadable PDF",
            "pages": 0,
        }


def list_demo() -> list[dict]:
    return [describe(path) for path in vault_files(demo_vault_dir())]


def list_stored() -> list[dict]:
    return db.rows(
        """
        SELECT id, filename, title, kind, pages, size, added_at
        FROM vault_documents ORDER BY filename COLLATE NOCASE
        """
    )


def usage() -> dict:
    row = db.row("SELECT COUNT(*) AS count, COALESCE(SUM(size), 0) AS bytes FROM vault_documents")
    return {
        "count": row["count"],
        "bytes": row["bytes"],
        "max_documents": MAX_VAULT_DOCUMENTS,
        "max_bytes": MAX_VAULT_BYTES,
        "max_file_bytes": MAX_FILE_BYTES,
    }


def add_document(filename: str, content: bytes) -> str:
    """Save a PDF in the vault. Returns "added" or "replaced"; raises VaultError."""
    filename = Path(filename or "").name
    if not filename.lower().endswith(".pdf"):
        raise VaultError("Only PDF files can be added.")
    if not content:
        raise VaultError("The file is empty.")
    if len(content) > MAX_FILE_BYTES:
        raise VaultError(f"The file is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB.")
    if not content.startswith(b"%PDF-"):
        raise VaultError("This is not a readable PDF.")
    try:
        details = inspect_pdf_bytes(content)
    except ValueError as exc:
        raise VaultError(str(exc)) from exc

    existing = db.row("SELECT id, size FROM vault_documents WHERE filename = ?", (filename,))
    current = usage()
    if existing is None and current["count"] >= MAX_VAULT_DOCUMENTS:
        raise VaultError(f"The vault holds at most {MAX_VAULT_DOCUMENTS} documents. Delete one first.")
    projected = current["bytes"] - (existing["size"] if existing else 0) + len(content)
    if projected > MAX_VAULT_BYTES:
        raise VaultError(f"The vault is full ({MAX_VAULT_BYTES // (1024 * 1024)} MB). Delete a document first.")

    values = (_title(details, filename), classify(details), details["pages"], len(content), content, time.time())
    if existing:
        db.execute(
            """
            UPDATE vault_documents
            SET title = ?, kind = ?, pages = ?, size = ?, content = ?, added_at = ?
            WHERE id = ?
            """,
            (*values, existing["id"]),
        )
        return "replaced"
    db.execute(
        """
        INSERT INTO vault_documents(title, kind, pages, size, content, added_at, filename)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (*values, filename),
    )
    return "added"


def delete_document(document_id: int) -> bool:
    row = db.row("SELECT id FROM vault_documents WHERE id = ?", (document_id,))
    if not row:
        return False
    db.execute("DELETE FROM vault_documents WHERE id = ?", (document_id,))
    return True


def stored_documents() -> list[dict]:
    """The stored PDFs with their bytes, for a run to snapshot."""
    return db.rows(
        "SELECT filename, content FROM vault_documents ORDER BY filename COLLATE NOCASE"
    )
