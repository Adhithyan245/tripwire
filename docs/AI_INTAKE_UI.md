# AI-Assisted Intake Prototype – API Contract & UI Specification

## Overview

The intake prototype lets a user upload a CSV/TSV file, get AI-suggested
column mappings, review and approve them, and produce a renamed DataFrame
ready for downstream analysis. It never touches the existing Tripwire
engine, never pretends one CSV is a valid TCGA release, and never applies
mappings without explicit human approval.

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
