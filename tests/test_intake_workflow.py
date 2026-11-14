"""Two-agent intake workflow: consent, untrusted model output, ambiguity, approvals, the candidate copy and the
real firewall run. Every model call is mocked (no network, no key); every input is synthetic."""
from __future__ import annotations

import hashlib
import json
import os
import pathlib

import pytest

from intake_prototype import agents as ag
from intake_prototype.demo import make_synthetic_inputs, scripted_transport
from intake_prototype.upload import UploadError
from intake_prototype.workflow import IntakeWorkflow, WorkflowError, _fingerprint, safe_session_root
from tripwire.config import VERDICT_ORDER

OWNER = "data owner (test)"
Q1 = "What is the PAM50 subtype mix of primary tumors in the new release?"
Q2 = "Does ER-alpha protein differ between ER-positive and ER-negative tumors?"


class FakeAI:
    """Records every request body; answers like the scripted demo unless overridden."""

    def __init__(self, prep=None, question=None, raw=None):
        self.prep, self.question, self.raw, self.bodies = prep, question, raw, []

    def __call__(self, url, headers, body, timeout):
        self.bodies.append(body)
        if self.raw is not None:
            return self.raw
        system = json.loads(body)["messages"][0]["content"]
        override = self.prep if system == ag.PREPARATION_SYSTEM else self.question
        if override is None:
            return scripted_transport(url, headers, body, timeout)
        return json.dumps({"choices": [{"message": {"content": json.dumps(override)}}]}).encode()


def _sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.fixture
def env(tmp_path):
    paths = make_synthetic_inputs(tmp_path / "inputs")
    wf = IntakeWorkflow.create(tmp_path / "sessions", allow_system_temp=True)
    wf.upload(paths["upload"].read_bytes(), paths["upload"].name)
    return wf, paths


def _consent(wf, agent):
    prev = wf.preview_ai_payload(agent)
    wf.grant_consent(agent, granted_by=OWNER, payload_sha256=prev["sha256"])


def _review_all(wf, view):
    for p in view["proposals"]:
        wf.decide_mapping(p["source"], "accept", decided_by=OWNER)
    for c in view["clarifications"]:
        wf.answer_clarification(c["id"], "Same definition as the target field.", answered_by=OWNER)


def _prepared(wf, ai):
    _consent(wf, ag.PREPARATION)
    _review_all(wf, wf.propose_mappings(transport=ai))
    wf.complete_mapping_review(reviewed_by=OWNER)
    wf.approve(data_owner_confirmed=True, approved_by=OWNER)
    return wf.prepare()


def _confirmed(wf, paths, ai, card="subtype_mix"):
    _prepared(wf, ai)
    wf.bind_releases(paths["trusted"], paths["candidate"], upload_belongs_to_candidate=True, confirmed_by=OWNER)
    wf.set_question(Q1)
    _consent(wf, ag.QUESTION)
    wf.propose_question(transport=ai)
    return wf.confirm_question(card, confirmed_by="researcher (test)")


# ------------------------------------------------------------ consent and metadata-only payloads

def test_no_consent_means_no_call(env):
    wf, _ = env
    ai = FakeAI()
    with pytest.raises(ag.AgentError, match="no consent"):
        wf.propose_mappings(transport=ai)
    assert ai.bodies == [] and wf.state == "uploaded"


def test_consent_must_match_shown_payload(env):
    wf, _ = env
    with pytest.raises(WorkflowError, match="changed since it was shown"):
        wf.grant_consent(ag.PREPARATION, granted_by=OWNER, payload_sha256="0" * 64)
    with pytest.raises(WorkflowError):
        wf.grant_consent(ag.PREPARATION, granted_by=" ", payload_sha256=wf.preview_ai_payload("preparation")["sha256"])


def test_missing_api_key_without_transport_fails_before_network(env, monkeypatch):
    wf, _ = env
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(ag, "_default_transport", lambda *a: pytest.fail("network used"))
    _consent(wf, ag.PREPARATION)
    with pytest.raises(ag.AgentError, match="OPENAI_API_KEY"):
        wf.propose_mappings()
    assert wf.state == "uploaded"


def test_agents_receive_metadata_only_and_separately(env):
    wf, paths = env
    ai = FakeAI()
    _confirmed(wf, paths, ai)
    assert len(ai.bodies) == 2
    prep, quest = (json.loads(b) for b in ai.bodies)
    assert prep["messages"][0]["content"] == ag.PREPARATION_SYSTEM
    assert quest["messages"][0]["content"] == ag.QUESTION_SYSTEM
    for body in ai.bodies:
        text = body.decode()
        assert "TCGA-ZZ" not in text  # no sample barcodes (cell values) in any payload
        assert "release-B-clinical-upload.csv" not in text  # filename not sent
    sent = json.loads(quest["messages"][1]["content"])
    assert set(sent) == {"task", "question", "supported_cards", "prepared_clinical_columns",
                         "candidate_release_files", "note"}  # no findings, no values
    assert sent["prepared_clinical_columns"][0] == "sampleID"


def test_question_change_invalidates_interpretation_and_consent(env):
    wf, paths = env
    ai = FakeAI()
    _confirmed(wf, paths, ai)
    assert wf.state == "question_confirmed"
    wf.set_question(Q2)
    ev = wf.evidence()
    assert wf.state == "prepared" and ev["question_confirmation"] is None and ev["question_proposal"] is None
    n = len(ai.bodies)
    with pytest.raises(ag.AgentError, match="changed since consent"):
        wf.propose_question(transport=ai)
    assert len(ai.bodies) == n
    _consent(wf, ag.QUESTION)
    wf.propose_question(transport=FakeAI(question={"card_id": "er_protein_by_er_status", "explanation": "ER"}))
    assert wf.evidence()["question_proposal"]["card_id"] == "er_protein_by_er_status"


# ------------------------------------------------------------ untrusted model output

def test_hallucinated_mappings_are_rejected(env):
    wf, _ = env
    ai = FakeAI(prep={"mappings": [
        {"source": "Sample Barcode", "target": "sampleID", "confidence": "high"},
        {"source": "Ghost column", "target": "age", "confidence": "high"},
        {"source": "Age at dx", "target": "date_of_birth", "confidence": "high"},
        {"source": "Subtype call", "target": "sampleID", "confidence": "high"},
        {"source": "ER status (IHC)", "target": "breast_carcinoma_estrogen_receptor_status", "confidence": "sure"},
        "not an object"], "clarification_questions": "not a list"})
    _consent(wf, ag.PREPARATION)
    view = wf.propose_mappings(transport=ai)
    assert [p["source"] for p in view["proposals"]] == ["Sample Barcode"]
    assert len(view["rejected"]) == 5
    assert all(r["source"] in (None, *wf.evidence()["upload"]["columns"]) for r in view["rejected"])
    assert view["agent_errors"]


@pytest.mark.parametrize("raw", [b"not json", json.dumps({"choices": []}).encode(),
                                 json.dumps({"choices": [{"message": {"content": "[1, 2]"}}]}).encode(),
                                 b"x" * (ag.MAX_RESPONSE_BYTES + 10)])
def test_malformed_model_output_changes_nothing(env, raw):
    wf, _ = env
    _consent(wf, ag.PREPARATION)
    with pytest.raises(ag.AgentError):
        wf.propose_mappings(transport=FakeAI(raw=raw))
    assert wf.state == "uploaded" and wf.evidence()["mapping"] is None


def test_unknown_question_card_fails_closed(env):
    wf, paths = env
    _prepared(wf, FakeAI())
    wf.set_question("Predict everything about every patient")
    _consent(wf, ag.QUESTION)
    view = wf.propose_question(transport=FakeAI(question={"card_id": "predict_everything", "explanation": "x"}))
    assert view["proposal"]["card_id"] is None and view["proposal"]["agent_errors"]
    with pytest.raises(WorkflowError, match="not a supported"):
        wf.confirm_question("predict_everything", confirmed_by="researcher")
    with pytest.raises(WorkflowError, match="no card is never assumed"):
        wf.confirm_question(None, confirmed_by="researcher")
    assert wf.state == "question_proposed"


def test_ambiguous_question_needs_answer_and_human_choice(env):
    wf, _ = env
    _prepared(wf, FakeAI())
    wf.set_question("How are the subtypes doing?")
    _consent(wf, ag.QUESTION)
    view = wf.propose_question(transport=FakeAI(question={
        "card_id": None, "explanation": "Could be subtype mix or survival by subtype.",
        "clarification_questions": ["Do you mean the subtype shares or survival by subtype?"]}))
    cid = view["clarifications"][0]["id"]
    with pytest.raises(WorkflowError, match="unanswered"):
        wf.confirm_question("subtype_mix", confirmed_by="researcher")
    wf.answer_clarification(cid, "Subtype shares.", answered_by="researcher")
    conf = wf.confirm_question("subtype_mix", confirmed_by="researcher")
    assert conf["matches_proposal"] is False and conf["proposed_card_id"] is None


# ------------------------------------------------------------ review, ambiguity and approval

def test_unresolved_ambiguity_is_never_approved(env):
    wf, _ = env
    _consent(wf, ag.PREPARATION)
    view = wf.propose_mappings(transport=FakeAI())
    assert view["clarifications"]  # agent question plus a system question for the medium-confidence mapping
    with pytest.raises(WorkflowError, match="undecided"):
        wf.complete_mapping_review(reviewed_by=OWNER)
    for p in view["proposals"]:
        wf.decide_mapping(p["source"], "accept", decided_by=OWNER)
    with pytest.raises(WorkflowError, match="unanswered clarifications"):
        wf.complete_mapping_review(reviewed_by=OWNER)
    with pytest.raises(WorkflowError, match="cannot be empty"):
        wf.answer_clarification(view["clarifications"][0]["id"], "   ", answered_by=OWNER)
    with pytest.raises(WorkflowError):
        wf.approve(data_owner_confirmed=True, approved_by=OWNER)  # review not complete
    assert wf.state == "mapping_proposed"


def test_data_owner_confirmation_is_mandatory(env):
    wf, _ = env
    _consent(wf, ag.PREPARATION)
    _review_all(wf, wf.propose_mappings(transport=FakeAI()))
    wf.complete_mapping_review(reviewed_by=OWNER)
    for bad in (False, None, "yes", 1):
        with pytest.raises(WorkflowError, match="mandatory"):
            wf.approve(data_owner_confirmed=bad, approved_by=OWNER)
    with pytest.raises(WorkflowError):
        wf.prepare()
    wf.approve(data_owner_confirmed=True, approved_by=OWNER)
    assert wf.state == "approved"


def test_changing_a_decision_after_approval_reopens_review(env):
    wf, _ = env
    _prepared(wf, FakeAI())
    assert (wf.dir / "prepared" / "clinical.tsv").exists()
    wf.decide_mapping("Age at dx", "reject", decided_by=OWNER)
    ev = wf.evidence()
    assert wf.state == "mapping_proposed" and ev["approval"] is None and ev["prepared"] is None
    assert not (wf.dir / "prepared").exists()


def test_missing_sample_id_blocks_review(env):
    wf, _ = env
    wf.start_manual_mapping()
    wf.decide_mapping("Age at dx", "edit", "age", decided_by=OWNER)
    with pytest.raises(WorkflowError, match="sampleID"):
        wf.complete_mapping_review(reviewed_by=OWNER)
    with pytest.raises(WorkflowError, match="fixed supported schema"):
        wf.decide_mapping("Subtype call", "edit", "OS", decided_by=OWNER)


def test_manual_path_without_ai_preserves_values_and_original(env, tmp_path):
    wf, paths = env
    original = paths["upload"].read_bytes()
    wf.start_manual_mapping()
    for src, tgt in {"Sample Barcode": "sampleID", "Subtype call": "PAM50Call_RNAseq"}.items():
        wf.decide_mapping(src, "edit", tgt, decided_by=OWNER)
    wf.complete_mapping_review(reviewed_by=OWNER)
    wf.approve(data_owner_confirmed=True, approved_by=OWNER)
    prep = wf.prepare()
    assert prep["columns"] == ["sampleID", "ER status (IHC)", "PAM50Call_RNAseq", "Age at dx"]
    assert prep["values_preserved"] and wf.evidence()["ai_calls"] == []
    import pandas as pd
    before = pd.read_csv(paths["upload"], dtype=str, keep_default_na=False)
    after = pd.read_csv(wf.dir / "prepared" / "clinical.tsv", sep="\t", dtype=str, keep_default_na=False)
    assert before.to_numpy().tolist() == after.to_numpy().tolist()
    assert paths["upload"].read_bytes() == original
    assert (wf.dir / "upload" / "original.csv").read_bytes() == original


def test_upload_rejects_unsupported_files(env):
    wf, _ = env
    with pytest.raises(UploadError):
        wf.upload(b"a,b\n1,2\n", "table.xlsx")
    assert wf.state == "uploaded"


def test_reupload_restarts_and_unbinds_releases(env):
    wf, paths = env
    _prepared(wf, FakeAI())
    wf.bind_releases(paths["trusted"], paths["candidate"], upload_belongs_to_candidate=True, confirmed_by=OWNER)
    wf.upload(paths["upload"].read_bytes(), "again.csv")
    ev = wf.evidence()
    assert wf.state == "uploaded" and ev["releases"] is None and ev["mapping"] is None and ev["approval"] is None


# ------------------------------------------------------------ releases and the firewall run (real engine)

def test_full_run_on_real_engine_leaves_originals_unchanged(env):
    wf, paths = env
    b = paths["candidate"]
    (b / "README.txt").write_text("synthetic notes\n")
    (b / "CHANGES.json").write_text("{}")  # stands in for an answer key: never copied or hashed
    before = {k: _fingerprint(paths[k]) for k in ("trusted", "candidate")}
    upload_sha = _sha(paths["upload"])
    _confirmed(wf, paths, FakeAI())
    run = wf.run_firewall()
    assert run["status"] == "complete" and run["verdict"] in VERDICT_ORDER
    assert run["question_verdict"] in VERDICT_ORDER and run["n_findings"] >= 1  # four relabelled subtypes
    assert run["originals_unchanged"] and run["review"] == "pending" and wf.state == "review_pending"
    build = run["candidate_build"]
    assert build["kept_from_candidate"] == ["README.txt", "protein_rppa.tsv.gz"]
    assert build["candidate_had_clinical"] is False and "CHANGES.json" in build["excluded"]
    assert {k: _fingerprint(paths[k]) for k in ("trusted", "candidate")} == before
    assert not (b / "clinical.tsv").exists() and _sha(paths["upload"]) == upload_sha
    assert not (wf.dir / "work").exists() or not any((wf.dir / "work").iterdir())
    assert wf.findings()["verdict"] == run["verdict"]


def test_existing_candidate_clinical_is_replaced_only_in_the_copy(env):
    wf, paths = env
    b = paths["candidate"]
    (b / "clinical.tsv").write_bytes((paths["trusted"] / "clinical.tsv").read_bytes())
    sha = _sha(b / "clinical.tsv")
    _confirmed(wf, paths, FakeAI())
    run = wf.run_firewall(link_mode="symlink")
    assert run["status"] == "complete" and run["candidate_build"]["candidate_had_clinical"] is True
    assert run["sample_overlap"]["n_shared"] == run["sample_overlap"]["n_uploaded"]
    assert _sha(b / "clinical.tsv") == sha and run["originals_unchanged"]


def test_baseline_only_path(env):
    wf, paths = env
    _prepared(wf, FakeAI())
    wf.bind_releases(paths["trusted"], paths["candidate"], upload_belongs_to_candidate=True, confirmed_by=OWNER)
    wf.confirm_question(None, confirmed_by="researcher", baseline_only=True)
    run = wf.run_firewall()
    assert run["status"] == "complete" and run["card_id"] is None and run["question_verdict"] is None


def test_belonging_confirmation_and_valid_folders_required(env, tmp_path):
    wf, paths = env
    with pytest.raises(WorkflowError, match="belongs"):
        wf.bind_releases(paths["trusted"], paths["candidate"], upload_belongs_to_candidate=False, confirmed_by=OWNER)
    with pytest.raises(WorkflowError, match="not found"):
        wf.bind_releases(tmp_path / "nope", paths["candidate"], upload_belongs_to_candidate=True, confirmed_by=OWNER)
    with pytest.raises(WorkflowError, match="separate"):
        wf.bind_releases(paths["trusted"], paths["trusted"], upload_belongs_to_candidate=True, confirmed_by=OWNER)


def test_no_verdict_when_inputs_missing(env):
    wf, _ = env
    _prepared(wf, FakeAI())
    with pytest.raises(WorkflowError):
        wf.run_firewall()  # question not confirmed
    wf.confirm_question(None, confirmed_by="researcher", baseline_only=True)
    with pytest.raises(WorkflowError, match="releases not bound"):
        wf.run_firewall()
    assert wf.state == "question_confirmed" and wf.evidence()["run"] is None


def test_engine_failure_gives_no_verdict_and_cleans_up(env, monkeypatch):
    wf, paths = env
    _confirmed(wf, paths, FakeAI())
    import tripwire.api

    def boom(*a, **k):
        raise RuntimeError("could not parse value TCGA-ZZ-0001-01")
    monkeypatch.setattr(tripwire.api, "check", boom)
    run = wf.run_firewall()
    assert run["status"] == "failed" and run["verdict"] is None and wf.state == "firewall_failed"
    assert "TCGA" not in run["error"] and "RuntimeError" in run["error"]
    assert not (wf.dir / "work" / run["run_id"]).exists()
    with pytest.raises(WorkflowError):
        wf.record_review("accept_result", reason="looks fine", reviewer_role="curator")


def test_release_changed_after_binding_gives_no_verdict(env):
    wf, paths = env
    _confirmed(wf, paths, FakeAI())
    (paths["candidate"] / "extra.tsv").write_text("x\ty\n1\t2\n")
    run = wf.run_firewall()
    assert run["status"] == "failed" and run["verdict"] is None and "changed since" in run["error"]


def test_review_is_explicit_and_separate(env):
    wf, paths = env
    _confirmed(wf, paths, FakeAI())
    wf.run_firewall()
    with pytest.raises(WorkflowError):
        wf.record_review("approve_everything", reason="x", reviewer_role="curator")
    with pytest.raises(WorkflowError):
        wf.record_review("accept_result", reason=" ", reviewer_role="curator")
    wf.record_review("request_more_evidence", reason="check the relabelled samples", reviewer_role="curator")
    assert wf.state == "review_pending"
    rev = wf.record_review("accept_result", reason="relabels confirmed by curator", reviewer_role="curator")
    assert wf.state == "reviewed" and rev["repairs_applied"] is False and len(wf.evidence()["reviews"]) == 2


# ------------------------------------------------------------ session storage, audit, secrets, cleanup

def test_session_root_refuses_tmp():
    for bad in ("/tmp/intake", "/private/tmp/intake"):
        with pytest.raises(WorkflowError, match="refusing"):
            safe_session_root(bad)


def test_audit_chain_has_no_values_answers_or_key(env, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-do-not-leak-123")
    wf, paths = env
    _confirmed(wf, paths, FakeAI())
    wf.run_firewall()
    audit = (wf.dir / "audit.jsonl").read_text()
    evidence = (wf.dir / "evidence.json").read_text()
    assert "sk-test-do-not-leak-123" not in audit + evidence
    assert "TCGA-ZZ" not in audit and "Same definition as the target field." not in audit
    assert "Same definition as the target field." in evidence  # human answers are captured in the evidence
    prev = "0" * 64
    for line in audit.splitlines():
        e = json.loads(line)
        h = e.pop("hash")
        assert e["prev"] == prev
        assert hashlib.sha256(json.dumps(e, sort_keys=True, ensure_ascii=False).encode()).hexdigest() == h
        prev = h
    if os.name != "nt":
        assert (wf.dir / "evidence.json").stat().st_mode & 0o077 == 0


def test_load_resumes_and_close_purges_patient_data(env):
    wf, paths = env
    _consent(wf, ag.PREPARATION)
    _review_all(wf, wf.propose_mappings(transport=FakeAI()))
    wf.complete_mapping_review(reviewed_by=OWNER)
    wf.approve(data_owner_confirmed=True, approved_by=OWNER)
    again = IntakeWorkflow.load(wf.dir, allow_system_temp=True)
    assert again.state == "approved"
    again.prepare()  # re-reads the stored original upload and checks its hash
    closed = again.close(purge_findings=True)
    assert set(closed["removed"]) >= {"upload", "prepared"}
    assert not (again.dir / "upload").exists() and (again.dir / "evidence.json").exists()
    with pytest.raises(WorkflowError, match="closed"):
        again.set_question(Q1)


def test_low_level_agents_refuse_network_without_explicit_consent():
    from intake_prototype import agents
    sent = []
    def transport(*args):
        sent.append(True)
        return b'{}'
    for call in (agents.call_preparation_agent, agents.call_question_agent):
        with pytest.raises(agents.AgentError, match='consent'):
            call({}, transport=transport)
    assert sent == []
