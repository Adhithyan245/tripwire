"""A malformed release must never stop Driftwire from writing findings.json."""
import pandas as pd

from conftest import write
from tripwire.detect import detect_changes
from tripwire.findings import build
from tripwire.release import Release
from tripwire.validate import challenge_dir, validate


def run(a, b):
    doc = build(detect_changes(Release(a), Release(b)), Release(a), Release(b))
    if challenge_dir():
        assert validate(doc) == []
    return doc


def an(doc, aid):
    return next(x for x in doc["analyses"] if x["id"] == aid)


def test_repeated_clinical_row_does_not_crash(releases):
    a, b, clinical, protein = releases
    write(b, pd.concat([clinical, clinical.iloc[[5]]], ignore_index=True), protein)
    doc = run(a, b)
    assert any(f["kind"] == "duplicate" for f in doc["findings"])
    assert an(doc, "A1")["verdict"] and an(doc, "A2")["verdict"]


def test_missing_eralpha_row_is_reported_not_a_crash(releases):
    a, b, clinical, protein = releases
    write(b, clinical, protein.drop(index="ERALPHA"))
    doc = run(a, b)
    a1 = an(doc, "A1")
    assert a1["verdict"] == "Insufficient Evidence" and "ERALPHA" in a1["why"]
    lost = [f for f in doc["findings"] if f["kind"] == "missing_data"]
    assert lost and "A1" in lost[0]["affects_analyses"]
    assert an(doc, "A2")["verdict"] == "Ready"


def test_missing_er_column_is_reported_not_a_crash(releases):
    a, b, clinical, protein = releases
    write(b, clinical.drop(columns=["breast_carcinoma_estrogen_receptor_status"]), protein)
    doc = run(a, b)
    assert an(doc, "A1")["verdict"] == "Insufficient Evidence"
    assert any("breast_carcinoma_estrogen_receptor_status" in f["summary"] or
               any("breast_carcinoma_estrogen_receptor_status" in str(e.get("note", "")) for e in f["evidence"])
               for f in doc["findings"])
