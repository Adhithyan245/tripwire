"""Basic structural checks for findings displayed in the dashboard.

These checks are not the organizers' shared-format validator.
"""
import json

from jsonschema import Draft202012Validator

STRING_LIST = {"type": "array", "items": {"type": "string"}}
RECORDS = {"type": "array", "items": {"type": "object"}}
SCHEMA = {
    "type": "object",
    "required": ["verdict", "data", "findings", "analyses", "repairs"],
    "properties": {
        "verdict": {"type": "string"}, "question": {"type": "string"},
        "data": {"type": "object", "required": ["releases"], "properties": {
            "releases": {"type": "array", "minItems": 1, "items": {"type": "object", "required": ["name"],
                "properties": {"name": {"type": "string"}, "files": RECORDS}}}}},
        "analyses": {"type": "array", "items": {"type": "object", "required": ["id", "verdict", "status", "why"],
            "properties": {"id": {"type": "string"}, "verdict": {"type": "string"}, "status": {"type": "string"},
                "why": {"type": "string"}, "before": {"type": ["object", "null"]}, "after": {"type": ["object", "null"]},
                "inputs": STRING_LIST, "input_changes": {"type": "object", "required": ["identical", "added", "removed", "values_changed"]}}}},
        "findings": {"type": "array", "items": {"type": "object", "required": ["id", "summary"], "properties": {
            "id": {"type": "string"}, "summary": {"type": "string"}, "severity": {"type": "string"},
            "needs_human_review": {"type": "boolean"}, "affects_analyses": STRING_LIST, "not_affected_analyses": STRING_LIST,
            "relevant_questions": STRING_LIST, "evidence": {"type": "array", "items": {"type": "object", "required": ["id"], "properties": {"id": {"type": "string"}}}}}}},
        "repairs": {"type": "array", "items": {"type": "object", "required": ["id", "action", "justification"], "properties": {
            "id": {"type": "string"}, "action": {"type": "string"}, "justification": {"type": "string"},
            "addresses": STRING_LIST, "targets": {"type": "array", "items": {"type": "object", "required": ["id"], "properties": {"id": {"type": "string"}}}}}}},
        "decisions": {"type": "array", "items": {"type": "object", "required": ["repair_id", "decision", "reason", "reviewer_role"],
            "properties": {"repair_id": {"type": "string"}, "decision": {"enum": ["approve", "reject", "request_more_evidence"]},
                "reason": {"type": "string", "minLength": 1}, "reviewer_role": {"type": "string", "minLength": 1}}}},
        "questions": {"type": "array", "items": {"type": "object", "required": ["verdict", "title", "intended_use", "cohort", "why"],
            "properties": {"verdict": {"type": "string"}, "title": {"type": "string"}, "intended_use": {"type": "string"},
                "cohort": {"type": "string"}, "why": {"type": "string"}, "relevant_findings": STRING_LIST,
                "coverage": {"type": "object", "properties": {k: STRING_LIST for k in ("skipped", "unavailable", "missing")}}}}},
        "settings": {"type": "object"},
    },
}


def parse_findings(raw: bytes) -> dict:
    try:
        doc = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc
    error = next(Draft202012Validator(SCHEMA).iter_errors(doc), None)
    if error:
        location = ".".join(map(str, error.absolute_path)) or "document"
        raise ValueError(f"{location}: {error.message}")
    repair_ids = [r["id"] for r in doc["repairs"]]
    if len(set(repair_ids)) != len(repair_ids):
        raise ValueError("Repair IDs must be unique.")
    decision_ids = [d["repair_id"] for d in doc.get("decisions", [])]
    if len(set(decision_ids)) != len(decision_ids) or any(r not in repair_ids for r in decision_ids):
        raise ValueError("Decisions must refer to unique repair IDs in this document.")
    return doc
