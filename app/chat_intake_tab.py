"""Chat-first front end for intake_prototype.workflow.IntakeWorkflow (experimental research prototype).

One conversation thread: the assistant asks one thing at a time, the person answers in the chat box or with short
buttons. Every workflow step is still an explicit call made only after an explicit human action; nothing is accepted
on the person's behalf. No model is called until the exact payload has been shown and the person has said yes to
that payload (consent is bound to its SHA-256). Only metadata is ever sent, never dataset rows.

User and model text is always shown with st.text / st.json (never as Markdown or HTML). Only fixed strings written
in this file are rendered as Markdown. Starting over only forgets the conversation in this browser tab; the session
folder on disk is left as is. Data is only deleted by the explicit "Close session" button.
"""
from __future__ import annotations

import os
from typing import Mapping, Optional

from intake_prototype import agents as ag
from intake_prototype.upload import UploadError
from intake_prototype.workflow import (APPROVAL_STATEMENT, BELONGS_STATEMENT, LIMITATIONS, REVIEW_DECISIONS,
                                       IntakeWorkflow, WorkflowError)

P = "chat_"  # every session_state key of this tab starts with this
WF_KEY = P + "wf"
UPLOAD_TYPES = ["csv", "tsv", "gz"]
UNMAPPED = "(leave unmapped)"
PRIVACY_NOTICE = ("Privacy: only metadata goes to the model (column names, row and column counts, file format, your "
                  "question, the supported card descriptions and release file names). No rows or cell values are "
                  "sent. Column names and your question can still be sensitive: if they are, say no and continue "
                  "manually.")
REVIEW_LABELS = {"accept_result": "Accept the result", "reject_result": "Reject the result",
                 "request_more_evidence": "Ask for more evidence"}
HELP_TEXT = ("You can type **help** for this message, **status** to see where we are, or **start over** to begin a "
             "new conversation. Otherwise just answer my question, or use the buttons under it.")
COMMANDS = {
    "help": "help", "?": "help", "what can i do": "help",
    "status": "status", "where am i": "status", "progress": "status",
    "start over": "restart", "restart": "restart", "reset": "restart", "new session": "restart",
}


# ---------------------------------------------------------------- pure helpers (tested without Streamlit)

def parse_command(text: Optional[str]) -> Optional[str]:
    """'help' | 'status' | 'restart' for a chat command, else None (the text is an answer)."""
    t = " ".join((text or "").strip().lower().rstrip(".!").split())
    t = t[1:] if t.startswith("/") else t
    return COMMANDS.get(t)


def clean_path(text: Optional[str]) -> str:
    """A folder path typed in chat: strip whitespace and matching quotes, expand ~."""
    t = (text or "").strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "'\"`":
        t = t[1:-1].strip()
    return os.path.expanduser(t) if t else ""


def api_key_available(env: Optional[Mapping[str, str]] = None) -> bool:
    return bool((env if env is not None else os.environ).get("OPENAI_API_KEY", "").strip())


def _has_key(st) -> bool:
    return api_key_available() or bool(st.session_state.get(P + "api_key", "").strip())


def _user_key_transport(st):
    """Use an optional session-only key without changing the shared process environment."""
    key = st.session_state.get(P + "api_key", "").strip()
    if not key:
        return None
    def send(url, headers, body, timeout):
        return ag._default_transport(url, {**headers, "Authorization": f"Bearer {key}"}, body, timeout)
    return send


def next_proposal(view: dict) -> Optional[dict]:
    """The first AI proposal that nobody has decided yet."""
    return next((p for p in view["proposals"] if p["source"] not in view["decisions"]), None)


def next_manual_column(view: dict, finished: bool) -> Optional[str]:
    """Manual mapping: the next column without a decision, unless the person said they are done."""
    if finished or view["origin"] != "manual":
        return None
    return next((c for c in view["source_columns"] if c not in view["decisions"]), None)


def open_clarification(clarifications: list[dict]) -> Optional[dict]:
    return next((c for c in clarifications if c["answer"] is None), None)


def expected_input(state: str, ui: Mapping) -> Optional[str]:
    """What a free-text chat message means right now. ui: person, path_a, path_b, releases_bound, question_set,
    edit_question, open_clarification, proposals_left, review_choice."""
    if not (ui.get("person") or "").strip():
        return "person"
    if state in ("mapping_proposed", "question_proposed") and ui.get("open_clarification") \
            and not ui.get("proposals_left"):
        return "clarification"
    if state == "prepared":
        if not ui.get("releases_bound"):
            return "path_a" if not ui.get("path_a") else ("path_b" if not ui.get("path_b") else None)
        if not ui.get("question_set") or ui.get("edit_question"):
            return "question"
    if state == "review_pending" and ui.get("review_choice"):
        return "reason"
    return None


def friendly_error(exc: BaseException) -> str:
    """Plain message. Unknown exceptions show only their type (their text may quote data)."""
    if isinstance(exc, UploadError):
        return f"I couldn't read that file: {str(exc)[:300]}"
    if isinstance(exc, ag.AgentError):
        return f"The AI step didn't complete ({exc}). Nothing was changed; we can continue manually."
    if isinstance(exc, WorkflowError):
        msg = str(exc)
        if "payload changed" in msg:
            return "What would be sent changed after I showed it, so nothing was sent. Please look at it again."
        return f"That step didn't go through: {msg}"
    return f"Something went wrong ({type(exc).__name__}). Nothing was changed."


def target_label(t: str) -> str:
    return t if t == UNMAPPED else f"{t} ({ag.CLINICAL_TARGETS.get(t, '')})"


def verdict_lines(run: dict, cards: list[dict]) -> list[str]:
    card = next((c for c in cards if c["id"] == run.get("card_id")), None)
    out = []
    if card:
        out.append(f"Your question ({card['title']}): {run.get('question_verdict') or '-'}")
    elif run.get("baseline_only"):
        out.append("No question card (baseline comparison only).")
    out.append(f"Assessment verdict: {run.get('verdict') or '-'}")
    out.append(f"Findings: {run.get('n_findings')} · flagged for review: {run.get('flagged_for_review')} · "
               f"original files unchanged: {run.get('originals_unchanged')}")
    return out


# ---------------------------------------------------------------- conversation plumbing

def _history(ss) -> list:
    return ss.setdefault(P + "history", [])


def say(ss, body: str, *, md: bool = False, role: str = "assistant") -> None:
    """md=True only for fixed strings from this file; anything with user/AI/column text is plain text."""
    _history(ss).append({"role": role, "md": md, "body": body})


def _render_history(st) -> None:
    for m in _history(st.session_state):
        with st.chat_message(m["role"]):
            (st.markdown if m["md"] else st.text)(m["body"])


def _do(st, user_says: Optional[str], fn, *args, success: Optional[str] = None, **kwargs) -> None:
    ss = st.session_state
    if user_says:
        say(ss, user_says, role="user")
    try:
        fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001  every failure is shown, never swallowed
        say(ss, friendly_error(exc))
    else:
        if success:
            say(ss, success)
    st.rerun()


def _restart(ss) -> None:
    """Forget this conversation only. The session folder on disk is not touched."""
    wf = ss.get(WF_KEY)
    for k in [k for k in ss.keys() if str(k).startswith(P)]:
        del ss[k]
    if wf is not None:
        say(ss, f"Started a new conversation. The previous session folder was kept on disk: {wf.dir}")


def _ui(ss, wf: Optional[IntakeWorkflow]) -> dict:
    ui = {"person": ss.get(P + "person", ""), "path_a": ss.get(P + "path_a"), "path_b": ss.get(P + "path_b"),
          "edit_question": ss.get(P + "edit_question"), "review_choice": ss.get(P + "review_choice")}
    if wf is None or wf.state in ("created", "closed"):
        return ui
    ev = wf.evidence()
    ui.update(releases_bound=ev["releases"] is not None, question_set=ev["question"] is not None)
    if wf.state == "mapping_proposed":
        v = wf.mapping_view()
        ui["proposals_left"] = next_proposal(v) is not None or next_manual_column(v, ss.get(P + "manual_done")) \
            is not None
        ui["open_clarification"] = open_clarification(v["clarifications"])
    elif wf.state == "question_proposed":
        ui["open_clarification"] = open_clarification(wf.clarifications("question"))
    return ui


def _status_text(wf: Optional[IntakeWorkflow]) -> str:
    if wf is None:
        return "Nothing started yet."
    s = wf.status()
    return (f"Step: {s['state']}. Undecided proposals: {len(s['undecided_proposals'])}. Open questions: "
            f"{len(s['open_clarifications'])}. Releases set: {s['releases_bound']}. Verdict: {s['verdict'] or '-'}.")


def _handle_chat(st, text: str, wf: Optional[IntakeWorkflow], ui: dict) -> None:
    ss = st.session_state
    cmd = parse_command(text)
    if cmd == "restart":
        say(ss, text, role="user")
        ss[P + "confirm_restart"] = True
        st.rerun()
    if cmd in ("help", "status"):
        say(ss, text, role="user")
        say(ss, HELP_TEXT, md=True) if cmd == "help" else say(ss, _status_text(wf))
        st.rerun()
    exp = expected_input(wf.state if wf else "created", ui)
    if exp == "person":
        ss[P + "person"] = text.strip()[:120]
        say(ss, text, role="user")
        say(ss, f"Thanks, {ss[P + 'person']}. I'll record that name or role with each decision you make.")
    elif exp in ("path_a", "path_b"):
        say(ss, text, role="user")
        p = clean_path(text)
        if not p or not os.path.isdir(p):
            say(ss, "I can't find a folder at that path on this machine. Please paste the full folder path again.")
        else:
            ss[P + exp] = p
    elif exp == "question":
        ss.pop(P + "edit_question", None)
        _do(st, text, wf.set_question, text, success="Got it, I've saved your question.")
    elif exp == "clarification":
        c = ui["open_clarification"]
        _do(st, text, wf.answer_clarification, c["id"], text, answered_by=ui["person"], success="Answer recorded.")
    elif exp == "reason":
        choice = ss.pop(P + "review_choice")
        _do(st, text, wf.record_review, choice, reason=text, reviewer_role=ui["person"],
            success=f"Recorded your review: {REVIEW_LABELS[choice]}.")
    else:
        say(ss, text, role="user")
        say(ss, "I'm not waiting for typed text right now; please use the buttons under my last message. "
                "Type help for options.")
    st.rerun()


# ---------------------------------------------------------------- the current step (one live assistant bubble)

def _consent_step(st, wf: IntakeWorkflow, agent: str, gen: str, intro: str, call, decline_label: str, decline):
    ss = st.session_state
    try:
        preview = wf.preview_ai_payload(agent)
    except WorkflowError as exc:
        st.text(friendly_error(exc))
        return
    ss[P + "shown_" + agent] = preview["sha256"]
    st.markdown(intro)
    st.caption(PRIVACY_NOTICE)
    with st.expander(f"Show exactly what would be sent to the {agent} agent", expanded=False):
        st.json(preview["payload"])
        st.text(f"Fingerprint (SHA-256): {preview['sha256']}")
    st.markdown("May I send exactly this to OpenAI? Your yes covers only this payload.")
    c1, c2 = st.columns(2)
    if c1.button("Yes, send it", type="primary", key=f"{P}yes_{agent}_{gen}"):
        shown = ss.get(P + "shown_" + agent)

        def go():
            wf.grant_consent(agent, granted_by=ss[P + "person"], payload_sha256=shown)
            call()
        _do(st, "Yes, send it.", go, success="The assistant replied. Its ideas are suggestions only; let's go through "
                                              "them together.")
    if c2.button(decline_label, key=f"{P}no_{agent}_{gen}"):
        _do(st, decline_label, decline)


def _step_upload(st, wf):
    ss = st.session_state
    st.markdown("Please upload the clinical table (.csv, .tsv, or either one gzipped). It stays on this machine.")
    up = st.file_uploader("Clinical table", type=UPLOAD_TYPES, key=P + "upload", label_visibility="collapsed")
    if st.button("Use this file", type="primary", disabled=up is None, key=P + "upload_btn"):
        def go():
            w = ss.get(WF_KEY) or IntakeWorkflow.create()
            ss[WF_KEY] = w
            u = w.upload(up.getvalue(), up.name, up.type)
            say(ss, f"Read {u['n_rows']} rows and {u['n_columns']} columns ({u['format']}). Stored privately in the "
                    f"session folder.")
        _do(st, f"Uploaded {up.name}", go)


def _step_uploaded(st, wf, gen):
    if _has_key(st):
        _consent_step(st, wf, ag.PREPARATION, gen,
                      "Next, the column names need matching to the supported fields. I can ask the preparation "
                      "assistant for suggestions, or you can match them yourself.",
                      lambda: wf.propose_mappings(transport=_user_key_transport(st)),
                      "No, I'll match them myself", wf.start_manual_mapping)
    else:
        st.markdown("No OpenAI key is set up here, so we'll match the columns by hand. I'll show them one at a time.")
        if st.button("Start matching columns", type="primary", key=f"{P}manual_{gen}"):
            _do(st, "Start matching columns", wf.start_manual_mapping)


def _step_mapping(st, wf, gen):
    ss, person = st.session_state, st.session_state[P + "person"]
    v = wf.mapping_view()
    targets = [UNMAPPED] + list(ag.CLINICAL_TARGETS)
    p = next_proposal(v)
    if p:
        st.markdown("The assistant suggests (confidence is its own guess, not proof):")
        st.text(f"{p['source']}  ->  {p['target'] or '(no matching field)'}   [{p['confidence']}]")
        if p["rationale"]:
            st.text(f"Reason given: {p['rationale']}")
        c1, c2, c3 = st.columns(3)
        if c1.button("Accept", type="primary", key=f"{P}acc_{gen}"):
            _do(st, f"Accept {p['source']}", wf.decide_mapping, p["source"], "accept", decided_by=person)
        if c2.button("Reject", key=f"{P}rej_{gen}"):
            _do(st, f"Reject {p['source']} (leave unmapped)", wf.decide_mapping, p["source"], "reject",
                decided_by=person)
        if c3.button("Pick another field", key=f"{P}alt_{gen}"):
            ss[P + "picking"] = p["source"]
            st.rerun()
        if ss.get(P + "picking") == p["source"]:
            _pick_field(st, wf, p["source"], targets[1:], gen, person)
        return
    col = next_manual_column(v, ss.get(P + "manual_done"))
    if col:
        st.markdown("Which supported field does this column hold?")
        st.text(f"Column: {col}")
        _pick_field(st, wf, col, targets, gen, person, extra_done=True)
        return
    c = open_clarification(v["clarifications"])
    if c:
        st.markdown("A question before we finish (please answer in the chat box below):")
        st.text(c["text"])
        return
    review = v["decisions"]
    st.markdown("All set for review. These renames will be applied to a copy (values never change):")
    renames = [f"{s} -> {d['target']}" for s, d in review.items() if d["target"] and d["target"] != s]
    st.text("\n".join(renames) or "(no renames)")
    with st.expander("Change or add a mapping"):
        src = st.selectbox("Column", v["source_columns"], key=f"{P}chg_src_{gen}")
        _pick_field(st, wf, src, targets, gen + "_chg", person)
    if st.button("Finish mapping review", type="primary", key=f"{P}finish_{gen}"):
        _do(st, "Finish mapping review", wf.complete_mapping_review, reviewed_by=person,
            success="Mapping review is complete.")


def _pick_field(st, wf, col, options, gen, person, extra_done=False):
    tgt = st.selectbox("Field", options, format_func=target_label, key=f"{P}pick_{gen}",
                       label_visibility="collapsed")
    cols = st.columns(3 if extra_done else 2)
    if cols[0].button("Use this", type="primary", key=f"{P}use_{gen}"):
        st.session_state.pop(P + "picking", None)
        if tgt == UNMAPPED:
            _do(st, f"Leave {col} unmapped", wf.decide_mapping, col, "reject", decided_by=person)
        else:
            _do(st, f"{col} -> {tgt}", wf.decide_mapping, col, "edit", tgt, decided_by=person)
    if cols[1].button("Leave unmapped", key=f"{P}skip_{gen}"):
        st.session_state.pop(P + "picking", None)
        _do(st, f"Leave {col} unmapped", wf.decide_mapping, col, "reject", decided_by=person)
    if extra_done and cols[2].button("Leave the rest unmapped", key=f"{P}rest_{gen}"):
        st.session_state[P + "manual_done"] = True
        say(st.session_state, "Leave the rest unmapped.", role="user")
        st.rerun()


def _step_releases(st, wf, gen, ui):
    ss = st.session_state
    if not ui["path_a"]:
        st.markdown("Now the releases. Please type the folder path of **trusted release A** in the chat box.")
        return
    if not ui["path_b"]:
        st.text(f"Release A: {ui['path_a']}")
        st.markdown("Thanks. Now type the folder path of **candidate release B**.")
        return
    st.text(f"Release A: {ui['path_a']}\nRelease B: {ui['path_b']}")
    st.markdown("Please confirm this statement:")
    st.text(BELONGS_STATEMENT)
    c1, c2 = st.columns(2)
    if c1.button("Yes, that's correct", type="primary", key=f"{P}belongs_{gen}"):
        def go():
            try:
                wf.bind_releases(ui["path_a"], ui["path_b"], upload_belongs_to_candidate=True,
                                 confirmed_by=ui["person"])
            except WorkflowError:
                ss.pop(P + "path_a", None)
                ss.pop(P + "path_b", None)
                raise
        _do(st, "Yes, the upload belongs to release B.", go, success="Releases set. Nothing in them is modified.")
    if c2.button("No, re-enter the folders", key=f"{P}notbelongs_{gen}"):
        ss.pop(P + "path_a", None)
        ss.pop(P + "path_b", None)
        say(ss, "No, re-enter the folders.", role="user")
        st.rerun()


def _card_buttons(st, wf, gen, person, proposed: Optional[str]):
    ss = st.session_state
    cards = ag.card_catalogue()
    if not cards:
        st.text("No question cards are installed, so the firewall can't run with a card.")
    chosen = ss.get(P + "card")
    if chosen is None:
        st.markdown("Which supported card fits your question? (Only these are supported.)")
        for c in cards:
            with st.container(border=True):
                st.text(("Suggested: " if c["id"] == proposed else "") + c["title"])
                st.caption(c["intended_use"])
                if st.button("Choose this", key=f"{P}card_{c['id']}_{gen}"):
                    ss[P + "card"] = c["id"]
                    say(ss, f"Choose: {c['title']}", role="user")
                    st.rerun()
        if st.button("None fits: compare the releases without a card", key=f"{P}baseline_{gen}"):
            ss[P + "card"] = ""
            st.rerun()
        return
    title = next((c["title"] for c in cards if c["id"] == chosen), "No card (baseline only)")
    st.markdown("Please confirm: this choice matches your question.")
    st.text(title)
    c1, c2 = st.columns(2)
    if c1.button("Yes, confirm", type="primary", key=f"{P}cardok_{gen}"):
        ss.pop(P + "card", None)
        _do(st, "Yes, confirm.", wf.confirm_question, chosen or None, confirmed_by=person,
            baseline_only=not chosen, success="Confirmed.")
    if c2.button("Choose again", key=f"{P}cardagain_{gen}"):
        ss.pop(P + "card", None)
        st.rerun()


def _step_question(st, wf, gen, ui):
    ss = st.session_state
    if ui["edit_question"] or not ui["question_set"]:
        st.markdown("What research question do you want to check? Type it in the chat box.")
        return
    if wf.state == "prepared":
        st.text(f"Your question: {wf.evidence()['question']['text']}")
        if st.button("Rephrase my question", key=f"{P}rephrase_{gen}"):
            ss[P + "edit_question"] = True
            st.rerun()
        if _has_key(st) and not ss.get(P + "skip_qagent"):
            def skip():
                ss[P + "skip_qagent"] = True
            _consent_step(st, wf, ag.QUESTION, gen,
                          "I can ask the question assistant which supported card fits. This is a separate request "
                          "with its own permission.", lambda: wf.propose_question(transport=_user_key_transport(st)),
                          "No, I'll pick the card myself", skip)
            return
        _card_buttons(st, wf, gen, ui["person"], None)
        return
    view = wf.question_view()  # question_proposed
    c = open_clarification(view["clarifications"])
    if c:
        st.markdown("The question assistant asks (please answer in the chat box):")
        st.text(c["text"])
        return
    p = view["proposal"]
    st.markdown("The question assistant's suggestion:")
    st.text(view["proposed_card"]["title"] if view["proposed_card"] else "No supported card fits.")
    if p["explanation"]:
        st.text(f"Why: {p['explanation']}")
    for e in p["agent_errors"]:
        st.text(f"Note: assistant output problem: {e}")
    _card_buttons(st, wf, gen, ui["person"], p["card_id"])


def _step_result(st, wf, ev, gen, person):
    ss = st.session_state
    run = ev["run"]
    st.markdown("**Result (pending human review; nothing is accepted automatically)**")
    st.text("\n".join(verdict_lines(run, ag.card_catalogue())))
    try:
        doc = wf.findings()
        q = next((x for x in doc.get("questions", []) if x.get("id") == run.get("card_id")), None)
        if q and q.get("why"):
            st.text(f"Why: {q['why']}")
        for f in doc.get("findings", [])[:5]:
            st.text(f"- {f.get('id', 'Finding')}: {f.get('summary', '')}")
        with st.expander("Full findings.json (local only, never sent to a model)"):
            st.json(doc)
    except Exception as exc:  # noqa: BLE001
        st.text(friendly_error(exc))
    for w in run.get("warnings", []):
        st.text(f"Warning: {w}")
    if ev["state"] != "review_pending":
        return
    choice = ss.get(P + "review_choice")
    if choice:
        st.text(f"You chose: {REVIEW_LABELS[choice]}")
        st.markdown("Please type the reason in the chat box.")
        if st.button("Choose differently", key=f"{P}rechoose_{gen}"):
            ss.pop(P + "review_choice")
            st.rerun()
        return
    st.markdown("What's your decision?")
    cols = st.columns(len(REVIEW_DECISIONS))
    for col, d in zip(cols, REVIEW_DECISIONS):
        if col.button(REVIEW_LABELS[d], key=f"{P}rev_{d}_{gen}"):
            ss[P + "review_choice"] = d
            say(ss, REVIEW_LABELS[d], role="user")
            st.rerun()


def _current_step(st, wf: Optional[IntakeWorkflow], ui: dict) -> None:
    ss = st.session_state
    if not ui["person"]:
        st.markdown("Hi! I'll guide you through preparing a clinical table and checking it, one step at a time. "
                    "First, what's your name or role? Type it below.")
        return
    if wf is None or wf.state == "created":
        _step_upload(st, wf)
        return
    ev = wf.evidence()
    gen = f"{ev['session_id']}_{len(ev['history'])}_{len(_history(ss))}"
    s = wf.state
    if s == "uploaded":
        _step_uploaded(st, wf, gen)
    elif s == "mapping_proposed":
        _step_mapping(st, wf, gen)
    elif s == "mapping_reviewed":
        st.markdown("Renames to apply to a copy:")
        st.text("\n".join(f"{r['source']} -> {r['target']}" for r in ev["mapping_review"]["renames"]) or "(none)")
        st.markdown("As the data owner (or acting for them), do you approve this statement?")
        st.text(APPROVAL_STATEMENT)
        if st.button("I approve", type="primary", key=f"{P}approve_{gen}"):
            _do(st, "I approve.", wf.approve, data_owner_confirmed=True, approved_by=ui["person"],
                success="Approved.")
    elif s == "approved":
        st.markdown("Ready to write the prepared copy (renames only; values are checked to be unchanged).")
        if st.button("Prepare the copy", type="primary", key=f"{P}prep_{gen}"):
            _do(st, "Prepare the copy.", wf.prepare, success="Prepared copy written and checked.")
    elif s == "prepared" and not ui["releases_bound"]:
        _step_releases(st, wf, gen, ui)
    elif s in ("prepared", "question_proposed"):
        _step_question(st, wf, gen, ui)
    elif s in ("question_confirmed", "firewall_failed"):
        if s == "firewall_failed":
            st.text(f"The last run gave no verdict: {ev['run']['error']}")
        st.markdown("Everything is ready. Run the firewall on the reviewed card?")
        if st.button("Run the firewall", type="primary", key=f"{P}run_{gen}"):
            _do(st, "Run the firewall.", wf.run_firewall, success="The run finished.")
    elif s in ("review_pending", "reviewed"):
        _step_result(st, wf, ev, gen, ui["person"])
        if s == "reviewed":
            st.markdown("Review recorded. You can close the session (deletes the upload copy and the prepared "
                        "table; the evidence log stays), or keep it for later.")
            if st.button("Close session and delete the data copies", key=f"{P}close_{gen}"):
                _do(st, "Close the session.", wf.close, success="Closed. The data copies were deleted.")
    elif s == "closed":
        st.markdown("This session is closed. Use **Start over** above to begin a new one.")


def render(st, html=None, ui=None) -> None:  # html/ui unused: nothing here is rendered as raw HTML
    ss = st.session_state
    wf: Optional[IntakeWorkflow] = ss.get(WF_KEY)
    st.caption("Experimental research prototype, not a validated or production tool. Supported: one clinical table "
               f"mapped onto {', '.join(ag.CLINICAL_TARGETS)}, and the listed question cards only.")
    with st.expander("Use your OpenAI key (optional)"):
        st.caption("Enter it only on a trusted app. It stays in this browser session's server memory and is sent "
                   "to OpenAI to authorize requests. It is not written to the project or shown in the conversation.")
        st.text_input("OpenAI API key", type="password", key=P + "api_key")
    c1, c2 = st.columns([1, 3])
    if c1.button("Start over", key=P + "restart_btn"):
        ss[P + "confirm_restart"] = True
    if ss.get(P + "confirm_restart"):
        c2.warning("Start a new conversation? Nothing on disk is deleted.")
        y, n = c2.columns(2)
        if y.button("Yes, start over", key=P + "restart_yes"):
            _restart(ss)
            st.rerun()
        if n.button("Cancel", key=P + "restart_no"):
            ss.pop(P + "confirm_restart")
            st.rerun()
    with st.expander("Limitations and privacy"):
        st.markdown(PRIVACY_NOTICE)
        for l in LIMITATIONS:
            st.markdown(f"- {l}")
        if wf is not None:
            st.text(f"Session folder: {wf.dir}")

    ui_state = _ui(ss, wf)
    _render_history(st)
    with st.chat_message("assistant"):
        _current_step(st, wf, ui_state)
    exp = expected_input(wf.state if wf else "created", ui_state)
    placeholder = {"person": "Your name or role", "path_a": "Folder path of trusted release A",
                   "path_b": "Folder path of candidate release B", "question": "Your research question",
                   "clarification": "Your answer", "reason": "Reason for your decision"}.get(exp, "Type help or status")
    text = st.chat_input(placeholder, key=P + "input", max_chars=4000)
    if text and text.strip():
        _handle_chat(st, text.strip(), wf, ui_state)
