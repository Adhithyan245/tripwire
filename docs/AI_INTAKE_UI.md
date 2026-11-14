# AI-Assisted Intake Prototype – API Contract & UI Specification

## Overview

The intake prototype lets a user upload a CSV/TSV file, get AI-suggested
column mappings, review and approve them, and produce a renamed DataFrame
ready for downstream analysis. It never modifies the existing Tripwire
engine or any release, never pretends one CSV is a valid TCGA release, and never applies
mappings without explicit human approval.

**Two-agent workflow (experimental, `role3/ai-intake-prototype` only):** the
end-to-end flow that ends in a real firewall run is documented in
[Two-agent workflow](#two-agent-workflow-experimental) below. The single-call
helpers documented first (`suggest_mappings` and the rest) still work, but new
UI work should use `IntakeWorkflow`.

---

## Python API Contract

### `parse_upload(data: bytes, filename: str, content_type: str | None = None) -> pd.DataFrame`

Validates and parses uploaded bytes.

| Parameter      | Type             | Description                                    |
| -------------- | ---------------- | ---------------------------------------------- |
| `data`         | `bytes`          | Raw upload payload (UTF-8 CSV, TSV, or gzip)   |
| `filename`     | `str`            | Original filename; drives type inference        |
| `content_type` | `str \| None`    | Optional MIME type hint                         |

**Returns:** `pd.DataFrame`

**Raises `UploadError`** when:
- Not bytes, empty, or exceeds 50 MiB
- Filename is empty or extension is unsupported (only `.csv`, `.tsv`, `.csv.gz`, `.tsv.gz`)
- Non-UTF-8 encoding
- Duplicate column headers
- Gzip decompression fails or exceeds 20x ratio (bomb protection)
- Header only, no data rows
- Exceeds 2 000 columns or 500 000 rows

---

### `suggest_mappings(source_columns, num_rows, *, consent, model, timeout, ...) -> dict`

Calls OpenAI Chat Completions to suggest column mappings.

| Parameter        | Type              | Default            | Description                                  |
| ---------------- | ----------------- | ------------------ | -------------------------------------------- |
| `source_columns` | `list[str]`       | —                  | Column names from the upload                 |
| `num_rows`       | `int`             | —                  | Row count (aggregate only)                   |
| `allowed_targets`| `frozenset[str]`  | `ALLOWED_TARGETS`  | Valid target column names                    |
| `card_ids`       | `list[str]`       | from `BY_ID.keys()`| Supported question card IDs                  |
| `consent`        | `bool`            | `False`            | **Must be `True`** – explicit opt-in         |
| `model`          | `str`             | `"gpt-4.1-mini"`  | OpenAI model                                 |
| `timeout`        | `int`             | `30`               | Request timeout in seconds                   |
| `filename`       | `str \| None`     | `None`             | Filename context for the model               |
| `research_question` | `str`          | `""`               | User question; omit to suppress card suggestion |

**Consent gate:** If `consent` is `False`, raises `ValueError` immediately
with no network activity.

**Data sent to OpenAI:** Column names, row count, filename, research question,
allowed targets, and card IDs. No data rows are sent. Headers, filenames and
free text can themselves contain sensitive information; review them before
opting in. A question-card suggestion is only a proposal and requires review.

**Returns:** Raw parsed JSON dict from the model (unvalidated).

**Raises:** `ValueError` (no consent or missing API key), `RuntimeError`
(network/API/JSON errors).

---

### `validate_suggestions(suggestions, source_columns, ...) -> dict`

Validates AI output against actual headers and allowed sets.

**Returns:**
```python
{
    "valid_mappings": [...],         # mappings that passed all checks
    "rejected_mappings": [...],      # with rejection_reasons
    "question_card_id": str | None,  # validated or None
    "clarification_questions": [...], # from the model
    "errors": [...]                  # structural validation errors
}
```

**Rejects:**
- Source columns not present in the upload
- Target columns not in `ALLOWED_TARGETS`
- Duplicate source or target assignments
- Hallucinated question card IDs
- Invalid confidence values
- Malformed entries (non-dict, missing keys)

---

### `match_question_card(card_id, card_ids=None) -> str | None`

Returns the card ID if it exists in `tripwire.questions.BY_ID`, else `None`.

---

### `apply_mappings(df, approved_mappings, *, approval, ...) -> pd.DataFrame`

Applies human-approved column renames to produce a **new** DataFrame.

| Parameter          | Type              | Description                           |
| ------------------ | ----------------- | ------------------------------------- |
| `df`               | `pd.DataFrame`    | Original upload (never mutated)       |
| `approved_mappings`| `list[dict]`      | `{"source": ..., "target": ...}`      |
| `approval`         | `bool`            | **Must be `True`** – human approved   |

**Guarantees:**
- Original DataFrame is never mutated
- All rows and values are preserved exactly
- No deduplication, imputation, or clinical relabeling
- Unmapped columns keep their original names
- Null targets are skipped (column unchanged)

**Raises `TransformError`:** missing approval, invalid/hallucinated targets,
missing source columns, duplicate source or target.

---

### `ALLOWED_TARGETS`

```python
frozenset({
    "sampleID",
    "breast_carcinoma_estrogen_receptor_status",
    "PAM50Call_RNAseq",
    "age",
    "OS",
    "OS.time",
    "Redaction",
})
```

---

## UI Screen Requirements

### Screen 1: Privacy Opt-In

- Show: "With your consent, column names, filename, row count, and your
  research question will be sent to OpenAI. Data rows are not sent. Review
  those details for sensitive information before consenting."
- Future-product note: "A production version could use a locally hosted AI
  model so that dataset metadata and research questions remain within the
  user's environment. Local processing is planned, not implemented in this
  prototype; additional security controls would still be required."
- Buttons: **Consent & Continue** / **Skip AI (Manual Only)**
- If user skips, go directly to Screen 3 (manual mapping).

### Screen 2: Upload

- Accept: `.csv`, `.tsv`, `.csv.gz`, `.tsv.gz` (drag-and-drop or file picker)
- Show upload progress
- On success: display filename, column count, row count
- On error: display the `UploadError` message; allow retry
- Max size: 50 MiB (before decompression)

### Screen 3: Suggested Mappings

- Table with columns: Source Column | Suggested Target | Confidence | Action
- Confidence shown as badge: high (green), medium (yellow), low (red)
- Each row: **Accept** / **Edit** / **Reject** buttons
- Rejected/hallucinated mappings shown separately with reasons
- If AI suggested a question card: show card title and ID, with
  **Accept** / **Reject**
- All suggestions are proposals; none are pre-applied

### Screen 4: Clarification Questions

- List any clarification questions from the AI
- User can type answers (for context; not sent back to AI in this prototype)
- **Continue** to proceed with current mappings

### Screen 5: Approve & Apply

- Summary table of all accepted mappings: Source → Target
- Warning: "This will rename columns in a new copy. The original file is
  not modified. This is NOT a valid TCGA release and the Tripwire firewall
  has not run."
- **Approve & Transform** / **Go Back**

### Screen 6: Results

- Show the renamed DataFrame preview (first 10 rows)
- Download button for the result as CSV/TSV
- Show any unmapped columns
- Banner: "This output is a renamed copy for exploration only. It is not a
  validated TCGA release. The Tripwire integrity engine requires paired
  releases with fixed structures."

### Limitations & Disclaimers (shown on every screen)

- AI suggestions are proposals, not decisions
- Column renaming does not imply semantic equivalence
- A single transformed CSV is not a valid TCGA release
- The Tripwire firewall has not run on this output
- No deduplication, imputation, or clinical relabeling is performed
- Show ambiguous cases as needing human review; the AI cannot determine
  whether two fields are semantically equivalent
- Input metadata sent to OpenAI only with explicit consent

---

## Two-agent workflow (experimental)

> **Status:** experimental, on `role3/ai-intake-prototype` only. It was built after
> the Friday feature freeze, so under CONTRIBUTING.md it must not go into `dev`
> without a plan-change proposal that the owners approve. Tests use mocked
> AI. **The live OpenAI integration has not been tested.**

Code: `intake_prototype/workflow.py` (state machine), `intake_prototype/agents.py`
(the two agents and their validation), `intake_prototype/demo.py` (CLI demo).
Tests: `tests/test_intake_workflow.py`. Uses only the standard library and the
existing dependencies (pandas, numpy).

### What it does

A researcher has a trusted release **A** and a candidate release **B**. B's
clinical table arrives as a separate upload whose columns don't use the
standard names. The workflow:

1. Proposes mappings onto the fixed clinical schema. Either the **preparation
   agent** proposes them or the user maps by hand.
2. Has the data owner review each mapping, answer every clarification and
   approve the result.
3. Writes a prepared `clinical.tsv`. The only change is renamed columns.
4. Interprets the research question. The separate **question agent** proposes
   a supported card or none, and a person confirms the card or chooses
   baseline-only.
5. Builds a **temporary candidate copy**: B's files, with `clinical.tsv`
   replaced by the prepared table. It runs the real engine
   (`tripwire.api.check`) on that copy, then deletes it.
6. Puts the verdict up for **human review**. Nothing is ever accepted
   automatically.

### State machine

```
created → uploaded → mapping_proposed ─→ mapping_reviewed → approved → prepared
                     (AI or manual)                                      │
        ┌──────────────────────────────────────────────────────────────┘
        └→ question_proposed (AI, optional) → question_confirmed → run_firewall()
              ├→ review_pending → (record_review) → reviewed → close() → closed
              └→ firewall_failed (no verdict; fix inputs and run again)
```

- Each step is a separate method call. Out-of-order calls raise `WorkflowError`.
- Changing an earlier input invalidates every later step. That covers a new
  upload, a mapping decision, a clarification answer, the question text and
  the releases. For example, a mapping change after approval deletes the
  prepared table and reopens the review. A new question clears the
  interpretation, the confirmation, any run and the review. A new upload
  also unbinds the releases, because the "belongs to B" confirmation was for
  the old file.
- `wf.status()` returns `state`, `next` (the allowed actions),
  `open_clarifications`, `undecided_proposals`, `consents`, `releases_bound`,
  `verdict` and `review`. The UI can drive the screens from it.

### Integration API

```python
from intake_prototype import IntakeWorkflow, WorkflowError, AgentError
from intake_prototype import agents as ag

wf = IntakeWorkflow.create()                 # or create("/path/to/sessions"); never /tmp
wf.upload(file_bytes, "clinical_B.csv")      # .csv/.tsv(.gz); raises UploadError

# Preparation agent: show the exact payload, then ask for consent bound to it
prev = wf.preview_ai_payload("preparation")  # {"agent", "payload", "sha256"}
wf.grant_consent("preparation", granted_by="Dr. X (data owner)", payload_sha256=prev["sha256"])
view = wf.propose_mappings()                 # real OpenAI call; AgentError on any failure (state unchanged)
# ...or skip AI entirely:  view = wf.start_manual_mapping()

# Review: decide EVERY proposal, answer EVERY clarification
wf.decide_mapping("Sample Barcode", "accept", decided_by="Dr. X")
wf.decide_mapping("Age at dx", "edit", "age", decided_by="Dr. X", note="years at diagnosis")
wf.decide_mapping("Notes", "reject", decided_by="Dr. X")
wf.answer_clarification("C1", "IHC-based, same as release A", answered_by="Dr. X")
wf.complete_mapping_review(reviewed_by="Dr. X")      # raises, listing what is still open
wf.approve(data_owner_confirmed=True, approved_by="Dr. X")
wf.prepare()                                          # writes prepared/clinical.tsv; values verified unchanged

# Releases: the person must confirm the upload is B's clinical table
wf.bind_releases("data/release-A", "data/release-B", upload_belongs_to_candidate=True, confirmed_by="Dr. X")

# Question agent: separate consent, separate call
wf.set_question("What is the PAM50 subtype mix of primary tumors?")
prev = wf.preview_ai_payload("question")
wf.grant_consent("question", granted_by="Dr. Y (researcher)", payload_sha256=prev["sha256"])
qv = wf.propose_question()            # qv["proposal"]["card_id"] is a supported id or None
wf.confirm_question("subtype_mix", confirmed_by="Dr. Y")      # the person's choice; may differ from the proposal
# or: wf.confirm_question(None, confirmed_by="Dr. Y", baseline_only=True)

run = wf.run_firewall()               # link_mode="symlink" to save disk; validate=True to run format/validate.py
run["status"], run["verdict"], run["question_verdict"], run["review"]   # review is always "pending"
wf.findings()                          # the findings.json document (stays local; never sent to a model)

wf.record_review("accept_result", reason="relabels confirmed", reviewer_role="curator")
# or "reject_result", or "request_more_evidence" (keeps the review open)

wf.close()                             # deletes upload/, prepared/, work/; close(purge_findings=True) also deletes results/
```

Return values are plain JSON-ready dicts. `wf.evidence()` returns the full
structured record, which is also persisted as `evidence.json`.
`IntakeWorkflow.load(session_dir)` resumes a session, for example after a UI
restart. `wf.mapping_view()` and `wf.question_view()` return everything the
review screens need: proposals, rejected model output with reasons, targets
with descriptions, clarifications and the supported cards.

**Errors the UI must show:** `UploadError` (bad file), `AgentError` (no
consent, no key, network failure, invalid model output; offer the manual path)
and `WorkflowError` (step out of order or preconditions not met; the message
says what is missing).

### The two agents

| | Preparation agent | Question agent |
|---|---|---|
| Receives | column names, row and column counts, file format, the fixed targets with descriptions | the question text, every supported card (id, title, intended use, label, inputs, cohort), the prepared column names, the candidate release's file names |
| Never receives | cell values, rows, the filename, findings | cell values, rows, findings |
| Returns (validated) | `proposals` [{source, target or null, confidence, rationale}], `rejected` with reasons, clarifications | `card_id` (supported id or None), explanation, clarifications |
| Consent | `grant_consent("preparation", ...)` | `grant_consent("question", ...)`, given separately |

- **Consent** is per workflow and per agent, and it is bound to the sha256 of
  the payload the user was shown. If the payload changes (new upload, new
  question, new releases), the call is refused with
  `AgentError("... changed since consent ...")` before anything is sent.
  `revoke_consent(agent)` withdraws it.
- **Model output is untrusted.** Responses are capped at 256 KiB and must be a
  JSON object. Fields are projected onto an allow-list and text is trimmed
  and stripped of control characters. Sources must be real headers. Targets
  must be in the fixed schema. Duplicate sources or targets and invalid
  confidences are rejected. An unknown card id becomes `None` with an error,
  so the check fails closed. Proposals with medium or low confidence get an
  extra clarification that must be answered. **Confidence is the model's
  self-report and is never treated as proof of meaning.**
- The key comes from `OPENAI_API_KEY`. It is never stored or logged. The model
  defaults to `gpt-4.1-mini` and can be overridden with `OPENAI_MODEL` or the
  `model=` argument. HTTP errors don't echo the response body.

### Fixed supported schema

The upload replaces `clinical.tsv` only, so the targets are the clinical fields:
`sampleID` (required), `breast_carcinoma_estrogen_receptor_status`,
`PAM50Call_RNAseq` and `age`. Survival fields (`OS`, `OS.time`, `Redaction`)
are in `survival.tsv`, which this workflow never edits, so they are not
offered. Unmapped columns keep their names. Values, rows and their order are
never changed. This is verified in memory and again after the prepared file
is written and read back.

### Candidate copy and the firewall run

- The run needs bound releases (with `upload_belongs_to_candidate=True`), the
  prepared table matching its recorded hash, and a confirmed card or an
  explicit baseline-only choice. If any of these is missing, it raises
  `WorkflowError` and no verdict is produced.
- Both release folders are fingerprinted (sha256 of every file) when they are
  bound. They are checked again before and after the run, along with the
  stored original upload. Any difference means no verdict.
- The copy is built under `<session>/work/<run>/candidate/`. It contains every
  file in B except `clinical.tsv`, which is replaced by the prepared table.
  Organizer answer keys named `CHANGES.json` are never opened, hashed or
  copied. The copy is deleted in a `finally` block, so it is removed on
  failure too.
- If the engine fails, the run is recorded as `firewall_failed` with only the
  exception type, because the message could quote data. No verdict is given.
- `run["sample_overlap"]` and `run["warnings"]` give a counts-only local check
  of whether the uploaded sample IDs appear in B's own `clinical.tsv`, when B
  has one.

### Storage, audit and cleanup

- Sessions are stored under `$DRIFTWIRE_INTAKE_ROOT` or
  `~/.driftwire/intake-sessions/<id>/`, outside the repo. `/tmp`, `/var/tmp`
  and the system temp folder are refused. Files are written `0600` and
  folders `0700`.
- `upload/` holds the original bytes, which are never modified. `prepared/`
  holds `clinical.tsv`. `results/<run>/` holds `findings.json`. The session
  also has `evidence.json` and `audit.jsonl`.
- `audit.jsonl` is hash-chained, with `prev` and `hash` on each event. It
  holds event names, states, counts, hashes, card ids and mapping decisions.
  It holds no cell values, no human free text (only sha256 of answers, notes
  and reasons) and no secrets. Human answers themselves are in
  `evidence.json`.
- `close()` deletes all patient-derived data folders. Findings are kept
  unless you pass `purge_findings=True`. `discard()` deletes the whole session.
  Use `with IntakeWorkflow.create() as wf:` to close the session even when an
  error is raised.

### UI screen mapping (for the UI owner)

| Screen | Calls |
|---|---|
| Upload | `upload()` |
| Privacy and consent (preparation) | show `preview_ai_payload("preparation")["payload"]`, then `grant_consent(...)`; offer **Manual** → `start_manual_mapping()` |
| Mapping review | `mapping_view()`: proposals (Accept / Edit / Reject → `decide_mapping`), rejected output with reasons, confidence shown as "model self-report" |
| Clarifications | `clarifications("mapping")` → `answer_clarification` (every answer required) |
| Data-owner approval | `complete_mapping_review()` → `approve(data_owner_confirmed=True, ...)` → `prepare()` |
| Releases | trusted path, candidate path, checkbox for the `BELONGS_STATEMENT` text → `bind_releases()` |
| Question | `set_question()`; consent for the question agent as above; `propose_question()`; `question_view()`; card picker (supported cards plus baseline-only) → `confirm_question()` |
| Run | `run_firewall()`; show "no verdict" when `status != "complete"` |
| Review | verdict, findings, "review pending" banner → `record_review()` |

Show `wf.evidence()["limitations"]` on every screen.

### CLI demo (entirely synthetic)

```bash
python -m intake_prototype demo                          # scripted stand-in agents: no network, no key
python -m intake_prototype demo --session-root ~/driftwire-sessions --link-mode symlink
OPENAI_API_KEY=... python -m intake_prototype demo --ai openai --consent   # real calls; synthetic metadata only
```

The demo creates synthetic releases A and B. B has no `clinical.tsv`; its
clinical table is a CSV upload with non-standard headers and four relabelled
subtypes. The demo runs every step, runs the real engine and leaves the
verdict pending review. It then deletes the session's data folders and the
synthetic inputs. The script stands in for the human, and every scripted
answer is labelled `DEMO`. The scripted agents return fixed JSON; they are not
a model.

### Limitations

- This is a research prototype. A renamed table is not a validated release.
  The workflow makes no clinical claims and is not production-ready.
- Column names and the question are metadata, but they can still be
  sensitive. Users should review the payload preview before consenting. A
  locally hosted model is a possible future option; it is not implemented.
- Clarification answers are stored for audit. They are not sent back to a
  model.
- The workflow does not apply repairs. Findings flagged for human review still
  go through `tripwire.review.apply_decisions`.
- Only the clinical table can be supplied. Other candidate files are used as
  delivered.
