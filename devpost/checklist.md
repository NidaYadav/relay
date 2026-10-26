---
doc: checklist
status: approved
---

# Build Checklist

Build mode: fast

## Slices

- [x] **1. Upload the sample renewal and see a task brief**
  Becomes usable: A running app. "Try the sample renewal" loads the generated PDFs in `docs/`, runs Intake and Mapper, and shows a task brief with deadline source, form parts, and the you / found / needs-a-person split.
  Why now: Proves the PDF sample path end to end first, including app setup and the model/API risk, and establishes the synthetic packet for later slices.
  PRD ref: `prd.md > The Core Journey` (steps 1–4), `prd.md > Reading documents`, `prd.md > Task brief`
  Spec ref: `spec.md > Intake agent`, `spec.md > Mapper agent`, `spec.md > Orchestrator`, `spec.md > Data Model`, `spec.md > File Structure`
  Build: FastAPI app, SQLite schema, generator for the synthetic PDF sample pack in `docs/`, OpenAI wrapper with required configuration and structured outputs, PDF Intake + API-backed Mapper, orchestrator, home + brief screens with polling work log.
  Verify (mechanical): Confirm startup fails clearly when API configuration is missing. With `OPENAI_API_KEY` and `RELAY_MODEL` set, start the server, submit the generated PDF sample, poll until status is ready, and confirm the brief includes a deadline whose quote appears in the form, at least 12 fields, and at least one helper field. Confirm API authentication failure is reported rather than replaced with local results.
  Learner check: Open the app, press "Try the sample renewal", watch the log, and read the brief.
  Commit: `Upload documents and build the task brief`

- [x] **2. Relay one blocked step to a helper and approve the answer**
  Becomes usable: From the brief, the helper step opens the handoff screen: preview of what the helper sees vs. what stays with you, a one-time link, the helper page, and approve/reject.
  Why now: This is the kernel. It has to work before the guided flow is polished around it.
  PRD ref: `prd.md > Minimum-disclosure handoff (the kernel)`, `prd.md > The Core Journey` (steps 6–9)
  Spec ref: `spec.md > Relay agent`, `spec.md > The Core Journey Through the System`
  Build: Relay packet builder, leak check, tokens with expiry and single use, helper API and page, decision endpoint, relay screen.
  Verify (mechanical): Script creates a handoff, sends it, reads the helper packet (asserting it contains no other field values or ids), answers, and confirms a second answer and an expired token are both refused. Then approves and checks the field origin is helper.
  Learner check: Send the helper link, open it in a second window, answer, and approve it back on the first window.
  Commit: `Relay a single blocked step to a one-time helper link`

- [x] **3. Your vault and the form's questions on screen**
  Becomes usable: The home screen lists the vault's documents. "Try the sample renewal" uses a generated demo vault with well-laid-out synthetic documents; choosing a form uses the person's own vault. The brief lists every question (numbered, by part, with who will answer it) and then the vault documents Relay read.
  Why now: It makes the product match the learner's idea (a vault of saved documents plus an uploaded form) before answers are read from it, and it replaces the earlier per-run supporting uploads.
  PRD ref: `prd.md > The Core Journey` (steps 1–4), `prd.md > Reading documents`, `prd.md > Task brief`
  Spec ref: `spec.md > Where It Runs and How Someone Tries It`, `spec.md > Intake agent`, `spec.md > Data Model`, `spec.md > File Structure`
  Build: Vault module and `GET /api/vault`, session creation from a form plus a vault snapshot, demo vault generator (identity card, assessment letter, bank statement, scanned note) in `docs/vault/`, home vault lists, brief question list and vault documents.
  Verify (mechanical): Tests confirm the demo vault PDFs exist with the 10 expected answer values, `GET /api/vault` lists them with titles and kinds, the sample session snapshots the demo vault, a form upload snapshots the person's vault (and handles an empty vault), and the person's vault folder is git-ignored. Live check: run the sample against the API and confirm the brief shows 14 numbered questions and the vault documents.
  Learner check: Open the app, read the vault list on the home screen, press "Try the sample renewal", and see the questions followed by the vault documents.
  Commit: `Add the document vault and question list`

- [x] **4. Answers read from your vault, shown with their sources**
  Becomes usable: Relay reads the vault and fills in what it finds. The brief shows each question with its answer and where it came from (document, page, exact words), marks unverified or scanned finds as "please check", and counts what was found in the vault.
  Why now: This is the behavior the learner most wants to see, and it is the biggest API risk (several PDFs plus structured output), so it comes before the guided screen.
  PRD ref: `prd.md > Guided questions` (found answers and sources), `prd.md > Task brief`
  Spec ref: `spec.md > Evidence agent`, `spec.md > LLM wrapper`, `spec.md > Orchestrator`
  Build: A multi-PDF call in the OpenAI wrapper, the Evidence agent with a strict findings schema and quote verification against each document's text, storage of proposed answers with evidence, orchestrator step, and answers plus sources on the brief.
  Verify (mechanical): Stubbed-model tests cover a verified finding, a fabricated quote (stored as unverified), an unknown field key (ignored), and a helper field (never filled). Live check: after processing the 14-question demo, at least 10 fields hold a proposed answer from the vault with a quote found in its document.
  Learner check: Press "Try the sample renewal" and read the answers and sources on the brief.
  Commit: `Read answers from the vault and show their sources`

- [x] **5. Export the questions and answers as a PDF**
  Becomes usable: A "Download the answers" button on the brief returns a PDF: the form with its fields filled in, followed by a page listing every question with its answer and where it came from. Questions without an answer are listed as not answered.
  Why now: The learner wants the output to be the question and the answer, and it closes the demo loop early.
  PRD ref: `prd.md > Completion`
  Spec ref: `spec.md > Assembler agent`, `spec.md > The Core Journey Through the System`
  Build: Assembler agent, export endpoint, download button, forget-this-session endpoint.
  Verify (mechanical): Export a stored session, reopen the PDF, and confirm form fields hold the stored answers and the questions-and-answers pages list every question with its answer and source. Deleting the session removes its rows and files.
  Learner check: Download the PDF from the brief and open it.
  Commit: `Export the questions and answers as a PDF`

- [x] **6. Manage your vault: drop in PDFs, see them, delete them**
  Becomes usable: A vault page where the person drops PDFs, sees every saved document (title, file, kind, pages, size, date) and deletes any of them. Documents are stored in the database and used for every form the person chooses; the demo keeps reading `docs/vault/`.
  Why now: The learner asked for it in place of guided answering, and it replaces the folder-based vault with something a non-technical person can use.
  PRD ref: `prd.md > The vault page`, `prd.md > Reading documents`
  Spec ref: `spec.md > Data Model`, `spec.md > Where It Runs and How Someone Tries It`, `spec.md > File Structure`
  Build: `vault_documents` table, vault module with validation and limits, vault endpoints and page, home link, main flow reading the database vault.
  Verify (mechanical): Tests cover saving, listing, replacing, rejecting (not PDF, empty, fake, password-protected, over limits), deleting, the main flow snapshotting the database vault, the sample flow ignoring it, and sessions being forgotten without touching it. Live check in a browser: drop two PDFs, see them listed, delete one, and run a form against the remaining vault.
  Learner check: Open the vault page, drop in a PDF, delete it, then choose a form and watch Relay read the vault.
  Commit: `Add the vault page with database storage`

- [ ] **7. Answer one question at a time and ask a helper about any of them**
  Becomes usable: Guided mode with progress, form wording / simpler wording, typed answers, clear date display, skip, back, confirming or correcting found answers, and "I need help with this one" on any question, which opens the relay for that question with a redacted crop of its source.
  Why now: Lets the person review and correct what Relay found and send any unsure question to a helper, once answers exist.
  PRD ref: `prd.md > Guided questions`, `prd.md > Minimum-disclosure handoff (the kernel)`
  Spec ref: `spec.md > Guide agent`, `spec.md > Relay agent`, `spec.md > Components (web)`
  Build: Guide validation, answer storage and endpoint, guided screen, helper handoff for the chosen question, source crop with word-level redaction.
  Verify (mechanical): A bad date is rejected, a valid date is normalised, an empty required answer is rejected, a skip is accepted, and a handoff for a non-helper field returns a packet with the other answers redacted from its crop.
  Learner check: Answer several questions with the keyboard, confirm a found answer, correct another, and ask a helper about one.
  Commit: `Guided answering and helper requests for any question`

- [ ] **8. Accessibility pass and error states**
  Becomes usable: Reading settings (size, contrast, motion) persist; focus moves to each screen heading; live announcements; clear errors for bad uploads and failed agents.
  Why now: An accessibility product must itself be accessible; polish goes last so it covers every screen.
  PRD ref: `prd.md > States and Boundaries`, `prd.md > Look and Feel`
  Spec ref: `spec.md > Look and Feel`
  Build: Settings panel, focus management, error rendering, README.
  Verify (mechanical): Run the end-to-end test; check every button and input in the HTML has an accessible name.
  Learner check: Do the whole journey with the keyboard only at 130% text in high-contrast mode.
  Commit: `Accessibility settings, focus handling and error states`

## Hands-on Checkpoints

- [x] Early usable behavior explored — after slice 2 (brief + relay handoff)
- [ ] Final kick-the-tires exploration and feedback completed

## Final Review

- [ ] Final review complete — feedback resolved and learner confirms ready to ship

## Code Tour and App Map

- [ ] Learning activity complete — guided route, focused alternative, prior practice connected, or brief recap
- [ ] Optional edit and transfer reflection addressed — offered/declined/already covered/not applicable as appropriate
- [ ] `devpost/app-map.html` generated from finished code, checked, and shown, including a project-grounded practice to reuse

Activity and evidence:
Route and stops:
Edit outcome:
Reflection:
Activity mode:

## Revisions
- Uvicorn access logging is disabled for the local run command — default request logs can expose single-use helper tokens in URLs.
- Learner feedback set a measurable sample target: at least 10 of 14 answers (70%+) must be source-backed in the supporting PDFs and saved for review. The approved one-question helper boundary and review-before-final-PDF behavior remain unchanged.
- Learner direction (vault page): the learner postponed guided answering and asked for a vault page where PDFs are dropped in, listed and deleted, with the vault stored in the database instead of `data/vault/`. A new slice 6 delivers this, guided answering and accessibility move to slices 7 and 8, and the `RELAY_VAULT_DIR` setting and `data/vault/` folder are gone. The demo still reads `docs/vault/`. Uploaded documents now live in `data/relay.db`, which is git-ignored.
- Learner direction (several questions per helper request): one helper link could carry only one question, so the helper answered two witness questions in one box and both landed under the first. A request now carries up to ten chosen questions with one answer box each, the person can send any unanswered question, and approval fills each question separately. This delivers the "any question to a helper" part of slice 6 early; slice 6 keeps guided answering and the source crop. The `handoffs` table gained an `items_json` column with an automatic migration.
- Slices 4 and 5 were built and committed together because the answers display, the counts and the export share the same endpoints and screen. The live run showed the model inventing a household size from an unrelated scanned note, so the Evidence agent now drops any answer whose value is not in its own quote.
- Learner direction (answers and export): the learner wants to see the answers read from the vault and an export that lists each question with its answer. Slices were reordered: slice 4 reads the vault and shows answers with sources, slice 5 exports questions and answers, and guided answering (with the source crop for helper requests) moves to slice 6. Until slice 6, found answers are shown and exported as proposed ("not yet reviewed"); the person confirms or corrects them in slice 6, as the PRD requires. The unique kernel is unchanged.
- Learner direction (vault): the product reads the person's saved documents (a vault) for every form they upload, shows the form's questions and the vault on screen, and lets the person send any unsure question to a helper. This inserts a new slice 3 (vault and question list), renumbers the later slices, and changes slice 4 to allow a helper request on any question and slice 5 to read from the vault. The unique kernel is unchanged; real documents stay in the git-ignored `data/vault/`. the learner loaded the brief, completed the one-question helper handoff, and approved the reply.
