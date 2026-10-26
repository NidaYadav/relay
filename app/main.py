import json
import threading
import uuid
from typing import Literal
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from app import db, samples, vault
from app.agents.assembler import build_export
from app.agents.llm import validate_config
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
from app.agents.orchestrator import log, process_session

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
app = FastAPI(title="Relay", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=WEB), name="static")


class HandoffItem(BaseModel):
    field_id: int
    question: str | None = Field(default=None, max_length=300)


class HandoffRequest(BaseModel):
    items: list[HandoffItem] = Field(min_length=1, max_length=10)


class HelperAnswerItem(BaseModel):
    number: int
    answer: str = Field(max_length=2000)


class HelperAnswers(BaseModel):
    answers: list[HelperAnswerItem] = Field(min_length=1, max_length=10)


class HandoffDecision(BaseModel):
    decision: Literal["approve", "reject"]


@app.on_event("startup")
def startup():
    validate_config()
    db.init()


@app.get("/")
def home():
    return FileResponse(WEB / "index.html")


def read_pdf_upload(upload: UploadFile):
    filename = Path(upload.filename or "").name
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail=f"{filename or 'File'} is not a PDF.")
    content = upload.file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"{filename} exceeds the 20 MB limit.")
    if not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=415, detail=f"{filename} is not a readable PDF.")
    return filename, content


def save_pdf(session_id: str, role: str, filename: str, content: bytes):
    folder = db.UPLOADS / session_id
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / f"{uuid.uuid4().hex}.pdf"
    destination.write_bytes(content)
    db.execute(
        """
        INSERT INTO documents(session_id, role, filename, path, kind)
        VALUES (?, ?, ?, ?, 'PDF')
        """,
        (session_id, role, filename, str(destination)),
    )


@app.post("/api/sessions")
async def create_session(
    sample: bool = Form(False),
    form_file: UploadFile | None = File(None),
):
    session_id = uuid.uuid4().hex
    incoming = []
    notices = []
    if sample:
        form_path = samples.DOCS / "renewal_form.pdf"
        if not form_path.is_file():
            raise HTTPException(
                status_code=503,
                detail="Synthetic sample PDFs are missing. Run `python -m app.samples` and retry.",
            )
        incoming.append(("form", form_path.name, form_path.read_bytes()))
        vault_items = [
            (path.name, path.read_bytes()) for path in vault.vault_files(vault.demo_vault_dir())
        ]
    else:
        if form_file is None:
            raise HTTPException(status_code=400, detail="Choose one PDF form to begin.")
        form_name, form_content = read_pdf_upload(form_file)
        incoming.append(("form", form_name, form_content))
        vault_items = [(row["filename"], row["content"]) for row in vault.stored_documents()]

    if not vault_items:
        notices.append("Your vault has no PDFs, so every question will be asked of you.")
    for filename, content in vault_items:
        incoming.append(("evidence", filename, content))

    if not incoming:
        raise HTTPException(status_code=400, detail="No PDF documents were provided.")
    db.execute(
        "INSERT INTO sessions(id, created_at, status, mode) VALUES (?, strftime('%s','now'), 'reading', 'ai')",
        (session_id,),
    )
    try:
        for role, filename, content in incoming:
            if not content.startswith(b"%PDF-"):
                raise HTTPException(
                    status_code=415,
                    detail=f"{filename} is not a readable PDF.",
                )
            save_pdf(session_id, role, filename, content)
    except Exception:
        db.delete_session(session_id)
        raise
    log(session_id, "Relay", "Your form and vault are ready for review")
    for message in notices:
        log(session_id, "Intake", message, "warning")
    threading.Thread(target=process_session, args=(session_id,), daemon=True).start()
    return {"session_id": session_id}


@app.get("/vault")
def vault_page():
    return FileResponse(WEB / "vault.html")


@app.get("/api/vault")
def get_vault():
    return {
        "mine": {"documents": vault.list_stored(), "usage": vault.usage()},
        "demo": {"folder": "docs/vault", "documents": vault.list_demo()},
    }


@app.post("/api/vault/documents")
def add_vault_documents(files: list[UploadFile] = File(...)):
    results = []
    for upload in files:
        filename = Path(upload.filename or "").name or "file"
        try:
            content = upload.file.read(vault.MAX_FILE_BYTES + 1)
            outcome = vault.add_document(filename, content)
            results.append({"filename": filename, "outcome": outcome})
        except vault.VaultError as exc:
            results.append({"filename": filename, "outcome": "rejected", "reason": str(exc)})
    return {
        "results": results,
        "documents": vault.list_stored(),
        "usage": vault.usage(),
    }


@app.delete("/api/vault/documents/{document_id}")
def delete_vault_document(document_id: int):
    if not vault.delete_document(document_id):
        raise HTTPException(status_code=404, detail="That document is not in your vault.")
    return {"deleted": True, "usage": vault.usage()}


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str):
    session = db.row(
        "SELECT id, status, task_json, error FROM sessions WHERE id = ?",
        (session_id,),
    )
    if not session:
        raise HTTPException(status_code=404, detail="This Relay session was not found.")
    documents = db.rows(
        "SELECT filename, role, kind, pages FROM documents WHERE session_id = ? ORDER BY id",
        (session_id,),
    )
    events = db.rows(
        "SELECT at, agent, message, level FROM events WHERE session_id = ? ORDER BY id",
        (session_id,),
    )
    fields = db.rows(
        """
        SELECT id, ord, section, key, label, plain_label, required, source,
               helper_reason, pdf_field, value, origin, status, evidence_json
        FROM fields WHERE session_id = ? ORDER BY ord
        """,
        (session_id,),
    )
    for field in fields:
        field["evidence"] = db.loads(field.pop("evidence_json"))
    handoffs = db.rows(
        """
        SELECT id, question, items_json, field_ids_json, status, answer_json, token, expires_at
        FROM handoffs WHERE session_id = ? AND status != 'draft' ORDER BY id DESC
        """,
        (session_id,),
    )
    handoffs = [handoff_summary(handoff) for handoff in handoffs]
    counts = {"person": 0, "documents": 0, "helper": 0}
    for field in fields:
        if field["status"] in {"done", "skipped"}:
            continue
        if field["status"] == "proposed":
            counts["documents"] += 1
        elif field["source"] == "helper":
            counts["helper"] += 1
        else:
            counts["person"] += 1
    task = json.loads(session["task_json"]) if session["task_json"] else None
    return {
        "session_id": session["id"],
        "status": session["status"],
        "task": task,
        "error": session["error"],
        "documents": documents,
        "events": events,
        "fields": fields,
        "counts": counts,
        "handoffs": handoffs,
    }


@app.get("/api/sessions/{session_id}/export.pdf")
def export_answers(session_id: str):
    session = db.row("SELECT status FROM sessions WHERE id = ?", (session_id,))
    if not session:
        raise HTTPException(status_code=404, detail="This Relay session was not found.")
    if session["status"] != "ready":
        raise HTTPException(status_code=409, detail="The form is still being read.")
    form = db.row("SELECT path FROM documents WHERE session_id = ? AND role = 'form'", (session_id,))
    if not form or not Path(form["path"]).is_file():
        raise HTTPException(
            status_code=410,
            detail="This session's form is no longer stored, so it can't be exported. Start a new run.",
        )
    return Response(
        content=build_export(session_id),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="relay-questions-and-answers.pdf"'},
    )


@app.delete("/api/sessions/{session_id}")
def forget_session(session_id: str):
    if not db.row("SELECT id FROM sessions WHERE id = ?", (session_id,)):
        raise HTTPException(status_code=404, detail="This Relay session was not found.")
    db.delete_session(session_id)
    return {"deleted": True}


@app.post("/api/sessions/{session_id}/handoffs")
def prepare_handoff(session_id: str, request: HandoffRequest):
    if not db.row("SELECT id FROM sessions WHERE id = ?", (session_id,)):
        raise HTTPException(status_code=404, detail="This Relay session was not found.")
    try:
        preview = create_handoff(
            session_id,
            [{"field_id": item.field_id, "question": item.question} for item in request.items],
        )
    except HandoffError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    count = len(preview["items"])
    log(session_id, "Relay", f"Prepared a helper preview with {count} question{'s' if count != 1 else ''}")
    return preview


@app.post("/api/sessions/{session_id}/handoffs/{handoff_id}/send")
def send_helper_link(session_id: str, handoff_id: int):
    try:
        sent = send_handoff(session_id, handoff_id)
    except HandoffError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    log(session_id, "Relay", "Created a one-time helper link that expires in 24 hours")
    return sent


@app.post("/api/sessions/{session_id}/handoffs/{handoff_id}/decision")
def review_helper_answer(session_id: str, handoff_id: int, decision: HandoffDecision):
    try:
        result = decide_handoff(
            session_id,
            handoff_id,
            approve=decision.decision == "approve",
        )
    except HandoffError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    log(
        session_id,
        "Relay",
        "Approved the helper's answers" if result["status"] == "approved" else "Rejected the helper's answers",
    )
    return result


@app.post("/api/sessions/{session_id}/handoffs/{handoff_id}/cancel")
def cancel_helper_link(session_id: str, handoff_id: int):
    try:
        result = cancel_handoff(session_id, handoff_id)
    except HandoffError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    log(session_id, "Relay", "Cancelled the helper request")
    return result


@app.get("/h/{token}")
def helper_page(token: str):
    return FileResponse(WEB / "helper.html")


@app.get("/api/h/{token}")
def get_helper_packet(token: str):
    try:
        return public_packet(token)
    except HandoffError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.post("/api/h/{token}")
def submit_helper_answer(token: str, request: HelperAnswers):
    handoff = db.row("SELECT session_id FROM handoffs WHERE token = ?", (token,))
    answers = {item.number: item.answer for item in request.answers}
    try:
        result = answer_handoff(token, answers)
    except HandoffError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    if handoff:
        log(handoff["session_id"], "Relay", "The helper submitted their answers")
    return result


@app.post("/api/sessions/{session_id}/retry")
def retry_session(session_id: str):
    session = db.row("SELECT id, status FROM sessions WHERE id = ?", (session_id,))
    if not session:
        raise HTTPException(status_code=404, detail="This Relay session was not found.")
    if session["status"] != "failed":
        raise HTTPException(status_code=409, detail="This session is not ready to retry.")
    db.execute("DELETE FROM fields WHERE session_id = ?", (session_id,))
    db.execute(
        "UPDATE sessions SET status = 'reading', error = NULL, task_json = NULL WHERE id = ?",
        (session_id,),
    )
    log(session_id, "Relay", "Retrying document processing")
    threading.Thread(target=process_session, args=(session_id,), daemon=True).start()
    return {"session_id": session_id}


@app.get("/api/health")
def health():
    return {"status": "ok"}
