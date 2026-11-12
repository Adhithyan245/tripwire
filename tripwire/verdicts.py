"""One verdict engine for both modes. Code decides every verdict; the AI never does.

| Verdict               | Release diff                                       | Question readiness                         |
| Ready                 | Nothing this analysis uses changed                 | All checks pass                            |
| Conditional           | Inputs changed, result moved within tolerance      | A fixable issue, e.g. split by patient     |
| Blocked               | Moved beyond tolerance, conclusion flipped, or     | A check fails that can't be fixed here     |
|                       | moved with no detected change to explain it        |                                            |
| Insufficient Evidence | Too few samples left after the change              | Too few labeled samples per class          |
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .analyses import Movement
from .config import worst


@dataclass
class AnalysisVerdict:
    verdict: str
    reason: str


def release_verdict(affected: bool, movement: Movement | None) -> AnalysisVerdict:
    """movement is None when the analysis wasn't rerun."""
    if movement is None:
        return AnalysisVerdict("Ready", "Nothing this analysis uses changed; not rerun.")
    if not affected:
        if movement.moved:
            return AnalysisVerdict("Blocked", "The result moved although no detected change touches this "
                                   f"analysis: something changed that the detector didn't report ({movement.magnitude}).")
        return AnalysisVerdict("Ready", f"Nothing this analysis uses changed; a check rerun confirms it ({movement.magnitude}).")
    if movement.insufficient:
        return AnalysisVerdict("Insufficient Evidence", f"Too few samples left in a group after the change ({movement.magnitude}).")
    if movement.flipped:
        return AnalysisVerdict("Blocked", f"The conclusion flipped ({movement.magnitude}).")
    if movement.beyond_tolerance:
        return AnalysisVerdict("Blocked", f"The result moved beyond tolerance ({movement.magnitude}).")
    if movement.moved:
        return AnalysisVerdict("Conditional", f"Inputs changed; the result moved within tolerance ({movement.magnitude}).")
    return AnalysisVerdict("Conditional", f"Inputs changed but the result did not move ({movement.magnitude}).")


# ---------- Question readiness (Mode 2) ----------

CHECK_STATUS_TO_VERDICT = {
    "pass": "Ready",
    "fixable": "Conditional",
    "insufficient": "Insufficient Evidence",
    "fail": "Blocked",
    # A check that didn't run is missing evidence, never a pass.
    "skipped": "Insufficient Evidence",
    "unavailable": "Insufficient Evidence",
}


@dataclass
class CheckResult:
    name: str                 # "patient_leakage", "site_confounding", "sample_size"
    status: str               # pass | fixable | insufficient | fail | skipped | unavailable
    summary: str
    evidence: list[dict] = field(default_factory=list)  # evidence refs in findings.json shape
    fix: str | None = None    # for "fixable", what to do (e.g. "split by patient_id")

    def __post_init__(self):
        if self.status not in CHECK_STATUS_TO_VERDICT:
            raise ValueError(f"status must be one of {sorted(CHECK_STATUS_TO_VERDICT)}")


def coverage(checks: list[CheckResult], required: list[str]) -> dict[str, list[str]]:
    """Which checks ran, passed, failed, were skipped or unavailable, and which required ones are missing.
    Shown in the interface so a gap is never read as readiness."""
    out = {s: [c.name for c in checks if c.status == s] for s in CHECK_STATUS_TO_VERDICT}
    out["missing"] = [r for r in required if r not in {c.name for c in checks}]
    return out


def question_verdict(checks: list[CheckResult], required: list[str] | None = None) -> AnalysisVerdict:
    """A required check that is missing counts as unavailable: the verdict can't be better than Insufficient Evidence."""
    have = {c.name for c in checks}
    checks = list(checks) + [CheckResult(r, "unavailable", "required check did not run")
                             for r in (required or []) if r not in have]
    if not checks:
        return AnalysisVerdict("Insufficient Evidence", "No readiness checks ran.")
    v = worst(CHECK_STATUS_TO_VERDICT[c.status] for c in checks)
    driving = [c for c in checks if CHECK_STATUS_TO_VERDICT[c.status] == v]
    return AnalysisVerdict(v, "; ".join(f"{c.name}: {c.summary}" for c in driving))
