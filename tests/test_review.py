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
    flagged = [f["id"] for f in doc["findings"] if f.get("needs_human_review")]
    assert review_status(doc)["open"] == flagged and "F1" in flagged
    decide = {r["id"]: {"decision": "reject", "reason": "intended relabel", "reviewer_role": "PI"} for r in doc["repairs"]}
    new = apply_decisions(doc, decide)
    assert review_status(new)["open"] == []


@pytest.mark.skipif(challenge_dir() is None, reason="challenge repo not cloned next to this one")
def test_decisions_pass_the_official_validator(doc):
    rid = doc["repairs"][0]["id"]
    new = apply_decisions(doc, {rid: {"decision": "approve", "reason": "matches lab notes", "reviewer_role": "curator"}})
    assert validate(new) == []


def test_a_decision_is_a_record_and_never_changes_a_verdict(doc):
    """By design: review records who decided what and why; verdicts describe the data as delivered."""
    from tripwire.next_steps import build_plan
    rid = doc["repairs"][0]["id"]
    new = apply_decisions(doc, {rid: {"decision": "approve", "reason": "confirmed", "reviewer_role": "curator"}})
    assert new["decisions"][0]["original_preserved"] is True
    assert new["verdict"] == doc["verdict"]
    assert [a["verdict"] for a in new["analyses"]] == [a["verdict"] for a in doc["analyses"]]
    assert [q["verdict"] for q in new["questions"]] == [q["verdict"] for q in doc["questions"]]
    assert new["findings"] == doc["findings"] and build_plan(new) == build_plan(doc)
    assert len(review_status(new)["open"]) == len(review_status(doc)["open"]) - 1
