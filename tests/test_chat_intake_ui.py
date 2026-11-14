"""Pure helpers of app/chat_intake_tab.py (no Streamlit, no model calls, no data)."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))

import chat_intake_tab as t  # noqa: E402
from intake_prototype import agents as ag  # noqa: E402
from intake_prototype.upload import UploadError  # noqa: E402
from intake_prototype.workflow import WorkflowError  # noqa: E402


def test_parse_command():
    assert t.parse_command("help") == "help"
    assert t.parse_command("  /HELP ") == "help"
    assert t.parse_command("Start over!") == "restart"
    assert t.parse_command("reset") == "restart"
    assert t.parse_command("status") == "status"
    assert t.parse_command("What is ER status?") is None  # an answer, not a command
    assert t.parse_command("") is None and t.parse_command(None) is None


def test_clean_path_strips_quotes_and_expands_home():
    assert t.clean_path('  "/data/release A"  ') == "/data/release A"
    assert t.clean_path("'/x'") == "/x"
    assert t.clean_path("~/r").startswith(str(pathlib.Path.home()))
    assert t.clean_path("   ") == ""


def test_api_key_available():
    assert t.api_key_available({"OPENAI_API_KEY": "sk-x"})
    assert not t.api_key_available({"OPENAI_API_KEY": "  "})
    assert not t.api_key_available({})


def _view(origin="preparation_agent", decisions=None):
    return {"origin": origin, "source_columns": ["id", "er", "age"],
            "proposals": [{"source": "id", "target": "sampleID"}, {"source": "er", "target": "ER_Status"}],
            "decisions": decisions or {}}


def test_next_proposal_skips_decided_and_never_assumes():
    assert t.next_proposal(_view())["source"] == "id"
    assert t.next_proposal(_view(decisions={"id": {}}))["source"] == "er"
    assert t.next_proposal(_view(decisions={"id": {}, "er": {}})) is None


def test_next_manual_column():
    v = _view(origin="manual", decisions={"id": {}})
    v["proposals"] = []
    assert t.next_manual_column(v, finished=False) == "er"
    assert t.next_manual_column(v, finished=True) is None
    assert t.next_manual_column(_view(), finished=False) is None  # AI origin uses proposals


def test_open_clarification():
    cs = [{"id": "C1", "answer": "x"}, {"id": "C2", "answer": None}]
    assert t.open_clarification(cs)["id"] == "C2"
    assert t.open_clarification(cs[:1]) is None


def test_expected_input_flow():
    e = t.expected_input
    assert e("created", {}) == "person"
    me = {"person": "owner"}
    assert e("created", me) is None
    assert e("mapping_proposed", {**me, "open_clarification": {"id": "C1"}}) == "clarification"
    assert e("mapping_proposed", {**me, "open_clarification": {"id": "C1"}, "proposals_left": True}) is None
    assert e("prepared", me) == "path_a"
    assert e("prepared", {**me, "path_a": "/a"}) == "path_b"
    assert e("prepared", {**me, "path_a": "/a", "path_b": "/b"}) is None  # needs explicit belongs button
    assert e("prepared", {**me, "releases_bound": True}) == "question"
    assert e("prepared", {**me, "releases_bound": True, "question_set": True}) is None
    assert e("prepared", {**me, "releases_bound": True, "question_set": True, "edit_question": True}) == "question"
    assert e("question_proposed", {**me, "open_clarification": {"id": "C3"}}) == "clarification"
    assert e("review_pending", me) is None  # a decision button comes first
    assert e("review_pending", {**me, "review_choice": "accept_result"}) == "reason"


def test_friendly_error():
    assert "couldn't read" in t.friendly_error(UploadError("bad"))
    assert "manually" in t.friendly_error(ag.AgentError("no key"))
    assert "nothing was sent" in t.friendly_error(WorkflowError("the payload changed since it was shown"))
    msg = t.friendly_error(ValueError("patient 123"))
    assert "ValueError" in msg and "123" not in msg


def test_verdict_lines():
    cards = [{"id": "c1", "title": "Card one"}]
    lines = t.verdict_lines({"card_id": "c1", "question_verdict": "SAFE", "verdict": "SAFE", "n_findings": 0}, cards)
    assert lines[0].startswith("Your question (Card one): SAFE")
    assert "baseline" in t.verdict_lines({"card_id": None, "baseline_only": True}, cards)[0]


def test_say_marks_dynamic_text_plain():
    ss = {}
    t.say(ss, "column <b>x</b>")
    assert ss[t.P + "history"][0] == {"role": "assistant", "md": False, "body": "column <b>x</b>"}


def test_no_unsafe_html_in_module():
    src = (ROOT / "app" / "chat_intake_tab.py").read_text()
    assert "unsafe_allow_html" not in src


def test_session_key_transport_does_not_change_process_environment(monkeypatch):
    class FakeUI:
        session_state = {t.P + 'api_key': 'demo-key'}
    sent = []
    def fake_send(url, headers, body, timeout):
        sent.append(headers['Authorization'])
        return b'{}'
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.setattr(ag, '_default_transport', fake_send)
    assert t._has_key(FakeUI())
    t._user_key_transport(FakeUI())('https://example.invalid', {}, b'{}', 1)
    assert sent == ['Bearer demo-key']
    assert not t.api_key_available()
