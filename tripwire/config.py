"""Stated tolerances and minimums. Shown in the interface and written into findings.json. Changing a value is a
plan change (see CONTRIBUTING.md)."""

CONFIG = {
    # A1: relative change in the Positive-minus-Negative ER-alpha difference that still counts as "moved within tolerance"
    "A1_difference_rel_tolerance": 0.05,
    # A2: largest shift in any subtype's share, in percentage points
    "A2_percent_pp_tolerance": 1.0,
    # Fewer than this many samples in any compared group -> Insufficient Evidence
    "min_samples_per_group": 20,
    # Rerun the analyses the impact map says are unaffected, to check the map. If one moved anyway,
    # something changed that the detector didn't report, and the analysis is Blocked.
    "verify_unaffected": True,
    "producer_team": "Tripwire",
}

VERDICT_ORDER = ["Ready", "Conditional", "Insufficient Evidence", "Blocked"]


def worst(verdicts):
    verdicts = list(verdicts)
    return max(verdicts, key=VERDICT_ORDER.index) if verdicts else "Ready"
