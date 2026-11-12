import json

import pytest

from conftest import write
from tripwire.contract import Change
from tripwire.findings import build
from tripwire.impact import map_impact
from tripwire.release import Release, content_sha256
from tripwire.validate import challenge_dir, validate
from tripwire.verdicts import CheckResult, coverage, question_verdict


def er_pair(clinical, protein):
    er = clinical.set_index("sampleID")["breast_carcinoma_estrogen_receptor_status"]
    prim = [c for c in protein.columns if c[13:15] == "01"]
    return next(c for c in prim if er[c] == "Positive"), next(c for c in prim if er[c] == "Negative")


def swapped(protein, x, y):
    return protein.rename(columns={x: y, y: x})[protein.columns]


def test_swap_touches_A1_not_A2(releases):
    a, b, clinical, protein = releases
    x, y = er_pair(clinical, protein)
    write(b, clinical, swapped(protein, x, y))
    ch = [Change(x, "swap", "protein_rppa.tsv.gz", related_sample_id=y), Change(y, "swap", "protein_rppa.tsv.gz", related_sample_id=x)]
    imp = map_impact(ch, Release(a), Release(b))
    assert imp["A1"].affected and not imp["A2"].affected
    assert "doesn't read" in imp["A2"].why(2)
    doc = build(ch, Release(a), Release(b))
    v = {an["id"]: an["verdict"] for an in doc["analyses"]}
    assert v["A2"] == "Ready" and v["A1"] in ("Conditional", "Blocked")
    assert len(doc["findings"]) == 1 and doc["findings"][0]["kind"] == "sample_swap"  # one finding per pair
    assert all(f["needs_human_review"] for f in doc["findings"])


def test_pam50_change_touches_A2_not_A1(releases):
    a, b, clinical, protein = releases
    c2 = clinical.copy()
    s = c2.sampleID[0]
    c2.loc[0, "PAM50Call_RNAseq"] = "Basal" if c2.loc[0, "PAM50Call_RNAseq"] != "Basal" else "LumA"
    write(b, c2, protein)
    imp = map_impact([Change(s, "label_change", "clinical.tsv", ["PAM50Call_RNAseq"])], Release(a), Release(b))
    assert imp["A2"].affected and not imp["A1"].affected
    assert "fields it doesn't use" in imp["A1"].why(1)


def test_er_change_on_sample_without_protein_leaves_A1(releases):
    a, b, clinical, protein = releases
    no_prot = next(s for s in clinical.sampleID if s not in protein.columns and s[13:15] == "01")
    imp = map_impact([Change(no_prot, "label_change", "clinical.tsv", ["breast_carcinoma_estrogen_receptor_status"])],
                     Release(a), Release(a))
    assert not imp["A1"].affected and "outside its cohort" in imp["A1"].why(1)


def test_unrelated_file_and_field(releases):
    a, _, _, _ = releases
    ch = [Change("TCGA-T0-0001-01", "value_shift", "copy_number_gistic.tsv.gz"),
          Change("TCGA-T0-0001-01", "value_shift", "protein_rppa.tsv.gz", ["AKT"])]
    imp = map_impact(ch, Release(a), Release(a))
    assert not imp["A1"].affected and not imp["A2"].affected


def test_big_move_is_blocked(releases):
    a, b, clinical, protein = releases
    p2 = protein.copy()
    p2.loc["ERALPHA"] = p2.loc["ERALPHA"] * 0.5  # a unit-like shift
    write(b, clinical, p2)
    ch = [Change(s, "value_shift", "protein_rppa.tsv.gz", ["ERALPHA"]) for s in p2.columns]
    doc = build(ch, Release(a), Release(b))
    a1 = next(x for x in doc["analyses"] if x["id"] == "A1")
    assert a1["verdict"] == "Blocked" and doc["verdict"] == "Blocked"


def test_too_few_samples_is_insufficient(releases):
    a, b, clinical, protein = releases
    er = clinical.set_index("sampleID")["breast_carcinoma_estrogen_receptor_status"]
    negs = [c for c in protein.columns if c[13:15] == "01" and er[c] == "Negative"]
    drop = negs[5:]
    write(b, clinical, protein.drop(columns=drop))
    doc = build([Change(s, "disappeared", "protein_rppa.tsv.gz") for s in drop], Release(a), Release(b))
    assert next(x for x in doc["analyses"] if x["id"] == "A1")["verdict"] == "Insufficient Evidence"


def test_undetected_change_is_caught_by_verification(releases):
    a, b, clinical, protein = releases
    x, y = er_pair(clinical, protein)
    write(b, clinical, swapped(protein, x, y))
    doc = build([], Release(a), Release(b))  # detector saw nothing
    a1 = next(x for x in doc["analyses"] if x["id"] == "A1")
    assert a1["verdict"] == "Blocked" and a1["status"] == "changed"
    assert doc["findings"] and doc["findings"][0]["affects_analyses"] == ["A1"]
    a2 = next(x for x in doc["analyses"] if x["id"] == "A2")
    assert a2["verdict"] == "Ready" and a2["status"] == "unchanged"


def test_no_changes_is_ready(releases):
    a, _, _, _ = releases
    doc = build([], Release(a), Release(a, name="A-again"))
    assert doc["verdict"] == "Ready" and doc["findings"] == [] and doc["repairs"] == []


def test_repairs_point_at_findings(releases):
    a, b, clinical, protein = releases
    write(b, clinical, protein.drop(columns=protein.columns[:3]))
    doc = build([Change(s, "disappeared", "protein_rppa.tsv.gz") for s in protein.columns[:3]], Release(a), Release(b))
    ids = {f["id"] for f in doc["findings"]}
    assert doc["repairs"] and all(set(r["addresses"]) <= ids for r in doc["repairs"])
    assert all("never applied" in r["justification"] for r in doc["repairs"])


@pytest.mark.skipif(challenge_dir() is None, reason="challenge repo not cloned next to this one")
def test_output_passes_official_validator(releases):
    a, b, clinical, protein = releases
    x, y = er_pair(clinical, protein)
    write(b, clinical, swapped(protein, x, y))
    ch = [Change(x, "swap", "protein_rppa.tsv.gz", ["ERALPHA"], related_sample_id=y),
          Change("TCGA-T0-0002-01", "label_change", "clinical.tsv", ["PAM50Call_RNAseq"], before="LumA", after="Basal"),
          Change("TCGA-T0-0003-01", "duplicate", "protein_rppa.tsv.gz", related_sample_id="TCGA-T0-0004-01")]
    doc = build(ch, Release(a), Release(b))
    assert validate(json.loads(json.dumps(doc))) == []
    assert validate(build([], Release(a), Release(b))) == []


def test_content_hash_ignores_line_endings(tmp_path):
    (tmp_path / "lf.tsv").write_bytes(b"a\tb\n1\t2\n")
    (tmp_path / "crlf.tsv").write_bytes(b"a\tb\r\n1\t2\r\n")
    assert content_sha256(tmp_path / "lf.tsv") == content_sha256(tmp_path / "crlf.tsv")


def test_question_verdicts():
    assert question_verdict([CheckResult("sample_size", "pass", "ok")]).verdict == "Ready"
    assert question_verdict([CheckResult("a", "pass", "ok"), CheckResult("patient_leakage", "fixable", "split by patient")]).verdict == "Conditional"
    assert question_verdict([CheckResult("a", "fixable", "x"), CheckResult("b", "fail", "y")]).verdict == "Blocked"
    assert question_verdict([CheckResult("sample_size", "insufficient", "4 per class")]).verdict == "Insufficient Evidence"
    assert question_verdict([]).verdict == "Insufficient Evidence"
    with pytest.raises(ValueError):
        CheckResult("x", "maybe", "")


def test_missing_or_skipped_check_is_never_ready():
    ok = CheckResult("sample_size", "pass", "ok")
    assert question_verdict([ok, CheckResult("site_confounding", "skipped", "no site field")]).verdict == "Insufficient Evidence"
    assert question_verdict([ok], required=["sample_size", "patient_leakage"]).verdict == "Insufficient Evidence"
    assert question_verdict([ok], required=["sample_size"]).verdict == "Ready"
    # a real failure still outranks missing evidence
    assert question_verdict([CheckResult("patient_leakage", "fail", "x")], required=["sample_size"]).verdict == "Blocked"
    cov = coverage([ok, CheckResult("site_confounding", "unavailable", "")], ["sample_size", "patient_leakage"])
    assert cov["pass"] == ["sample_size"] and cov["unavailable"] == ["site_confounding"] and cov["missing"] == ["patient_leakage"]


def test_contract_rejects_unknown_type():
    with pytest.raises(ValueError):
        Change("TCGA-T0-0001-01", "teleported", "clinical.tsv")


def test_reordered_copy_is_a_no_change_control(releases):
    """Same data, rows and columns shuffled: nothing changed, so nothing may be reported."""
    a, b, clinical, protein = releases
    write(b, clinical.sample(frac=1, random_state=1), protein[protein.columns[::-1]].iloc[::-1])
    doc = build([], Release(a), Release(b))
    assert doc["verdict"] == "Ready" and doc["findings"] == []
    assert all(x["status"] == "unchanged" for x in doc["analyses"])
