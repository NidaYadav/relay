import base64
import json
import os
from pathlib import Path

from openai import APIConnectionError, APIStatusError, OpenAI, OpenAIError
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


class LLMError(RuntimeError):
    pass


def validate_config():
    missing = [
        name
        for name in ("OPENAI_API_KEY", "RELAY_MODEL")
        if not os.environ.get(name, "").strip()
    ]
    if missing:
        joined = " and ".join(missing)
        raise RuntimeError(
            f"Relay cannot start: {joined} { 'is' if len(missing) == 1 else 'are' } "
            "not configured. Set them in the server environment, then restart."
        )


def structured_pdf(system: str, prompt: str, path: Path, schema: dict, name: str):
    return structured_pdfs(system, prompt, [path], schema, name)


def _pdf_part(path: Path):
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return {
        "type": "input_file",
        "filename": path.name,
        "file_data": f"data:application/pdf;base64,{encoded}",
    }


def structured_pdfs(system: str, prompt: str, paths: list[Path], schema: dict, name: str):
    validate_config()
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    file_parts = [_pdf_part(path) for path in paths]
    try:
        response = client.responses.create(
            model=os.environ["RELAY_MODEL"],
            input=[
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system}],
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        *file_parts,
                    ],
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": name,
                    "schema": schema,
                    "strict": True,
                }
            },
        )
    except APIStatusError as exc:
        if exc.status_code == 401:
            raise LLMError(
                "OpenAI rejected the API key. Check OPENAI_API_KEY on the server."
            ) from exc
        if exc.status_code == 429:
            raise LLMError(
                "OpenAI rate limit or quota reached. Check the account and retry."
            ) from exc
        raise LLMError(
            f"OpenAI returned an API error (HTTP {exc.status_code}). Retry later."
        ) from exc
    except APIConnectionError as exc:
        raise LLMError(
            "Relay could not reach OpenAI. Check network access and retry."
        ) from exc
    except OpenAIError as exc:
        raise LLMError(
            "OpenAI could not process this PDF. Check the model configuration and retry."
        ) from exc

    if response.status != "completed":
        raise LLMError(
            f"OpenAI did not complete document analysis ({response.status}). Retry."
        )
    output = response.output_text
    if not output:
        raise LLMError(
            "OpenAI returned no structured result for this PDF. Retry or check the model."
        )
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise LLMError(
            "OpenAI returned an invalid structured result. Retry the document."
        ) from exc
