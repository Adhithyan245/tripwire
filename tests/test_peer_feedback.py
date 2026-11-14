"""Checkpoint 2 peer feedback: subgroup concentration, consistent next-step wording, why a preview stays Conditional."""
import warnings

import pandas as pd

from tripwire.findings import _concentration
from tripwire.next_steps import build_plan
from tripwire.repair_preview import _why_not_ready


def _clin(labels):
    return pd.DataFrame({"sampleID": [f"S{i}" for i in range(len(labels))], "PAM50Call_RNAseq": labels})


def test_rare_subtype_concentration_is_named():
    clin = _clin(["Her2"] * 8 + ["LumA"] * 92)
    s = _concentration([f"S{i}" for i in range(5)], clin)
    assert "All 5 are Her2" in s and "8.0%" in s and "one subgroup" in s


def test_no_concentration_for_mixed_common_or_tiny_groups():
    clin = _clin(["Her2"] * 8 + ["LumA"] * 92)
    assert _concentration(["S0", "S1", "S50"], clin) == ""          # mixed
    assert _concentration(["S10", "S11", "S12", "S13"], clin) == ""  # LumA is common
    assert _concentration(["S0", "S1"], clin) == ""                  # too few to say


def test_flag_wording_matches_conditional_verdict():
    doc = {"analyses": [{"id": "A1", "verdict": "Conditional"}],
           "findings": [{"id": "F3", "severity": "medium", "summary": "5 sample(s) lost data.", "affects_analyses": ["A1"]}],
           "repairs": [{"id": "R3", "action": "flag_for_review", "addresses": ["F3"], "targets": []}], "questions": []}
    why = build_plan(doc)["steps"][0]["why"]
    assert "on hold" not in why and "A1 can be used with care (Conditional)" in why


def test_flag_wording_holds_blocked_analysis():
    doc = {"analyses": [{"id": "A1", "verdict": "Blocked"}],
           "findings": [{"id": "F3", "severity": "high", "summary": "x.", "affects_analyses": ["A1"]}],
           "repairs": [{"id": "R3", "action": "flag_for_review", "addresses": ["F3"], "targets": []}], "questions": []}
    assert "keep A1 on hold (Blocked)" in build_plan(doc)["steps"][0]["why"]


def test_why_not_ready_names_sample_gap_and_open_repairs():
    class R:
        def __init__(self, n): self.n = n
    import tripwire.repair_preview as rp
    orig = rp.public
    rp.public = lambda r: {"n_samples": r.n}
    try:
        s = _why_not_ready(R(698), R(694), ["R3"])
    finally:
        rp.public = orig
    assert "694 samples, release A has 698" in s and "R3" in s


def test_restore_preview_does_not_fragment(tmp_path):
    from tripwire.repair_preview import _overlay
    a_prot = pd.DataFrame({f"S{i}": range(3) for i in range(150)})
    b_prot = a_prot.copy()

    class Rel:
        def __init__(self, prot):
            self.path, self.name, self.protein = tmp_path, "x", prot
            self.clinical = pd.DataFrame({"sampleID": list(prot.columns)})
    targets = [{"kind": "sample", "id": f"S{i}", "file": "protein_rppa.tsv.gz"} for i in range(150)]
    with warnings.catch_warnings():
        warnings.simplefilter("error", pd.errors.PerformanceWarning)
        import tripwire.repair_preview as rp
        orig = rp.Release
        rp.Release = lambda path, name=None: type("O", (), {})()
        try:
            ov = _overlay(Rel(a_prot), Rel(b_prot), "restore_from_previous_release", targets)
        finally:
            rp.Release = orig
    assert sorted(ov.protein.columns) == sorted(a_prot.columns)


def test_subgroup_chance_is_corrected_for_the_subtypes_tested():
    # 8% Her2, 12% Basal, 80% LumA: Her2 and Basal are the rare subtypes the rule tests (at most 25%)
    clin = _clin(["Her2"] * 8 + ["Basal"] * 12 + ["LumA"] * 80)
    s = _concentration([f"S{i}" for i in range(5)], clin)
    expected = round(1 / (0.08 ** 5 + 0.12 ** 5))   # not 1 / 0.08**5, the uncorrected single-subtype figure
    assert f"1 time in {expected:,}" in s and "2 subtypes tested" in s
