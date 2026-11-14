"""Human review: a reviewer approves, rejects or asks for more evidence on each proposed repair.

Decisions go into findings.json's `decisions` section (shared format v0.2), each with a reason and the reviewer's role.
Recording a decision never applies a repair and never changes source data: `original_preserved` is always true.
"""
from __future__ import annotations

import copy

DECISIONS = ("approve", "reject", "request_more_evidence")
LABELS = {"approve": "Approve", "reject": "Reject", "request_more_evidence": "Request more evidence"}


def apply_decisions(doc: dict, decisions: dict[str, dict]) -> dict:
    """decisions: repair_id -> {"decision", "reason", "reviewer_role"}. Returns a new document; the input is untouched.

    Raises ValueError for an unknown repair, an unknown decision, or a missing reason or role."""
    repairs = {r["id"] for r in doc.get("repairs", [])}
    out = []
    for rid, d in decisions.items():
        if rid not in repairs:
            raise ValueError(f"unknown repair {rid!r}")
        if d.get("decision") not in DECISIONS:
            raise ValueError(f"{rid}: decision must be one of {DECISIONS}")
        reason, role = (d.get("reason") or "").strip(), (d.get("reviewer_role") or "").strip()
        if not reason:
            raise ValueError(f"{rid}: a reason is required")
        if not role:
            raise ValueError(f"{rid}: the reviewer's role is required")
        out.append({"repair_id": rid, "decision": d["decision"], "reason": reason, "reviewer_role": role,
                    "original_preserved": True})
    new = copy.deepcopy(doc)
    new["decisions"] = sorted(out, key=lambda x: [r["id"] for r in doc["repairs"]].index(x["repair_id"]))
    return new


def review_status(doc: dict) -> dict:
    """Which findings flagged for review still have an undecided repair."""
    decided = {d["repair_id"] for d in doc.get("decisions", [])}
    by_finding: dict[str, list[str]] = {}
    for r in doc.get("repairs", []):
        for f in r.get("addresses", []):
            by_finding.setdefault(f, []).append(r["id"])
    flagged = [f["id"] for f in doc.get("findings", []) if f.get("needs_human_review")]
    open_ = [f for f in flagged if not all(rid in decided for rid in by_finding.get(f, []))]
    return {"flagged": flagged, "open": open_, "decided_repairs": sorted(decided)}
