"""Adapter: plugs the Role 3 intake backend (intake_prototype) into the dashboard's "Prepare data with AI" view.

The view calls suggest_mappings(meta, fields) and expects
    {"target": "clinical.tsv"|"survival.tsv", "mappings": [{"column", "field", "confidence": 0..1, "reason"}],
     "questions": [...]}.
This module translates to and from intake_prototype.suggest_mappings / validate_suggestions. Only column names, the
row count, the file name and the research question are sent (never rows), and only after the user ticks the opt-in
box in the view. Without OPENAI_API_KEY in the environment this module doesn't import, and the view says AI
suggestions are unavailable (the manual path still works). No key is read from or written to the repo.
"""
from __future__ import annotations

import os

if not os.environ.get("OPENAI_API_KEY"):
    raise ImportError("OPENAI_API_KEY is not set: AI suggestions unavailable")

from intake_prototype import suggest_mappings as _suggest  # noqa: E402
from intake_prototype import validate_suggestions as _validate  # noqa: E402

CONFIDENCE = {"high": 0.95, "medium": 0.7, "low": 0.4}  # the view asks for review below 0.8
SURVIVAL_ONLY = {"OS", "OS.time"}


def translate(validated: dict, fields: dict) -> dict:
    """intake_prototype's validated suggestions -> the view's contract. Pure, so it is testable without a network."""
    valid = [m for m in validated.get("valid_mappings", []) if m.get("target")]
    targets = {m["target"] for m in valid}
    target = "survival.tsv" if targets & SURVIVAL_ONLY and not targets & (set(fields["clinical.tsv"]) - {"sampleID"}) \
        else "clinical.tsv"
    rename = {"sampleID": "sample"} if target == "survival.tsv" else {}
    allowed = set(fields[target])
    mappings = []
    for m in valid:
        field = rename.get(m["target"], m["target"])
        if field in allowed:
            conf = m.get("confidence", "low")
            mappings.append({"column": m["source"], "field": field, "confidence": CONFIDENCE.get(conf, 0.4),
                             "reason": f"AI proposed ({conf} confidence)"})
    questions = list(validated.get("clarification_questions", []))
    rejected = validated.get("rejected_mappings", [])
    if rejected:
        questions.append(f"{len(rejected)} AI suggestion(s) were rejected by validation (e.g. a column not in the "
                         "file or an unsupported field). Map any missing columns yourself.")
    return {"target": target, "mappings": mappings, "questions": questions}


def suggest_mappings(meta: dict, fields: dict) -> dict:
    allowed = frozenset(f for t in fields.values() for f in t) | {"sampleID"}
    raw = _suggest(source_columns=list(meta["columns"]), num_rows=int(meta["n_rows"]), allowed_targets=allowed,
                   consent=True, filename=meta.get("file_name"), research_question=meta.get("research_question", ""))
    return translate(_validate(raw, list(meta["columns"]), allowed_targets=allowed), fields)
