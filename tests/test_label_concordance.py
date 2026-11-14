"""Receptor labels that contradict the tumor's own molecular data, including errors already in the trusted release."""
import numpy as np
import pandas as pd

from conftest import make_release, write
from tripwire.concordance import ER_COL, er_discordance
from tripwire.detect import detect_changes
from tripwire.findings import build
from tripwire.release import Release
from tripwire.validate import challenge_dir, validate


def _clean(tmp_path):
    """A release whose ER labels agree with ER-alpha protein: positives high, negatives low."""
    a = tmp_path / "A"
    clinical, protein = make_release(a)
    rng = np.random.default_rng(1)
    pos = clinical[ER_COL] == "Positive"
    ids = clinical["sampleID"]
    er = pd.Series(np.where(pos, rng.normal(2.0, 0.3, len(ids)), rng.normal(-1.0, 0.3, len(ids))), index=ids.values)
    protein.loc["ERALPHA", er.index] = er.values
    write(a, clinical, protein)
    return a, clinical, protein


def test_consistent_labels_raise_nothing(tmp_path):
    a, _, _ = _clean(tmp_path)
    assert er_discordance(Release(a)) == []


def test_mislabelled_sample_is_flagged_with_evidence(tmp_path):
    a, clinical, protein = _clean(tmp_path)
    neg = clinical.loc[clinical[ER_COL] == "Negative", "sampleID"].iloc[0]
    protein.loc["ERALPHA", neg] = 2.4          # ER-negative label, ER-positive-level protein
    write(a, clinical, protein)
    flagged = er_discordance(Release(a))
    assert [d.sample for d in flagged] == [neg]
    assert "labelled ER-negative" in flagged[0].evidence and "typical ER-positive level" in flagged[0].evidence


def test_error_already_in_trusted_release_becomes_a_finding(tmp_path):
    a, clinical, protein = _clean(tmp_path)
    neg = clinical.loc[clinical[ER_COL] == "Negative", "sampleID"].iloc[0]
    protein.loc["ERALPHA", neg] = 2.4
    write(a, clinical, protein)
    b = tmp_path / "B"
    write(b, clinical, protein)               # nothing changed between releases
    ra, rb = Release(a), Release(b)
    doc = build(detect_changes(ra, rb), ra, rb)
    f = next(f for f in doc["findings"] if f["kind"] == "label_conflict")
    assert "already like this in release" in f["summary"] and f["needs_human_review"]
    r = next(r for r in doc["repairs"] if f["id"] in r["addresses"])
    assert r["action"] == "flag_for_review"
    q = {x["id"]: x for x in doc["questions"]}
    ck = {c["name"]: c for c in q["predict_er_from_protein"]["checks"]}
    assert ck["label_concordance"]["status"] == "fixable" and neg in ck["label_concordance"]["summary"]
    if challenge_dir():
        assert validate(doc) == []
