# Relay

### Paperwork help, without handing over your whole life.

**Relay turns complex PDF paperwork into an evidence-backed workflow.** It searches your supporting documents for candidate answers, checks the cited text, and lets you ask a trusted person only the questions you choose to share.

**[Watch the demo video](https://youtu.be/cuOA2zzSv-E)** | [Try it locally](#run-locally) | [Planning evidence](#built-with-the-devpost-learn-skill-pack)

![Relay application overview](https://ik.imagekit.io/jroc4gnvp/devpost_hack/relay/1.png)

## The problem

A public-benefit renewal, banking form or agency application can become a maze of dense PDFs, unfamiliar language and supporting paperwork. For people with low vision, limited dexterity, cognitive overload or low digital confidence, working through the form can be especially difficult.

Asking for help creates another problem: handing over identity documents, bank statements and private letters just to answer one tricky question.

**Relay makes help more granular.** Find evidence in your own documents, inspect the sources, and delegate selected questions rather than the entire document bundle. These intended-user needs motivate the design; accessibility validation and research with target users remain future work.

## The experience, end to end

1. **Add supporting PDFs.** Upload documents into a SQLite-backed vault.
2. **Map the form.** Relay reads the PDF and organizes its questions into sections.
3. **Find candidate answers.** AI searches the vault and proposes an answer, source quote and page reference.
4. **Check the evidence.** Python checks the quote against extracted PDF text and whether non-date answer values appear in the quote. Unsupported non-date values are discarded; unverified quotes and scans are flagged for checking.
5. **Ask for help selectively.** Choose up to ten unresolved questions and preview a single-use link that expires after 24 hours. The helper sees those questions, not the vault or the rest of the form.
6. **Approve helper replies, then export.** Accept or reject the reply, then download the PDF with matching fillable fields populated and appended question/answer/source pages. Vault proposals are included as **not yet reviewed**.

![Relay workflow](https://ik.imagekit.io/jroc4gnvp/devpost_hack/relay/2.png)

## What makes Relay different

- **Evidence, not just generated text:** candidate answers include source quotations and page references.
- **Checks beyond the model:** ordinary Python checks the source text independently instead of trusting a citation at face value.
- **Minimum-disclosure assistance:** the helper endpoint returns a reduced packet containing selected questions rather than the whole session.
- **Human approval for helper replies:** a helper's response does not silently become an accepted answer.
- **A connected workflow:** document storage, form mapping, evidence inspection, targeted help and PDF export work together.

These checks reduce specific risks; they do not guarantee answer accuracy, confidentiality or production readiness.

![Relay interface](https://ik.imagekit.io/jroc4gnvp/devpost_hack/relay/7.png)

## Built with the Devpost Learn Skill Pack

Relay used the Devpost Learn Skill Pack to define the problem, approve a scope and technical plan, and build a small proof of concept in usable slices. The guiding principle was to prove one useful workflow rather than expand into an unfinished accessibility platform.

The [Devpost folder](devpost/) preserves the project's planning decisions and build progress:

| Artifact | Purpose |
|---|---|
| [Approved scope](devpost/scope.md) | Intended user, problem, unique kernel and proof-of-concept boundary |
| [Approved PRD](devpost/prd.md) | Core journey, expected behavior and acceptance criteria |
| [Approved technical spec](devpost/spec.md) | Architecture, components, storage and technical decisions |
| [Build checklist and revisions](devpost/checklist.md) | Implemented slices, verification requirements and user-directed changes |

These documents include planned behavior as well as completed work. Guided answering, document-crop sharing and reading settings remain unfinished; final hands-on review, learning wrap-up and app-map generation are not marked complete. The implementation and limitations below describe what works today. Historical references to slices, commits or paths record the original build context and may not all exist in this clean snapshot.

The personal learner profile is intentionally excluded from the public repository. This is evidence of planning and implementation, not a claim that every stage from `1-start` through `6-ship` is complete.

### Decisions that became working behavior

- **Keep help bounded:** the scope's minimum-disclosure goal became a question-only helper packet, token expiry and explicit approval. [Handoff tests](tests/test_handoff.py) check these boundaries and separate answer mapping.
- **Verify high-stakes suggestions in code:** an early live run inferred a household size from an unrelated note. [Evidence checks](app/agents/evidence.py) now require non-date values to appear in their quoted evidence; [tests](tests/test_evidence.py) cover unsupported values and fabricated quotations.
- **Make the vault usable from the browser:** user feedback replaced a manually managed folder with upload, replacement and deletion in a database-backed page. [Vault tests](tests/test_vault.py) also check that the personal and synthetic demo vaults stay separate.

## What works

- Upload, list, replace and delete PDF documents in a SQLite-backed vault.
- Upload a form and see extracted questions, proposed answers, source quotations and page references.
- Send up to ten selected questions through a single-use helper link that expires after 24 hours. Each question has a separate answer box; replies require your approval.
- Download a PDF with matching form widgets populated and appended question/answer/source pages.
- Try a fictional renewal form and synthetic vault independently of your personal vault.

Form interpretation and evidence extraction use the OpenAI API, including the sample. There is no offline fallback. API access costs money and requires network connectivity.

The prototype has been exercised on a fictional 14-question renewal form with four synthetic supporting PDFs. AI output varies; the sample is not an accuracy benchmark or evidence of real-user testing.

![Relay prototype](https://ik.imagekit.io/jroc4gnvp/devpost_hack/relay/6.png)

## Run locally

Requirements: Python 3.11+, Git, and an OpenAI API account with a model supporting PDF input and structured outputs.

From Windows PowerShell:

```powershell
git clone https://github.com/NidaYadav/relay.git
cd relay
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `OPENAI_API_KEY` and `RELAY_MODEL` in `.env`. Neither has a default. Never commit API keys.

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Open **http://localhost:8000**. Startup creates a fresh SQLite database automatically. No seed database or migration command is required.

## Run with Docker

Configure `.env` as above, then:

```powershell
docker compose up --build
```

Or:

```powershell
docker build -t relay .
docker run --rm -p 127.0.0.1:8000:8000 --env-file .env -v relay-data:/app/data relay
```

FastAPI serves both the frontend and backend on port **8000**. The Docker image uses Python 3.12 and a non-root user.

| Variable | Purpose | Default |
|---|---|---|
| `OPENAI_API_KEY` | Required server-side API key | None |
| `RELAY_MODEL` | Required PDF-capable model supporting structured outputs | None |
| `RELAY_DATA_DIR` | Database and session PDF storage | Local `data/`; `/app/data` in Docker |

For Render, configure both API variables in the service environment and use port **8000**. Attach a persistent disk at **`/app/data`** to retain documents and sessions across redeploys; the Docker volume declaration alone does not provision a Render disk. Do not publish real documents on this unauthenticated prototype.

## Try it

1. Click **Try the sample renewal** and wait for the work log to finish.
2. Inspect the proposed answers and their sources; output can vary between model runs.
3. Under **Ask a trusted person**, select the witness questions and preview the task.
4. Create a helper link and open it in a second tab. Answer each question in its own box.
5. Return to the original tab, approve the reply and download the questions and answers PDF.

To use your own safe test documents, open **Your vault**, upload PDFs, return home and choose a PDF form. A localhost helper link only works on the same computer unless you configure reachable hosting.

The committed PDFs in [docs/](docs/) are synthetic runtime demo fixtures, not development reference images. They are generated by [app/samples.py](app/samples.py). To regenerate:

```powershell
.\.venv\Scripts\python.exe -m app.samples
```

## How it was built

The plain HTML/CSS/JavaScript frontend calls FastAPI. PyMuPDF inspects and exports PDFs; OpenAI interprets forms and proposes cited answers; SQLite stores vault documents and session state. Session PDF copies are stored under the data directory.

| Component | Implementation |
|---|---|
| API and session workflow | FastAPI and Uvicorn; Python 3.11+ locally, 3.12 in Docker |
| PDF processing | PyMuPDF for inspection, text extraction, widget population and export |
| Form mapping and evidence extraction | OpenAI Responses API with JSON-schema-constrained output |
| Grounding checks | Normalized quote matching against document text and answer-in-quote checks |
| Persistence | SQLite plus session-level PDF snapshots |
| Interface | HTML, CSS and vanilla JavaScript; no frontend build step |

```text
Browser -> FastAPI -> Intake -> Mapper -> Evidence -> Task brief
              |                  |          |
              |                  +-- OpenAI API
              |
              +-- SQLite + session PDF snapshots
              +-- Selected helper questions -> review -> PDF export
```

### Challenges solved

**Unsupported AI answers.** Schema-constrained output alone cannot establish truth. Relay checks citations independently, discards unsupported non-date values and labels unverified evidence rather than treating every model result as a verified fact.

**Over-sharing to get help.** The helper page receives a reduced payload, not the user's whole session. Question wording is also checked for matches with other stored answers, but this heuristic is not a comprehensive privacy guarantee.

**Changing documents mid-session.** New sessions copy the current vault PDFs. Replacing a vault document later does not silently change the evidence used by an in-progress session.

## Limitations and safety

- PDF contents are sent to OpenAI when processing. Local storage does not mean offline processing.
- Source checks look for quoted text and answer values; they do not guarantee correct interpretation. Scans and unverified evidence need particular care.
- Guided editing/confirmation of vault answers and helper document crops/redaction are not implemented. Exported vault proposals remain marked **not yet reviewed**.
- No accounts, main-workspace authorization or encryption-at-rest feature. Anyone who can reach the app can access its workspace. Keep it local or restrict access externally.
- The vault accepts at most 20 PDFs, 20 MB each and 100 MB total. Replacing/deleting a vault document does not remove existing session copies.
- Sessions older than seven days are purged at startup. Forgetting a session removes its records and copied PDFs, not vault documents.
- Non-fillable PDFs receive an answer appendix rather than layout-positioned answers. Export fonts support Latin-1; unsupported characters may become `?`.
- No eligibility decisions, agency submission, production hardening or completed accessibility audit.

## Verification

From the repository root in the configured environment:

```powershell
.\.venv\Scripts\python.exe -m pip install httpx
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m compileall -q app tests
```

**36 automated tests passed** when preparing this application snapshot, covering vault operations, evidence checks, helper-link lifecycles, answer mapping and PDF export. Python compilation also passed.

`httpx` is required by the FastAPI TestClient tests but is not a runtime requirement. Tests use stubbed model responses and temporary storage; they do not establish live model accuracy. No lint or coverage workflow is configured. Docker image build/run has not been verified for this clean snapshot.

## What's next

- **Guided answering:** one-question-at-a-time confirmation and correction, with read-aloud and speech input as later extensions.
- **Safer visual context:** small, redacted crops when a question genuinely needs visual evidence.
- **Accessibility validation:** screen-reader and keyboard-only checks with target users, followed by WCAG-focused improvements.
- **Localization:** support for people navigating forms in another language.

## Project takeaways

- **Plan before prompting:** a clear scope and explicit specification keep AI-assisted development focused.
- **Verify high-stakes outputs in code:** structured responses are not enough; independent checks and explicit user review matter.
- **Design for control:** useful assistance should not require users to surrender their documents or their final say.

## Repository map

- [app/](app/): server, SQLite, vault rules, document agents and sample generator.
- [web/](web/): home, vault and helper screens; no frontend build step.
- [docs/](docs/): synthetic demo PDFs required by the sample flow.
- [tests/](tests/): automated behavior checks.
- [devpost/](devpost/): public hackathon scope, PRD, technical spec and build checklist.
- [Dockerfile](Dockerfile) and [docker-compose.yml](docker-compose.yml): single-service deployment.

Development videos, reference images, private notes, old database contents, skill tooling and previous Git history are not bundled. The screenshots above are linked externally; the runtime demo PDFs remain in the repository.

## License

The existing [MIT license](LICENSE) and copyright attribution are preserved. Dependencies retain their own licenses, including PyMuPDF's distribution terms; no complete third-party licensing audit is claimed.
