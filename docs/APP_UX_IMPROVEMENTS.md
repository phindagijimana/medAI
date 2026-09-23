# MedAI-EPI app UX improvement plan

**Framing.** MedAI-EPI is a research phenotyping assistant, not a clinical decision-support product. UX improvements are scoped to make **researchers, annotators, and reviewers** more productive — not to make it feel like consumer software or to nudge users toward automated clinical decisions.

Improvements ranked by user-value ÷ engineering-cost. Section 5 lists what was implemented in-session; the rest are proposals.

## 1. Highest-value: near-zero-cost quick wins

### 1.1 Document-type auto-detect on paste — **implemented**

**Problem.** `/extract` requires the caller to specify `doc_type` in the request body. When a researcher pastes a document and doesn't know whether it's `progress_note` or `initial_consult`, they either guess or read the schema doc.

**Fix.** Add a `/extract/detect_doc_type` endpoint that classifies text by keyword signature (MRI report → boilerplate like "TECHNIQUE:", "IMPRESSION:", "FLAIR"; EEG report → "background", "epileptiform", "electrographic"; clinic letter → "Dear Dr", "I reviewed"; discharge → "DISCHARGE SUMMARY"). Non-authoritative; UI shows suggestion + reason and asks user to confirm.

**Effort.** ~30 lines, deterministic; no LLM required.

### 1.2 Progress bar for LLM inference — **recommended, not yet implemented**

**Problem.** M2 inference on a long document takes 10–30 s. The UI currently spins with no indication of progress; users refresh and lose state.

**Fix.** Server-sent events (SSE) or polling. As the router iterates modules, emit `{module: "mri", status: "running"}` → `{module: "mri", status: "done", raw_valid: true}` → repeat. UI shows per-module ticks.

**Effort.** ~1 day (server SSE + minimal JS on the front end).

### 1.3 Evidence highlighting in UI — **recommended**

**Problem.** The extraction returns evidence quotes but the UI doesn't visualize where they came from in the source. Users can't quickly verify a claim.

**Fix.** When user clicks an extracted field, the UI scrolls to and highlights the corresponding character range in the source-text panel. Server already returns `char_start`/`char_end` when available.

**Effort.** ~1 day of JavaScript (no server changes required beyond ensuring offsets are returned).

### 1.4 Batch upload → CSV/JSON export

**Problem.** Researchers with 50 letters to phenotype currently paste each one manually.

**Fix.** `POST /extract/batch` accepting a ZIP of `.txt` files or a CSV column of text, with per-doc `doc_type` inferable via 1.1. Returns a downloadable CSV where each row is one document and each column is a phenotype field. Async: user submits, gets a `job_id`, polls or receives an email.

**Effort.** ~2 days (job queue via `apscheduler`, already in requirements.txt).

### 1.5 Copy-friendly output formats

**Problem.** Researchers using the extracted data in Excel, R, or MATLAB want a flat table, not nested JSON.

**Fix.** Alongside JSON, offer:
- CSV — one row per document, one column per field.
- FHIR R4 Bundle — for researchers integrating with hospital data lakes.
- REDCap-format CSV — auto-mappable if the user provides a REDCap data dictionary.

**Effort.** ~2–3 days per format.

## 2. Medium-value

### 2.1 Session persistence and history

Local IndexedDB or lightweight server-side session store so users can leave the tab and come back to their extractions. Not authenticated; keyed by browser session or an opt-in project token.

### 2.2 Confidence-based UI shading

Fields with `certainty=definite` render normally. `probable` → subtle amber tint. `possible` → hatched border. `not_documented` → grey italic. Draws attention to values that warrant reviewer scrutiny.

### 2.3 Model output comparison

Two-column view: on the left, one arm (e.g. M0). On the right, another (e.g. M2). Side-by-side diff of extracted fields highlights disagreements. Useful for reviewers debugging why an arm underperforms on a specific document.

### 2.4 Prompt-registry viewer

Read-only page listing the 22 templates with searchable content. Version history from git. Useful for reviewers who want to see the exact prompt without cloning the repo.

## 3. Longer-term / requires annotation infrastructure

### 3.1 Annotator UI

Document-first (not model-first) view: annotator reads the doc, fills fields with evidence spans, submits. Blind to model output until submission. Not a modification of the existing validator UI — a new page. Would benefit from off-the-shelf tools (Label Studio, Prodigy) but a custom Flask page keeps everything in one deployment.

### 3.2 Adjudication UI

Two-annotator diff viewer with a "resolve" workflow. Adjudicator picks one side, or writes a new value with a note. Logs to the adjudication database (feeds §7.4 gold-standard artefacts in the paper).

### 3.3 Reviewer / error-review UI

Runs eval on a submitted arm, shows the error-taxonomy breakdown by category (Table 8 of the study protocol), lets the reviewer click into individual errors to see the source document + pred + gold + evidence quotes. Feeds the clinical error-review section of the paper (Discussion §5.4).

### 3.4 Auth + roles

Currently no authentication. For annotation and adjudication workflows we need annotator / adjudicator / researcher / admin roles. Simple `flask-login` + hashed passwords (`bcrypt` already in requirements) or SSO via institutional Shibboleth.

### 3.5 PostgreSQL migration

SQLite is fine for single-user; concurrent annotators (§3.1–§3.3) need PostgreSQL. Migration path documented but not implemented.

## 4. Deployment / production hardening (only if hospital pilot)

Not directly UX but affects users' willingness to adopt:

- HTTPS + rate limiting.
- HIPAA measures (audit trail, encryption at rest, minimum-necessary access).
- Monitoring + backups.
- Explicit disclaimer interstitial on first visit ("Research use only — click to acknowledge").

## 5. What was implemented in this session

- **§1.1 doc-type auto-detect** — new `/extract/detect_doc_type` endpoint in `routes/extract.py`; deterministic keyword heuristic; returns `{doc_type: <best_guess>, reasons: [...], confidence: <low/medium/high>}`.
- **API metadata endpoint** — `/extract/health` (already existed) enhanced to also list registered doc types + module classes.

Implementation is in the current commit; smoke test verifies the endpoint returns reasonable classifications for the three canonical shapes.

## 6. Not implemented but scaffolded elsewhere

- Progress bar (§1.2) — the run manifest already carries per-module timing, so SSE glue is the only missing piece.
- Evidence highlighting (§1.3) — server already returns `char_start`/`char_end`; only front-end JS remains.
- Batch upload (§1.4) — `services/router.py::extract_phenotype` is thread-safe and idempotent; wrapping it in a job queue is small.

## 7. Explicit non-goals (per project §21 framing)

- "AI diagnosis" copy or workflows.
- Autocorrect suggestions that could be interpreted as clinical recommendations.
- Dark patterns encouraging users to trust extractions without human review.
- Any UX that hides the "research use only" framing.

The paper's Discussion (§5.1) is explicit: MedAI-EPI is a methodology + open framework contribution, not a clinical-accuracy tool. UX must reinforce that framing, not undermine it.
