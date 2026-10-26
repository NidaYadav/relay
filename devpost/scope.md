---
doc: scope
status: approved
---

# Relay

Relay helps someone complete a public-service form themselves: AI finds relevant answers in their documents, fills and saves them, and returns a completed form. If one step is blocked, the person can ask a trusted helper for only that step.

## The Unique Kernel
The person gets a completed document without handing their whole packet to someone else. A one-time helper task reveals only the blocked question and the minimum redacted evidence needed to answer it; the person reviews the answer before it goes into the form.

## Who It's For
Someone with low vision, limited dexterity, cognitive overload, or low digital confidence who is completing a renewal form for a benefit they rely on. They can handle most of the form but may need help with a step that is hard to read or requires another person's input. Today they may give up, wait for agency support, or hand over their whole bundle of private papers.

## The Core Loop
1. Keep a vault of personal documents (ID, bank statement, letters) saved in Relay, and upload only the form. The demo uses a generated sample vault whose details are scattered across several documents.
2. Relay lists the form's questions, finds and stores supported answers from the vault, then guides the person one question at a time to confirm or correct them.
3. For any question they are unsure about, the person previews and sends a one-time task to a trusted helper.
4. The person reviews the helper's answer and downloads the completed form.

## Inspiration & Identity
Warm, calm, high contrast, and large type. It should feel like a well-set printed form, not a chatbot: clear sections, rules, and numbering. No glowing robot, galaxy background, generic gradient dashboard, or emoji. The helper handoff should feel like a relay between two people.

## Why This Matters to the Learner
The learner's brief puts it this way: "The problem is not only that forms are hard to read. The problem is that inaccessible execution forces people to surrender the task." They also want to improve spec-driven AI-assisted development, product scoping, and agent orchestration.

## What "Working" Looks Like
The person sees their vault and the form's questions on screen. In the demo, the vault is a generated set of synthetic PDFs in `docs/vault/` (identity card, assessment letter, bank statement, scanned note) and the form is a synthetic renewal in `docs/`. For the 14-question sample, Relay uses API-backed AI to find and save source-backed answers for at least 10 fields (at least 70%), showing the source so the person can review or correct them before the completed PDF uses them. The person sends a one-time helper link for one blocked step; the helper sees only that question and its redacted evidence. After the person approves the reply, Relay produces a completed PDF showing where each answer came from.

**The "oh, that's cool" beat:** the helper sees one bounded task, while the person keeps the rest of the form and documents private—and still gets the completed form.

## The POC Boundary
- One synthetic renewal task: a form in `docs/` and a demo vault of generated PDFs in `docs/vault/` with the information scattered across them.
- A document vault: PDFs Relay reads for every form. The person manages their own vault on a vault page, where they drop in PDFs, see what is saved and delete documents. The vault is stored in the local SQLite database (git-ignored with the rest of `data/`), so real documents are never committed. The demo reads its synthetic vault straight from `docs/vault/`. The person uploads only the form.
- The form's questions and the vault's documents are both visible on screen.
- API-backed document reading and answer finding using a configured server-side OpenAI API key and model. No local pattern-matching fallback.
- One-question-at-a-time answer confirmation, stored answers, and a completed PDF with answer provenance.
- One blocked-step handoff to a trusted helper using an expiring, single-use link, minimum-necessary redacted evidence, and the person's approval.
- A local SQLite store and a way to forget the session.
- A short demo on synthetic data; no real personal documents.

## Later
- Support for document formats beyond PDF.
- Read-aloud, voice input, and more languages.
- Real government portals and online forms.
- Helper notifications or saved helper contacts.
- Testing with people who use assistive technology.

## Explicitly Cut
- **Eligibility decisions.** Relay helps complete paperwork; it never decides who qualifies.
- **Live submission to agencies.** Out of reach for a proof of concept and risky with real data.
- **Accounts and identity verification.** A one-time link is enough for this demo; real identity needs a real system.
- **A helper marketplace.** Helpers are people the user already trusts; strangers would change the privacy model.
- **Real personal data.** Demo documents are synthetic and labelled that way.
