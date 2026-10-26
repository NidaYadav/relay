---
doc: spec
status: approved
---

# Relay — Technical Spec

## How This Works, In Plain Language
Relay is a small Python web server with a plain HTML/JS front end. A local SQLite file is its notebook.

When you upload papers, the server passes them along a line of **agents**. Each agent is a short piece of code with one job, and it writes what it did to a work log you can watch:

1. **Intake** opens the form and each document in the **vault** (a folder of the person's PDFs) and identifies fillable fields, text pages, and scanned pages. It pulls out text and page images where needed.
2. **Mapper** reads the form and writes a *task model*: task name, deadline, parts and questions. For each question it records whether the answer comes from you, your papers, or another person.
3. **Evidence** searches your supporting papers for answers. It keeps the exact words and page for each one, and the code checks that those words really appear in the document.
4. **Guide** serves questions one at a time and checks answers: required fields, dates, numbers.
5. **Relay** builds the helper packet for a blocked step. It crops the one relevant spot on one page and blacks out any of your other answers that show up in that crop. It checks the question text for leaks, then makes a one-time link.
6. **Assembler** writes the completed PDF, with a record of who answered what.

Mapper and Evidence always use the OpenAI API. A valid server-side `OPENAI_API_KEY`, a configured `RELAY_MODEL`, and network access are required for document processing, including the sample demo. Intake, Guide, Relay and Assembler are plain code. The server enforces the helper boundary; it does not rely on a prompt.

Why this shape: one process, one file database, no build step. AI handles document interpretation and evidence extraction; deterministic code handles validation, disclosure boundaries and PDF assembly.

## The Core Journey Through the System
PRD ref: `prd.md > The Core Journey`.
0. Vault → `GET /api/vault` lists the person's vault and the demo vault. `POST /api/vault/documents` saves one or more PDFs (each checked for type, size, readability and password protection, with a per-file result), replacing a file with the same name. `DELETE /api/vault/documents/{id}` removes one. `GET /vault` serves the vault page.
1. Start → `POST /api/sessions` saves the form and a copy of the vault PDFs to `data/uploads/<session>/` and adds rows to `documents` (`role` form or evidence). A background thread starts the pipeline.
2. Intake → Mapper → Evidence each write `events` rows. The browser polls `GET /api/sessions/{id}` and renders the work log.
3. Task brief → the same endpoint returns `sessions.task_json` and the `fields` rows.
4. Guided answers → `POST /api/sessions/{id}/fields/{fid}`. Guide validates the answer and stores `value`, `origin=user`, `status=done`.
5. Blocked step → `POST /api/sessions/{id}/handoffs`. Relay builds the packet (question, crop PNG, redaction list, leak check) and returns a preview. `POST …/handoffs/{hid}/send` creates the token and its expiry.
6. Helper → `GET /h/{token}` serves `helper.html`. `GET /api/h/{token}` returns **only** the packet. `POST /api/h/{token}` stores the answer and closes the token.
7. Review → `POST …/handoffs/{hid}/decision` approves or rejects. Approval writes `origin=helper`.
8. Export → `GET /api/sessions/{id}/export.pdf` (Assembler). Forget → `DELETE /api/sessions/{id}`.

## Stack
- **Python 3.11+** with **FastAPI** (https://fastapi.tiangolo.com) and **uvicorn**: small, typed, and serves both the API and the static files.
- **PyMuPDF** (https://pymupdf.readthedocs.io): reads PDFs, fillable fields and images; renders crops; draws redactions; fills fields; writes the export. One library covers every PDF job.
- **sqlite3** (Python standard library): the local store the learner asked for.
- **openai** Python SDK (https://platform.openai.com/docs): uses the Responses API with a model configured through `RELAY_MODEL` that supports PDF/image inputs and structured outputs. Agents request JSON-schema-constrained responses and validate the returned data. API refusals and incomplete responses are reported explicitly, not replaced with fabricated or pattern-matched results.
- **Front end:** hand-written HTML, CSS and vanilla JS modules. No framework and no build step, so the design is ours, not a component kit's defaults.

## Where It Runs and How Someone Tries It
Local:
```
pip install -r requirements.txt
python -m app.samples          # writes the synthetic form to docs/ and the demo vault to docs/vault/
python -m uvicorn app.main:app --port 8000 --no-access-log
```
Before starting the server, copy `.env.example` to `.env` and set `OPENAI_API_KEY` and `RELAY_MODEL`, or set both in the server environment. Never put the key in browser code or commit it. Missing configuration stops startup with a clear configuration error. Open http://localhost:8000 after startup succeeds. Every document-processing run, including the sample, uses the API; there is no offline or pattern-matching mode.
The vault is a set of PDFs. The person's own vault is stored in the SQLite database (`vault_documents`), managed on the vault page at `/vault`; the synthetic demo vault is the folder `docs/vault/`. "Try the sample renewal" uses the demo form and demo vault; choosing a form uses the person's vault. Each run copies the vault PDFs into the session so the pipeline reads a stable snapshot. The vault holds at most 20 documents, 20 MB each and 100 MB in total.
Access logs are disabled so one-time helper tokens are not written to the server log. For the demo video: run locally and open the helper link in a second browser window side by side. Deployment is optional and not planned.

## Look and Feel
Implements `prd.md > Look and Feel`.
- **Tokens on `:root`:**
  - paper `#F5F0E6`
  - ink `#1C1A17`
  - rule `#D8CDB8`
  - muted `#5E574C`
  - go green `#1E5B40`
  - relay vermilion `#B3401D`
  - focus `#1B4FD8`, as a 3px outline with offset
- **Modes:** high-contrast is black on white with a yellow focus ring and underlined links. Reduced-motion removes all transitions. Text size steps between 100%, 115% and 130%.
- **Fonts:** Atkinson Hyperlegible for body text and Source Serif 4 for headings, loaded from Google Fonts, with system fallbacks.
- **Layout:** a single 44rem reading column. Each part looks like a paper form: letter badge, title, hairline rule. Buttons are at least 48px tall and always have a text label.
- **Copy:** second person, short sentences, no exclamation marks, no "AI magic" language.

## Agents
Each agent lives in `app/agents/`. It takes the session id, reads and writes the database, and logs to `events` through `AgentContext.log()`.

### Intake agent
`app/agents/intake.py`. Accepts PDF forms and supporting PDFs. It collects the text per page, fillable field names, labels and rectangles, and whether each page is image-only (a scan). It stores `kind`, `pages` and `text`.
PRD ref: `prd.md > Reading documents`.

### Mapper agent
`app/agents/mapper.py`.
- **API processing:** sends the PDF form and list of fillable field names to OpenAI. It gets back a task model through a JSON schema: task, issuer, deadline + deadline_quote, summary, sections → fields, and evidence_required[]. Each field carries key, label, plain_label, help, required, answer_type, options, answer_source ∈ {person, documents, helper}, helper_reason and pdf_field.
- **Code check:** if the deadline_quote isn't found in the form text, the deadline is dropped along with it.
- **API failure:** records the failure and stops processing with an actionable error and retry. No local parser substitutes for the model's task interpretation.

PRD ref: `prd.md > Task brief`.

### Evidence agent
`app/agents/evidence.py`.
- **API processing:** sends the supporting PDFs plus the questions to OpenAI. Each finding comes back with field_key, value, quote, doc_index, page, confidence, read_from_image, and a normalised bbox for image regions.
- **Code check:** for documents with a text layer, the quote must be found on the page with `page.search_for`, which also gives the exact rectangle. If the quote can't be found, confidence drops and the finding is marked "unverified".
- **API failure:** records the failure and stops processing with an actionable error and retry. Evidence is never replaced with label or synonym pattern matching.
- **Value check:** an answer is kept only if its value appears in the quote the model gave (dates are the exception, because the model reformats them). This stops invented values such as a household size read from an unrelated note.
- **Synthetic sample target:** the 14-question sample includes matching text evidence for 10 fields (over 70%). Store verified findings as proposed answers with their source and page; the person reviews them before they enter the completed PDF.

For fields that mention a stamp, seal, photo or handwriting, the helper crop is pointed at the nearest image region on the evidence page.
PRD ref: `prd.md > Guided questions`.

### Guide agent
`app/agents/guide.py`. Deterministic validation: required answers, dates (several formats, normalised and displayed clearly), numbers, yes/no. No AI is needed here, because Mapper already supplies the plain wording.
PRD ref: `prd.md > Guided questions`.

### Relay agent
`app/agents/relay.py`. This is the kernel.
- `build_packet` becomes `create_handoff(session_id, items)`: each item is a question id plus editable wording (from plain_label), up to ten per request. The optional crop of the evidence rectangle (padded, rendered at 3x) is added with guided answering.
- **One open request:** a person has at most one sent or answered request at a time; a new preview replaces any unsent draft.
- **Answers:** the helper submits `{number, answer}` pairs; blank answers are ignored and at least one is required. Approval writes each non-empty answer to its own field (`origin=helper`, `status=done`).
- **Redaction:** the person's other answers and found values are split into sensitive terms. Any word in the crop's text layer that matches one (`page.get_text("words", clip=…)`) is painted over in black on the rendered crop.
- **Leak check:** flags any sensitive term that appears in the question text.
- **"Stays with you" counts:** other questions, documents and pages.
- **Tokens:** `secrets.token_urlsafe(24)`, with an expiry, single use. Only `GET/POST /api/h/{token}` can read or answer, and they expose nothing but the packet fields.

PRD ref: `prd.md > Minimum-disclosure handoff (the kernel)`.

### Assembler agent
`app/agents/assembler.py`. It sets the form's fillable widget values by `pdf_field`, then appends "Questions and answers" pages listing every question with its answer and where the answer came from (you, your vault with document and page, or your helper), marking answers "not yet reviewed" until the person confirms them and listing unanswered questions as "Not answered". A form without fillable fields keeps its original pages and gets the same questions-and-answers pages. The built-in PDF fonts cover Latin-1 only, so other characters print as "?" in the exported pages.
PRD ref: `prd.md > Completion`.

### Orchestrator
`app/agents/orchestrator.py`. Runs Intake → Mapper → Evidence in a background thread. It sets `sessions.status` (reading → ready or failed) and records failures in the log.

### LLM wrapper
`app/agents/llm.py`. Startup validates that `OPENAI_API_KEY` and `RELAY_MODEL` are configured. `structured(system, content, schema)` calls the OpenAI Responses API with JSON-schema structured outputs, validates the result, and returns parsed data or raises `LLMError`. Authentication errors, rate limits, network failures, refusals, incomplete responses and invalid output are surfaced explicitly. Errors are logged without credentials or document contents. There is no local-result fallback.

## Components (web)
- `web/index.html` + `web/app.js`: the screens are sections toggled by state. Status and progress use `aria-live`, and focus moves to each new screen's heading.
- `web/vault.html` + `web/vault.js`: the vault page, with a drop zone, per-file results, the saved list and delete.
- `web/helper.html` + `web/helper.js`: the helper page.
- `web/styles.css`: tokens, the form-paper layout and the settings modes.

## Data Model
SQLite at `data/relay.db`.
- `sessions(id, created_at, status, mode, task_json, error)`; `mode` is always `ai`.
- `documents(id, session_id, role[form|evidence], filename, kind, pages, text, path, meta_json)`
- `vault_documents(id, filename unique and case-insensitive, title, kind, pages, size, content BLOB, added_at)`: the person's own vault. It is not tied to a session, so forgetting or purging a session never removes it.
- `fields(id, session_id, ord, section, key, label, plain_label, help, required, answer_type, options_json, source[person|documents|helper], helper_reason, pdf_field, value, origin[user|documents|helper], status[open|proposed|done|skipped|needs_helper|waiting], evidence_json)`
- `handoffs(id, session_id, field_ids_json, question, crop_path, redactions_json, include_crop, token, status[draft|sent|answered|approved|rejected|cancelled], answer_json, created_at, expires_at, answered_at)`
- `events(id, session_id, at, agent, message, level)`

Sessions older than 7 days are deleted at start-up. `DELETE /api/sessions/{id}` removes the rows and files.

## File Structure
```
relay/
├── app/
│   ├── main.py            # FastAPI routes, static files, helper boundary
│   ├── db.py              # SQLite schema and helpers
│   ├── samples.py         # generates the synthetic demo form and demo vault
│   ├── vault.py           # the database vault (save, list, delete) and the demo vault folder
│   └── agents/
│       ├── context.py     # AgentContext: db access + work log
│       ├── llm.py         # OpenAI wrapper (structured outputs)
│       ├── intake.py
│       ├── mapper.py
│       ├── evidence.py
│       ├── guide.py
│       ├── relay.py
│       ├── assembler.py
│       └── orchestrator.py
├── web/                   # index.html, vault.html, helper.html, styles.css, app.js, handoff.js, vault.js, helper.js
├── docs/                  # generated synthetic demo form (committed)
│   └── vault/             # generated synthetic demo vault PDFs (committed)
├── data/                  # SQLite database (including the person's vault) and session uploads (git-ignored)
├── tests/test_flow.py     # end-to-end check through the HTTP API
├── devpost/               # scope, prd, spec, checklist, app map
├── requirements.txt  .env.example  README.md  LICENSE
```

## External Services and Dependencies
- **OpenAI Responses API:** `POST /v1/responses` through the Python SDK, with the server-side key from `OPENAI_API_KEY` and model from `RELAY_MODEL`. Required for document processing. Paid per token: one Mapper call and one Evidence call per session with supporting documents.
- **Google Fonts:** fonts only, with system fonts if the font service is unavailable. This does not change the API requirement.

## Important Failure Modes
- **The model returns a value that isn't in the document** → the quote check fails. The answer is shown as "unverified — please check" and is never confirmed automatically.
- **Missing API configuration** → startup fails with instructions to set `OPENAI_API_KEY` and `RELAY_MODEL`.
- **Invalid API key, API outage, rate limit or refused request** → processing fails visibly in the work log with an actionable error and retry. No substitute results are generated.
- **The helper opens an expired or used link** → a specific message, and the API returns nothing else.

## What Was Simplified and Why
- **A copied link** instead of SMS or email delivery. It proves the boundary without adding messaging providers.
- **Polling** instead of websockets. Simpler, and fast enough for a work log.
- **Token-only helper access** instead of accounts. It proves minimum disclosure; a real deployment would add identity.
- **Deterministic validation** instead of an AI answer checker. It's predictable, and dates are read back in words.

## Decisions and Open Issues
- **Agents vs. the brief's "don't over-engineer agents".** The learner asked for an agent-based system. The resolution is six narrow agents with a visible log. Only two use a model, and the privacy boundary lives in code. The agents run as a fixed pipeline, not a free-roaming loop, so the demo is predictable. (That last point is an implementation detail, not the learner's choice.)
- **PDF-only proof.** The approved scope focuses the demo on a generated PDF form and supporting PDFs; other document types, voice input and read-aloud are deferred.
- **SQLite.** The learner's choice. It conflicts slightly with the brief's "no persistent PII", so the build adds a 7-day purge and a forget button.
- **Uncertainty to check during the build:** confirm that the configured OpenAI model supports PDF/image inputs and JSON-schema structured outputs together. Verify a real API run with synthetic documents before declaring the flow complete.
