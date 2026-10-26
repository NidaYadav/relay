from pathlib import Path

import pymupdf as fitz


def classify(result: dict) -> str:
    if result["field_names"]:
        return "fillable PDF"
    if any(page["scanned"] for page in result["page_details"]):
        return "PDF with scanned pages"
    return "text PDF"


def _inspect(document) -> dict:
    if document.needs_pass:
        raise ValueError("This PDF is password-protected. Remove the password and try again.")
    pages = []
    field_names = []
    for index, page in enumerate(document):
        text = page.get_text("text").strip()
        pages.append(
            {
                "number": index + 1,
                "text": text,
                "scanned": not bool(text),
            }
        )
        for widget in page.widgets() or ():
            if widget.field_name:
                field_names.append(widget.field_name)

    return {
        "pages": len(document),
        "text": "\n".join(page["text"] for page in pages),
        "page_details": pages,
        "field_names": field_names,
        "title": ((document.metadata or {}).get("title") or "").strip(),
    }


def inspect_pdf(path: Path):
    try:
        document = fitz.open(path)
    except (fitz.FileDataError, RuntimeError) as exc:
        raise ValueError("This PDF could not be opened. Try another PDF file.") from exc
    with document:
        return _inspect(document)


def inspect_pdf_bytes(content: bytes):
    try:
        document = fitz.open(stream=content, filetype="pdf")
    except (fitz.FileDataError, RuntimeError) as exc:
        raise ValueError("This PDF could not be opened. Try another PDF file.") from exc
    with document:
        if len(document) == 0:
            raise ValueError("This PDF has no pages.")
        return _inspect(document)
