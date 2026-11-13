import pytest

from conftest import write
from test_impact_verdicts import er_pair, swapped
from tripwire.contract import Change
from tripwire.findings import build
from tripwire.release import Release
from tripwire.review import apply_decisions, review_status
from tripwire.validate import challenge_dir, validate


@pytest.fixture
def doc(releases):
    a, b, clinical, protein = releases
    x, y = er_pair(clinical, protein)
    write(b, clinical, swapped(protein, x, y))
    return build([Change(x, "swap", "protein_rppa.tsv.gz", related_sample_id=y)], Release(a), Release(b))


def test_decisions_recorded_without_touching_the_original(doc):
    rid = doc["repairs"][0]["id"]
    new = apply_decisions(doc, {rid: {"decision": "request_more_evidence", "reason": "ask the provider",
                                      "reviewer_role": "data curator"}})
    assert "decisions" not in doc
    assert new["decisions"] == [{"repair_id": rid, "decision": "request_more_evidence", "reason": "ask the provider",
                                 "reviewer_role": "data curator", "original_preserved": True}]
    assert new["findings"] == doc["findings"] and new["repairs"] == doc["repairs"]  # nothing applied


def test_reason_role_and_known_repair_are_required(doc):
    rid = doc["repairs"][0]["id"]
    for bad in ({"decision": "approve", "reason": "", "reviewer_role": "x"},
                {"decision": "approve", "reason": "ok", "reviewer_role": " "},
                {"decision": "maybe", "reason": "ok", "reviewer_role": "x"}):
        with pytest.raises(ValueError):
            apply_decisions(doc, {rid: bad})
    with pytest.raises(ValueError):
        apply_decisions(doc, {"R99": {"decision": "approve", "reason": "ok", "reviewer_role": "x"}})


def test_review_status_tracks_open_items(doc):
    assert review_status(doc)["open"] == ["F1"]
    rid = doc["repairs"][0]["id"]
    new = apply_decisions(doc, {rid: {"decision": "reject", "reason": "intended relabel", "reviewer_role": "PI"}})
    assert review_status(new)["open"] == []


@pytest.mark.skipif(challenge_dir() is None, reason="challenge repo not cloned next to this one")
def test_decisions_pass_the_official_validator(doc):
    rid = doc["repairs"][0]["id"]
    new = apply_decisions(doc, {rid: {"decision": "approve", "reason": "matches lab notes", "reviewer_role": "curator"}})
    assert validate(new) == []
