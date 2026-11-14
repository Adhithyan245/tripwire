"""Pure helpers of app/agent_intake_tab.py (no Streamlit, no model calls, no data)."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))

import agent_intake_tab as t  # noqa: E402
from intake_prototype import agents as ag  # noqa: E402
from intake_prototype.upload import UploadError  # noqa: E402
from intake_prototype.workflow import STATES, WorkflowError  # noqa: E402


def test_every_state_has_a_title():
    assert all(t.step_title(s) != s for s in STATES)


def test_consent_needs_tick_person_and_current_hash():
    assert t.consent_ready(True, "owner", "abc", "abc")
    assert not t.consent_ready(False, "owner", "abc", "abc")
    assert not t.consent_ready(True, "  ", "abc", "abc")
    assert not t.consent_ready(True, "owner", "abc", "def")  # payload changed since shown
    assert not t.consent_ready(True, "owner", None, None)


def test_proposal_decisions_skip_undecided_and_incomplete_edits():
    calls = t.proposal_decisions({"a": "accept", "b": "", "c": "reject", "d": "edit", "e": "edit"},
                                 {"d": "age", "e": t.UNMAPPED})
    assert calls == [("a", "accept", None), ("c", "reject", None), ("d", "edit", "age")]


def test_manual_decisions_are_explicit_for_every_column():
    assert t.manual_decisions({"id": "sampleID", "x": t.UNMAPPED}) == [("id", "edit", "sampleID"), ("x", "reject", None)]


def test_verdict_summary_keeps_question_and_overall_apart():
    cards = [{"id": "q1", "title": "Card one"}]
    s = t.verdict_summary({"verdict": "Blocked", "question_verdict": "Ready", "card_id": "q1"}, cards)
    assert s == {"overall": "Blocked", "question": "Ready", "card_title": "Card one", "baseline_only": False}
    assert t.verdict_summary({"verdict": "Ready", "question_verdict": "x", "card_id": None,
                              "baseline_only": True}, cards)["question"] is None


def test_friendly_error_hides_unknown_exception_text():
    assert "secret-cell" not in t.friendly_error(RuntimeError("secret-cell"))
    assert t.friendly_error(WorkflowError("reach x first")).endswith("reach x first")
    assert "manual path" in t.friendly_error(ag.AgentError("no key"))
    assert t.friendly_error(UploadError("Upload is empty")).startswith("Can't read")


def test_notices_do_not_overclaim():
    assert "No dataset rows" in t.PRIVACY_NOTICE
    assert "not supported" in t.SCOPE_NOTE
