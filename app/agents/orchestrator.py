import json
import time
from pathlib import Path

from app import db
from app.agents.evidence import extract_evidence
from app.agents.intake import classify, inspect_pdf
from app.agents.mapper import map_form


def log(session_id: str, agent: str, message: str, level: str = "info"):
    db.execute(
        "INSERT INTO events(session_id, at, agent, message, level) VALUES (?, ?, ?, ?, ?)",
        (session_id, time.time(), agent, message, level),
    )


def process_session(session_id: str):
    try:
        documents = db.rows(
            "SELECT * FROM documents WHERE session_id = ? ORDER BY id",
            (session_id,),
        )
        form = next((doc for doc in documents if doc["role"] == "form"), None)
        if not form:
            raise ValueError("Add one PDF form to begin.")

        form_result = inspect_pdf(Path(form["path"]))
        for document in documents:
            origin = "the form" if document["role"] == "form" else "vault document"
            log(session_id, "Intake", f"Reading {origin} {document['filename']}")
            if document["id"] == form["id"]:
                result = form_result
            else:
                try:
                    result = inspect_pdf(Path(document["path"]))
                except ValueError as exc:
                    db.execute(
                        "UPDATE documents SET kind = 'unreadable PDF', pages = 0, text = '' WHERE id = ?",
                        (document["id"],),
                    )
                    log(
                        session_id,
                        "Intake",
                        f"Skipped {document['filename']}: {exc}",
                        "warning",
                    )
                    continue
            kind = classify(result)
            db.execute(
                "UPDATE documents SET kind = ?, pages = ?, text = ?, meta_json = ? WHERE id = ?",
                (
                    kind,
                    result["pages"],
                    result["text"],
                    json.dumps(
                        {
                            "page_details": result["page_details"],
                            "field_names": result["field_names"],
                        }
                    ),
                    document["id"],
                ),
            )
        log(session_id, "Mapper", "Mapping the renewal form with OpenAI")
        task = map_form(
            Path(form["path"]),
            form_result["text"],
            form_result["field_names"],
        )
        db.execute(
            "UPDATE sessions SET task_json = ?, error = NULL WHERE id = ?",
            (json.dumps(task, ensure_ascii=False), session_id),
        )
        ordinal = 0
        for section in task["sections"]:
            for field in section["fields"]:
                ordinal += 1
                db.execute(
                    """
                    INSERT INTO fields(
                        session_id, ord, section, key, label, plain_label, help,
                        required, answer_type, options_json, source, helper_reason,
                        pdf_field, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')
                    """,
                    (
                        session_id,
                        ordinal,
                        section["title"],
                        field["key"],
                        field["label"],
                        field["plain_label"],
                        field["help"],
                        int(field["required"]),
                        field["answer_type"],
                        json.dumps(field["options"]),
                        field["answer_source"],
                        field["helper_reason"],
                        field["pdf_field"],
                    ),
                )
        log(session_id, "Mapper", f"Found {ordinal} questions in the form")
        fields = db.rows(
            "SELECT id, key, label, answer_type, source FROM fields WHERE session_id = ? ORDER BY ord",
            (session_id,),
        )
        vault_documents = db.rows(
            """
            SELECT filename, path FROM documents
            WHERE session_id = ? AND role = 'evidence' AND pages > 0 ORDER BY id
            """,
            (session_id,),
        )
        if not vault_documents:
            log(
                session_id,
                "Evidence",
                "No readable vault documents, so every question will be asked of you.",
                "warning",
            )
        else:
            log(
                session_id,
                "Evidence",
                f"Looking for answers in {len(vault_documents)} vault documents with OpenAI",
            )
            found = extract_evidence(vault_documents, fields)
            for key, finding in found.items():
                db.execute(
                    """
                    UPDATE fields SET value = ?, origin = 'documents', status = 'proposed',
                        evidence_json = ?
                    WHERE session_id = ? AND key = ? AND status = 'open'
                    """,
                    (
                        finding["value"],
                        json.dumps(finding["evidence"], ensure_ascii=False),
                        session_id,
                        key,
                    ),
                )
            unverified = sum(1 for item in found.values() if not item["evidence"]["verified"])
            askable = sum(1 for field in fields if field["source"] != "helper")
            log(
                session_id,
                "Evidence",
                f"Found answers for {len(found)} of {askable} questions"
                + (f"; {unverified} need a check" if unverified else ""),
                "warning" if unverified else "info",
            )
        db.execute(
            "UPDATE sessions SET status = 'ready' WHERE id = ?",
            (session_id,),
        )
    except Exception as exc:
        message = str(exc) or "The document could not be processed. Retry."
        db.execute(
            "UPDATE sessions SET status = 'failed', error = ? WHERE id = ?",
            (message, session_id),
        )
        log(session_id, "Relay", message, "error")
