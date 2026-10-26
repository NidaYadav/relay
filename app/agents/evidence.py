import json
from pathlib import Path

import pymupdf

from app.agents.llm import structured_pdfs

FINDINGS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["findings"],
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "field_key",
                    "value",
                    "document",
                    "page",
                    "quote",
                    "confidence",
                    "read_from_image",
                ],
                "properties": {
                    "field_key": {"type": "string"},
                    "value": {"type": "string"},
                    "document": {"type": "string"},
                    "page": {"type": "integer"},
                    "quote": {"type": "string"},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    "read_from_image": {"type": "boolean"},
                },
            },
        }
    },
}


def _normalise(text: str) -> str:
    return " ".join(text.split()).casefold()


def _squash(text: str) -> str:
    return "".join(character for character in text.casefold() if character.isalnum())


def value_supported(value: str, quote: str) -> bool:
    """The answer must actually appear in the words the model says it read."""
    return bool(_squash(value)) and _squash(value) in _squash(quote)


def check_source(path: Path, page_number: int, quote: str) -> dict:
    """Find the quote in the document's own text; never trust the model's word for it."""
    wanted = _normalise(quote)
    with pymupdf.open(path) as document:
        title = ((document.metadata or {}).get("title") or "").strip() or path.stem.replace("_", " ")
        texts = [page.get_text("text") for page in document]
        scanned = not any(text.strip() for text in texts)
        order = list(range(len(document)))
        if 1 <= page_number <= len(document):
            order.remove(page_number - 1)
            order.insert(0, page_number - 1)
        if wanted and not scanned:
            for index in order:
                if wanted in _normalise(texts[index]):
                    rects = document[index].search_for(quote)
                    return {
                        "verified": True,
                        "page": index + 1,
                        "rect": [round(value, 2) for value in rects[0]] if rects else None,
                        "scanned": False,
                        "title": title,
                    }
    return {
        "verified": False,
        "page": page_number if page_number >= 1 else 1,
        "rect": None,
        "scanned": scanned,
        "title": title,
    }


def extract_evidence(documents: list[dict], fields: list[dict]) -> dict[str, dict]:
    """Return {field_key: {"value": ..., "evidence": {...}}} for answers found in the vault."""
    askable = {field["key"]: field for field in fields if field["source"] != "helper"}
    if not documents or not askable:
        return {}
    by_name = {document["filename"]: document for document in documents}
    questions = [
        {"key": key, "question": field["label"], "type": field["answer_type"]}
        for key, field in askable.items()
    ]
    prompt = (
        "These are the person's saved documents: "
        f"{', '.join(by_name)}.\n"
        "For each question below, return a finding only when a document explicitly states "
        "the answer. Copy a short verbatim quote from the document page that contains the "
        "answer, give the 1-based page number, and use the document filename exactly as "
        "listed. Write the value exactly as the document shows it, keeping currency "
        "codes, symbols and units, except write dates as "
        "'D Month YYYY'. Do not guess, combine facts to infer an answer, or decide "
        "eligibility. Omit any question the documents do not answer.\n"
        f"Questions (JSON): {json.dumps(questions)}"
    )
    result = structured_pdfs(
        "You find answers to form questions in a person's saved documents and cite your "
        "sources exactly.",
        prompt,
        [Path(document["path"]) for document in documents],
        FINDINGS_SCHEMA,
        "relay_evidence",
    )
    found: dict[str, dict] = {}
    for item in result["findings"]:
        key = item["field_key"]
        document = by_name.get(item["document"])
        value = item["value"].strip()
        if key not in askable or key in found or document is None or not value:
            continue
        supported = value_supported(value, item["quote"])
        if not supported and askable[key]["answer_type"] != "date":
            continue
        source = check_source(Path(document["path"]), item["page"], item["quote"])
        found[key] = {
            "value": value,
            "evidence": {
                "document": document["filename"],
                "title": source["title"],
                "page": source["page"],
                "quote": item["quote"],
                "confidence": item["confidence"],
                "verified": source["verified"] and supported,
                "read_from_image": bool(item["read_from_image"] or source["scanned"]),
                "rect": source["rect"],
            },
        }
    return found
