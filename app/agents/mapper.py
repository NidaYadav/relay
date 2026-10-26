from pathlib import Path

from app.agents.llm import structured_pdf

TASK_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "task",
        "issuer",
        "deadline",
        "deadline_quote",
        "summary",
        "evidence_required",
        "sections",
    ],
    "properties": {
        "task": {"type": "string"},
        "issuer": {"type": "string"},
        "deadline": {"type": ["string", "null"]},
        "deadline_quote": {"type": ["string", "null"]},
        "summary": {"type": "string"},
        "evidence_required": {"type": "array", "items": {"type": "string"}},
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["title", "fields"],
                "properties": {
                    "title": {"type": "string"},
                    "fields": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": [
                                "key",
                                "label",
                                "plain_label",
                                "help",
                                "required",
                                "answer_type",
                                "options",
                                "answer_source",
                                "helper_reason",
                                "pdf_field",
                            ],
                            "properties": {
                                "key": {"type": "string"},
                                "label": {"type": "string"},
                                "plain_label": {"type": "string"},
                                "help": {"type": "string"},
                                "required": {"type": "boolean"},
                                "answer_type": {
                                    "type": "string",
                                    "enum": ["text", "date", "number", "yes_no"],
                                },
                                "options": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "answer_source": {
                                    "type": "string",
                                    "enum": ["person", "documents", "helper"],
                                },
                                "helper_reason": {"type": ["string", "null"]},
                                "pdf_field": {"type": ["string", "null"]},
                            },
                        },
                    },
                },
            },
        },
    },
}


def map_form(path: Path, extracted_text: str, field_names: list[str]):
    prompt = (
        "Read this synthetic public-service renewal form. Return its task, issuing "
        "organization, exact deadline and a verbatim deadline quote, required "
        "supporting documents, form sections, and every answerable field. Use "
        "answer_source=helper only for a field that explicitly requires another "
        "person. Use answer_source=documents for personal facts that normally appear "
        "in the person's saved identity, address, bank or assessment documents (name, "
        "date of birth, address, reference numbers, dates, income, bank details, "
        "housing costs); use person for choices and counts only the person can state. "
        "Match pdf_field exactly to a "
        "provided fillable field name or null. Do not invent a deadline or fields. "
        f"Fillable PDF fields: {field_names}\n\n"
        f"Extracted form text (may be incomplete for a scan):\n{extracted_text[:24000]}"
    )
    result = structured_pdf(
        "You map PDF forms into a faithful, concise task model. Do not make "
        "eligibility decisions. Preserve dates and quote deadline wording exactly.",
        prompt,
        path,
        TASK_SCHEMA,
        "relay_task",
    )
    quote = result.get("deadline_quote")
    if not quote or quote not in extracted_text:
        result["deadline"] = None
        result["deadline_quote"] = None
    keys = set()
    for section in result["sections"]:
        for field in section["fields"]:
            key = field["key"].strip()
            if not key or key in keys:
                raise ValueError("The form mapping returned missing or duplicate field keys.")
            keys.add(key)
            field["key"] = key
    if not keys:
        raise ValueError("No fillable questions were found in this PDF.")
    return result
