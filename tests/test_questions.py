import pytest

from conftest import write
from test_impact_verdicts import er_pair, swapped
from tripwire import questions
from tripwire.contract import Change
from tripwire.findings import build
from tripwire.release import Release
from tripwire.validate import challenge_dir, validate
from tripwire.verdicts import CheckResult


def qv(doc):
    return {q["id"]: q for q in doc["questions"]}


@pytest.fixture
def all_checks_pass(monkeypatch):
    """Stand-in for Role 1's leakage and site checks, so tests can isolate the release part of the verdict."""
    for name in ("patient_leakage", "site_confounding"):
        monkeypatch.setitem(questions.CHECKS, name, lambda card, r, n=name: CheckResult(n, "pass", "stub pass"))


def test_same_release_different_question_different_verdict(releases, all_checks_pass):
    a, b, clinical, protein = releases
    x, y = er_pair(clinical, protein)
    write(b, clinical, swapped(protein, x, y))
    ch = [Change(x, "swap", "protein_rppa.tsv.gz", related_sample_id=y)]
    q = qv(build(ch, Release(a), Release(b)))
    assert q["subtype_mix"]["verdict"] == "Ready"
    assert q["er_protein_by_er_status"]["verdict"] in ("Conditional", "Blocked")          # follows A1's tolerance
    assert q["predict_er_from_protein"]["verdict"] == "Blocked"                           # training: integrity blocks
    assert "swap" in q["predict_er_from_protein"]["why"]
    assert q["predict_er_from_protein"]["relevant_findings"] == ["F1"]
    assert q["subtype_mix"]["relevant_findings"] == []


def test_missing_input_says_data_cannot_answer(releases):
    a, _, _, _ = releases
    q = qv(build([], Release(a), Release(a, name="again")))["predict_er_from_rna"]
    assert q["verdict"] == "Insufficient Evidence" and "can't answer" in q["why"]
    assert q["coverage"]["unavailable"] == q["required_checks"]


def test_unbuilt_checks_are_never_a_pass(releases):
    a, _, _, _ = releases
    q = qv(build([], Release(a), Release(a, name="again")))["predict_er_from_protein"]
    assert q["release_part"]["verdict"] == "Ready"
    assert q["verdict"] == "Insufficient Evidence"
    assert set(q["coverage"]["unavailable"]) == {"patient_leakage", "site_confounding"}


def test_training_card_ready_when_nothing_changed_and_checks_pass(releases, all_checks_pass):
    a, _, _, _ = releases
    assert qv(build([], Release(a), Release(a, name="again")))["predict_er_from_protein"]["verdict"] == "Ready"


def test_undetected_input_change_blocks_training_card(releases, all_checks_pass):
    a, b, clinical, protein = releases
    p2 = protein.copy()
    p2.loc["AKT", p2.columns[0]] += 5  # a field no analysis uses, but the training card reads every protein
    write(b, clinical, p2)
    q = qv(build([], Release(a), Release(b)))
    assert q["predict_er_from_protein"]["verdict"] == "Blocked"
    assert "no detected change explains it" in q["predict_er_from_protein"]["why"]
    assert q["er_protein_by_er_status"]["verdict"] == "Ready"  # ERALPHA untouched


def test_reordered_copy_keeps_training_card_ready(releases, all_checks_pass):
    a, b, clinical, protein = releases
    write(b, clinical.sample(frac=1, random_state=2), protein[protein.columns[::-1]])
    assert qv(build([], Release(a), Release(b)))["predict_er_from_protein"]["verdict"] == "Ready"


def test_non_integrity_change_is_conditional_for_training(releases, all_checks_pass):
    a, b, clinical, protein = releases
    gone = protein.columns[:2]
    write(b, clinical, protein.drop(columns=gone))
    ch = [Change(s, "disappeared", "protein_rppa.tsv.gz") for s in gone]
    assert qv(build(ch, Release(a), Release(b)))["predict_er_from_protein"]["verdict"] == "Conditional"


def test_small_class_is_insufficient(releases):
    a, b, clinical, protein = releases
    c2 = clinical.copy()
    neg = c2.index[c2.breast_carcinoma_estrogen_receptor_status == "Negative"][3:]
    c2.loc[neg, "breast_carcinoma_estrogen_receptor_status"] = None
    write(b, c2, protein)
    s = questions.sample_size(questions.BY_ID["predict_er_from_protein"], Release(b))
    assert s.status == "insufficient" and "Negative" in s.summary


def test_question_flag_sets_top_level(releases):
    a, b, clinical, protein = releases
    x, y = er_pair(clinical, protein)
    write(b, clinical, swapped(protein, x, y))
    ch = [Change(x, "swap", "protein_rppa.tsv.gz", related_sample_id=y)]
    d1 = build(ch, Release(a), Release(b), question="subtype_mix")
    d2 = build(ch, Release(a), Release(b), question="predict_er_from_protein")
    assert d1["verdict"] == "Ready" and d2["verdict"] == "Blocked"
    assert "subtype mix" in d1["question"]
    with pytest.raises(ValueError):
        build(ch, Release(a), Release(b), question="cure_cancer")


@pytest.mark.skipif(challenge_dir() is None, reason="challenge repo not cloned next to this one")
def test_question_output_validates(releases):
    a, b, clinical, protein = releases
    x, y = er_pair(clinical, protein)
    write(b, clinical, swapped(protein, x, y))
    doc = build([Change(x, "swap", "protein_rppa.tsv.gz", related_sample_id=y)], Release(a), Release(b),
                question="predict_er_from_protein")
    assert validate(doc) == []
