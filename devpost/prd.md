---
doc: prd
status: approved
---

# Relay — Product Requirements

Relay is for people who can do most of a public-service form themselves but are blocked on a step or two. It guides them through the form and relays only the blocked step to someone they trust.
Source: `scope.md > The Unique Kernel`, `scope.md > Who It's For`.

## The Core Journey
1. **Arrive.** The home page says what Relay does in one sentence and shows the person's vault: the PDFs they have saved, or a clear message that it is empty, with a link to manage it. The person can choose a PDF form, or try the synthetic sample with its demo vault in `docs/vault/`. Accessibility settings are reachable from every screen.
2. **Choose the form.** They choose one PDF form (fillable, text-based, or scanned). Supporting documents are not uploaded each time: Relay reads the vault.
3. **Relay reads.** A work log shows each agent as it runs, in plain words ("Reading the form", "Looking for answers in your papers"). No spinner-only waiting.
4. **Task brief.** Shows the task name, who it's from, and the deadline (with days left and the exact words it came from), then the parts of the form with question counts. A three-way split: *you can answer N*, *found in your papers N*, *needs another person N*. Also the documents the form asks for, then every question on the form (numbered, grouped by part, each with who will answer it), then the vault documents Relay read.
5. **Guided mode.** One question on screen at a time, with a progress line. For each question: the form's own wording, a "say it simpler" version, and a place to type the answer. When Relay found the answer, it shows the value and the exact words and page it came from, and asks "Is this right?"
6. **Blocked step.** When a question needs another person, or the person presses "I need help with this one" on any question they are unsure about, Relay switches to the handoff screen: *You're stuck on one step, not the whole task.*
7. **Handoff.** The screen shows what the helper will see (an exact preview of each question) and *What stays with you* (counts of other answers, documents and pages). The person chooses which questions to send, up to ten, and can edit the wording of each. They create a one-time link that expires.
8. **Helper.** The helper opens the link and sees only the chosen questions, each with its own answer box; they may leave a box empty. They send their answers. The link then stops working.
9. **Review.** Back on their screen, the person sees each question with the helper's answer, marked as coming from their helper, and approves or rejects the reply. Approved answers fill their own questions.
10. **Finish.** A completion page lists every answer grouped by who supplied it (you / your documents / your helper), plus anything left unresolved. The person downloads the completed PDF and can erase the session.

## Screens and Layout
Five screens for the person, one for the helper:
1. **Home.** Upload and sample.
2. **Brief.** Work log, then task brief.
3. **Guided.** One question at a time.
4. **Relay.** The handoff: prepare, send, wait, review.
5. **Done.** Summary, export, forget.
6. **Helper view.** Separate URL, no navigation, no access to anything else.

A top bar holds the Relay wordmark, the step the person is on, and "Reading settings" (text size, contrast, and motion).

## Look and Feel
- Looks like a well-set printed form: warm paper background, ink-dark text, hairline rules, parts labelled "Part A, Part B…", numbered questions.
- Type: Atkinson Hyperlegible for body text (designed for low-vision readers), a sturdy serif for headings. Large base size (19–20px), generous line height.
- Colour: ink on paper, a deep green for "done / continue", and one warm vermilion reserved for the relay/handoff moment. Colour is never the only signal; every state also has a word.
- Relay's work is shown as a plain, dated work log rather than an animation.
- Avoid: gradients, glassmorphism, emoji, robot or sparkle icons, chat bubbles.

## Features and Behavior

### Reading documents
- Accepts a PDF form, including fillable, text-based, and scanned PDFs. Supporting documents come from the vault, which holds PDFs.
- The generated synthetic demo (a form in `docs/` and a vault in `docs/vault/`) can be loaded from the home screen and always reads the demo vault. A form the person chooses reads their own vault, which they manage on the vault page.
- [ ] The home screen lists each vault document with its title, kind and page count.
- [ ] An unsupported or unreadable file shows a specific message and doesn't block the others.
- [ ] An empty vault is stated clearly, and Relay says every question will go to the person.

### The vault page
- A separate page lists every saved document with its title, file name, kind, page count, size and date added, and how much of the vault is used.
- [ ] The person can drop PDFs onto the page or choose files, and each saved document appears in the list. Several files can be added at once.
- [ ] Each file gets its own result: saved, saved in place of an older copy with the same name, or not added with the reason (not a PDF, empty, unreadable, password-protected, too large, or the vault is full).
- [ ] The person can delete any document after confirming. Deleted documents are no longer used for new forms.
- [ ] The page says where documents are kept (Relay's local database on this computer) and that they are sent to OpenAI when a form is read.
- [ ] Documents stay in the vault when a session is forgotten or purged.

### Task brief
- [ ] Shows the task name, the deadline, and the source words for the deadline. If none is found it says "No deadline found — check the form" and never makes one up.
- [ ] Lists every question on the form, numbered and grouped by part, each with who will answer it (you, your vault, another person).
- [ ] Lists the vault documents Relay read, each with its kind and page count.
- [ ] Shows the three-way split (you / vault / needs a person).
- [ ] Lists the supporting documents the form asks for.

### Guided questions
- [ ] Exactly one question on screen, with "Question n of N" and the part name.
- [ ] "Say it simpler" swaps in plain wording. The person can type an answer.
- [ ] Required answers can't be left empty without choosing "Skip for now". Dates are displayed in a clear written format (for example, "3 March 1961").
- [ ] For the 14-question synthetic sample, at least 10 fields have source-backed values found in supporting PDFs. Relay saves each as a proposed answer with its source and page, then the person confirms or corrects it before it is used in the completed PDF.
- [ ] Found answers show the value and a source line ("From *Assessment letter*, page 1: '…'"). The person confirms or changes the value. Nothing found is ever filled in silently.
- [ ] Values read from a scanned PDF page (such as a stamp or handwriting) are marked as read from a scan and offer "Ask someone to check this".
- [ ] Everything works with the keyboard only, with visible focus.

### Minimum-disclosure handoff (the kernel)
- [ ] One request can carry several questions. The helper answers each in its own box and may leave some empty; each approved answer fills only its own question.
- [ ] The helper preview is exactly what the helper will get.
- [ ] Words in the crop that match the person's other answers (name, address, reference numbers) are blacked out before sharing.
- [ ] The question is checked for the person's other answers, and any match is flagged before sending.
- [ ] The link is single-use and expires (default 24 hours). After an answer, or after expiry, it shows a clear "this link no longer works" message.
- [ ] The helper answer is labelled as coming from the helper and is not used until the person approves it.
- [ ] The person can cancel a handoff before it's answered.

### Completion
- [ ] Every question appears under who supplied it: you, your documents, or your helper.
- [ ] Unresolved questions are listed, not hidden.
- [ ] The downloaded PDF has the answers filled in (in the original form's fields when it had them) plus pages that list every question with its answer and where the answer came from, marking answers not yet reviewed and questions not answered.
- [ ] "Forget this session" deletes the stored documents and answers.

## States and Boundaries
- **First use:** home screen with a "Try the sample renewal" button, so the flow can be seen without personal papers.
- **Required API access:** document processing, including the sample renewal, requires a valid server-side OpenAI API key, configured model and network access. Missing configuration prevents startup with clear setup instructions. Authentication failures, API outages and rate limits show actionable errors; processing never switches to local pattern matching.
- **Reading fails:** the work log shows which agent failed and why, with a retry.
- **Nothing found in papers:** every question goes to the person, and the brief says so.
- **Helper link expired / used / cancelled:** helper sees a specific message and nothing else.
- **What persists:** sessions live in a local SQLite file until erased. Sessions older than 7 days are purged on start.
- **Who sees what:** the person sees everything. A helper sees one packet through one token and cannot list or reach anything else.

## Product Decisions
- Help is granular, not a takeover. The helper never gets the whole form. This is the product.
- The person approves every helper answer. Help is advice until it's accepted.
- Document answers are saved automatically as proposals with their sources; the person confirms or corrects them before they enter the completed form.
- No eligibility or legal judgments. Relay says so on the brief.
- The link is copied and sent by the person. Relay doesn't message anyone.
- Synthetic documents only in the demo, watermarked.
- The first proof supports PDF forms and a PDF vault; other formats and voice input or read-aloud are deferred.
- The person keeps a vault of documents and uploads only the form; any question they are unsure about can go to a helper. The vault is managed on its own page and stored in the local database (git-ignored); the committed `docs/` holds synthetic demo files only.

## What We're Building
Everything in **Features and Behavior** above: the generated synthetic PDF sample packet, the agent pipeline with a visible work log, guided mode, the handoff with redaction, the helper view, approval, PDF export and forget.

## Deferred From the POC
- **Sending the link for you** (SMS/email): needs messaging providers and consent flows.
- **Saved helpers:** needs accounts.
- **Several helpers on one task at once:** one active handoff proves the idea.
- **Filling web forms:** browser automation is a separate product.
- **Non-PDF uploads:** the first proof is built and verified around PDFs.
- **Voice input and read-aloud:** typed answers keep the first guided flow focused.

## Possible Later Enhancements
Multilingual guidance. A helper reply by voice note. An agency-side view that accepts Relay's provenance record.

## Non-Goals
- Determining eligibility or giving legal or medical advice.
- Submitting to any real agency.
- Persistent cloud document storage. Documents are stored locally, but their content is sent to OpenAI for processing; this is disclosed before upload.

## Open Questions
- The demo video must show a real API-backed run using synthetic documents. Never show the API key.
