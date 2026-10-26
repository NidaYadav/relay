import json
import re
import secrets
import time

from app import db

HANDOFF_TTL_SECONDS = 24 * 60 * 60
MAX_QUESTIONS = 10
MAX_QUESTION_LENGTH = 300
MAX_ANSWER_LENGTH = 2000


class HandoffError(ValueError):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _sensitive_terms(session_id: str, excluded_field_ids: list[int]):
    marks = ",".join("?" for _ in excluded_field_ids)
    rows = db.rows(
        f"""
        SELECT value FROM fields
        WHERE session_id = ? AND id NOT IN ({marks}) AND value IS NOT NULL AND value != ''
        """,
        (session_id, *excluded_field_ids),
    )
    terms = set()
    for row in rows:
        for word in row["value"].split():
            word = word.strip(".,:;()[]{}\"'").casefold()
            if len(word) >= 3:
                terms.add(word)
    return terms


def _leaks(terms: set[str], question: str) -> bool:
    return any(
        re.search(rf"(?<!\w){re.escape(term)}(?!\w)", question, re.IGNORECASE)
        for term in terms
    )


def _load_items(handoff: dict) -> list[dict]:
    items = db.loads(handoff.get("items_json"))
    if items:
        return items
    return [{"field_id": json.loads(handoff["field_ids_json"])[0], "question": handoff["question"]}]


def create_handoff(session_id: str, items: list[dict]):
    """Prepare a preview of up to MAX_QUESTIONS questions for one helper."""
    if not items:
        raise HandoffError("Choose at least one question to send.")
    if len(items) > MAX_QUESTIONS:
        raise HandoffError(f"Send at most {MAX_QUESTIONS} questions at a time.")
    field_ids = [item["field_id"] for item in items]
    if len(set(field_ids)) != len(field_ids):
        raise HandoffError("Each question can only be sent once.")

    prepared = []
    for item in items:
        field = db.row(
            "SELECT id, label, plain_label, status FROM fields WHERE id = ? AND session_id = ?",
            (item["field_id"], session_id),
        )
        if not field:
            raise HandoffError("That question is not part of this renewal.", 404)
        if field["status"] == "done":
            raise HandoffError(f"'{field['label']}' is already answered.", 409)
        question = (item.get("question") or field["plain_label"] or field["label"]).strip()
        if not question or len(question) > MAX_QUESTION_LENGTH:
            raise HandoffError(f"Use a helper question between 1 and {MAX_QUESTION_LENGTH} characters.")
        prepared.append({"field_id": field["id"], "question": question})

    terms = _sensitive_terms(session_id, field_ids)
    for item in prepared:
        item["leak"] = _leaks(terms, item["question"])

    db.execute(
        "UPDATE handoffs SET status = 'cancelled' WHERE session_id = ? AND status = 'draft'",
        (session_id,),
    )
    now = time.time()
    handoff_id = db.execute(
        """
        INSERT INTO handoffs(
            session_id, field_ids_json, question, items_json, include_crop,
            redactions_json, status, created_at, expires_at
        ) VALUES (?, ?, ?, ?, 0, '[]', 'draft', ?, ?)
        """,
        (
            session_id,
            json.dumps(field_ids),
            prepared[0]["question"],
            json.dumps([{"field_id": i["field_id"], "question": i["question"]} for i in prepared]),
            now,
            now + HANDOFF_TTL_SECONDS,
        ),
    )
    total_fields = db.row("SELECT COUNT(*) AS count FROM fields WHERE session_id = ?", (session_id,))["count"]
    documents = db.row(
        "SELECT COUNT(*) AS count, COALESCE(SUM(pages), 0) AS pages FROM documents WHERE session_id = ?",
        (session_id,),
    )
    return {
        "id": handoff_id,
        "items": prepared,
        "leak_detected": any(item["leak"] for item in prepared),
        "crop": None,
        "stays_with_you": {
            "other_questions": total_fields - len(prepared),
            "documents": documents["count"],
            "pages": documents["pages"],
        },
        "expires_in_hours": 24,
    }


def send_handoff(session_id: str, handoff_id: int):
    handoff = db.row(
        """
        SELECT id, question, status, field_ids_json, items_json FROM handoffs
        WHERE id = ? AND session_id = ?
        """,
        (handoff_id, session_id),
    )
    if not handoff:
        raise HandoffError("This helper request was not found.", 404)
    if handoff["status"] != "draft":
        raise HandoffError("This helper request has already been sent or closed.", 409)
    items = _load_items(handoff)
    terms = _sensitive_terms(session_id, [item["field_id"] for item in items])
    if any(_leaks(terms, item["question"]) for item in items):
        raise HandoffError(
            "A question may reveal a private answer. Edit it before sending.",
            422,
        )
    active = db.row(
        "SELECT id FROM handoffs WHERE session_id = ? AND status IN ('sent', 'answered')",
        (session_id,),
    )
    if active:
        raise HandoffError(
            "A helper request is already open. Cancel it or review its answers first.", 409
        )
    token = secrets.token_urlsafe(24)
    expires_at = time.time() + HANDOFF_TTL_SECONDS
    with db.connect() as connection:
        cursor = connection.execute(
            """
            UPDATE handoffs SET token = ?, status = 'sent', created_at = ?, expires_at = ?
            WHERE id = ? AND session_id = ? AND status = 'draft'
            """,
            (token, time.time(), expires_at, handoff_id, session_id),
        )
    if cursor.rowcount != 1:
        raise HandoffError("This helper request has already been sent or closed.", 409)
    return {"url": f"/h/{token}", "expires_at": expires_at}


def _open_handoff(token: str):
    handoff = db.row(
        "SELECT id, question, field_ids_json, items_json, status, expires_at FROM handoffs WHERE token = ?",
        (token,),
    )
    if not handoff:
        raise HandoffError("This link no longer works.", 404)
    if (
        handoff["status"] != "sent"
        or handoff["expires_at"] is None
        or handoff["expires_at"] <= time.time()
    ):
        raise HandoffError("This link no longer works.", 410)
    return handoff


def public_packet(token: str):
    """What the helper may see: numbered questions and nothing else."""
    handoff = _open_handoff(token)
    return {
        "questions": [
            {"number": number, "question": item["question"]}
            for number, item in enumerate(_load_items(handoff), start=1)
        ],
        "crop": None,
    }


def answer_handoff(token: str, answers: dict[int, str]):
    handoff = _open_handoff(token)
    count = len(_load_items(handoff))
    cleaned = {}
    for number, text in answers.items():
        if not 1 <= number <= count:
            raise HandoffError("That question is not part of this request.")
        text = text.strip()
        if len(text) > MAX_ANSWER_LENGTH:
            raise HandoffError(f"Keep each answer under {MAX_ANSWER_LENGTH:,} characters.")
        if text:
            cleaned[number] = text
    if not cleaned:
        raise HandoffError("Answer at least one question before sending.")
    with db.connect() as connection:
        cursor = connection.execute(
            """
            UPDATE handoffs
            SET status = 'answered', answer_json = ?, answered_at = ?
            WHERE id = ? AND status = 'sent' AND expires_at > ?
            """,
            (
                json.dumps({"answers": {str(k): v for k, v in cleaned.items()}}, ensure_ascii=False),
                time.time(),
                handoff["id"],
                time.time(),
            ),
        )
        if cursor.rowcount != 1:
            raise HandoffError("This link no longer works.", 410)
    return {"message": "Your answers were sent to the person who asked for help."}


def handoff_summary(handoff: dict) -> dict:
    """The person's own view of a request: each question with its answer, if any."""
    answers = (db.loads(handoff["answer_json"], {}) or {}).get("answers", {})
    return {
        "id": handoff["id"],
        "status": handoff["status"],
        "url": f"/h/{handoff['token']}" if handoff["token"] else None,
        "expires_at": handoff["expires_at"],
        "items": [
            {"question": item["question"], "answer": answers.get(str(number))}
            for number, item in enumerate(_load_items(handoff), start=1)
        ],
    }


def decide_handoff(session_id: str, handoff_id: int, approve: bool):
    handoff = db.row(
        """
        SELECT id, field_ids_json, question, items_json, status, answer_json FROM handoffs
        WHERE id = ? AND session_id = ?
        """,
        (handoff_id, session_id),
    )
    if not handoff:
        raise HandoffError("This helper request was not found.", 404)
    if handoff["status"] != "answered":
        raise HandoffError("There is no new helper answer to review.", 409)
    applied = 0
    if approve:
        answers = db.loads(handoff["answer_json"], {})["answers"]
        for number, item in enumerate(_load_items(handoff), start=1):
            answer = answers.get(str(number))
            if not answer:
                continue
            db.execute(
                """
                UPDATE fields SET value = ?, origin = 'helper', status = 'done', evidence_json = NULL
                WHERE id = ? AND session_id = ?
                """,
                (answer, item["field_id"], session_id),
            )
            applied += 1
    status = "approved" if approve else "rejected"
    db.execute(
        "UPDATE handoffs SET status = ? WHERE id = ? AND session_id = ?",
        (status, handoff_id, session_id),
    )
    return {"status": status, "applied": applied}


def cancel_handoff(session_id: str, handoff_id: int):
    with db.connect() as connection:
        cursor = connection.execute(
            """
            UPDATE handoffs SET status = 'cancelled'
            WHERE id = ? AND session_id = ? AND status IN ('draft', 'sent')
            """,
            (handoff_id, session_id),
        )
    if cursor.rowcount != 1:
        raise HandoffError(
            "This request can no longer be cancelled because it was answered or closed.",
            409,
        )
    return {"status": "cancelled"}
