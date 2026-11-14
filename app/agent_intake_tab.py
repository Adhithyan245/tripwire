"""Two-agent intake (experimental): a Streamlit front end for intake_prototype.workflow.IntakeWorkflow.

Every screen is chosen by the workflow's own state; every step is an explicit button. No model is called until the
user has seen the exact payload for that agent and ticked a consent box bound to that payload's hash. Only metadata
(column names, counts, the question text, card descriptions, release file names) is ever sent; never dataset rows.
Model text is shown as plain text, never as HTML. Session files live in the workflow's own session folder.
"""
from __future__ import annotations

import pathlib
from typing import Optional

from intake_prototype import agents as ag
from intake_prototype.upload import UploadError
from intake_prototype.workflow import (APPROVAL_STATEMENT, BELONGS_STATEMENT, LIMITATIONS, REVIEW_DECISIONS,
                                       IntakeWorkflow, WorkflowError)

WF_KEY = "ai_wf"
UPLOAD_TYPES = ["csv", "tsv", "gz"]
UNMAPPED = "(leave unmapped)"
PRIVACY_NOTICE = ("Only metadata is sent to the model: column names, row and column counts, file format, your "
                  "question, the supported card descriptions and release file names. No dataset rows or cell values "
                  "are sent. Column names and your question can still be sensitive; don't consent if they are.")
SCOPE_NOTE = ("Supported: one clinical table (.csv, .tsv, or either gzipped), mapped onto a fixed schema "
              f"({', '.join(ag.CLINICAL_TARGETS)}), and only the question cards listed here. Other formats and "
              "arbitrary questions are not supported.")
STEP_TITLES = {
    "created": "1 · Upload the clinical table",
    "uploaded": "2 · Map columns (AI proposal or manual)",
    "mapping_proposed": "3 · Review every proposal and clarification",
    "mapping_reviewed": "4 · Data-owner approval",
    "approved": "5 · Create the prepared copy",
    "prepared": "6 · Bind releases and enter the question",
    "question_proposed": "7 · Confirm the question card",
    "question_confirmed": "8 · Run the firewall",
    "firewall_failed": "8 · Run the firewall (last run failed)",
    "review_pending": "9 · Review the result",
    "reviewed": "10 · Close the session",
    "closed": "Session closed",
}
REVIEW_LABELS = {"accept_result": "Accept result", "reject_result": "Reject result",
                 "request_more_evidence": "Request more evidence"}


# ---------------------------------------------------------------- pure helpers (tested without Streamlit)

def step_title(state: str) -> str:
    return STEP_TITLES.get(state, state)


def friendly_error(exc: BaseException) -> str:
    """A plain message for the user. Unknown exceptions show only their type (their text may quote data)."""
    if isinstance(exc, UploadError):
        return f"Can't read this file: {str(exc)[:300]}"
    if isinstance(exc, ag.AgentError):
        return f"The AI step didn't complete: {exc}. Nothing was changed; you can use the manual path instead."
    if isinstance(exc, WorkflowError):
        return f"Not done: {exc}"
    return f"Something went wrong ({type(exc).__name__}). Nothing was changed."


def consent_ready(ticked: bool, person: str, shown_sha: Optional[str], current_sha: Optional[str]) -> bool:
    """Consent only counts when ticked, attributed, and for the exact payload still current."""
    return bool(ticked) and bool((person or "").strip()) and bool(shown_sha) and shown_sha == current_sha


def proposal_decisions(choices: dict[str, str], edits: dict[str, str]) -> list[tuple[str, str, Optional[str]]]:
    """Form choices -> decide_mapping calls. choices: source -> accept/reject/edit; edits: source -> target.
    Undecided ("") entries are skipped, never assumed."""
    out = []
    for src, d in choices.items():
        if d == "edit":
            tgt = edits.get(src)
            if tgt and tgt != UNMAPPED:
                out.append((src, "edit", tgt))
        elif d in ("accept", "reject"):
            out.append((src, d, None))
    return out


def manual_decisions(choices: dict[str, str]) -> list[tuple[str, str, Optional[str]]]:
    """Manual mapping form: every column gets an explicit edit (mapped) or reject (left unmapped)."""
    return [(src, "reject", None) if tgt in (None, "", UNMAPPED) else (src, "edit", tgt) for src, tgt in choices.items()]


def verdict_summary(run: dict, cards: list[dict]) -> dict:
    """Separate the selected question's verdict from the overall verdict, for display."""
    card = next((c for c in cards if c["id"] == run.get("card_id")), None)
    return {"overall": run.get("verdict"),
            "question": run.get("question_verdict") if run.get("card_id") else None,
            "card_title": card["title"] if card else None,
            "baseline_only": bool(run.get("baseline_only"))}


# ---------------------------------------------------------------- Streamlit plumbing

def _act(st, fn, *args, success: Optional[str] = None, **kwargs) -> bool:
    try:
        fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001  every failure is shown, never swallowed
        st.session_state["ai_error"] = friendly_error(exc)
        st.rerun()
        return False
    st.session_state["ai_error"] = None
    st.session_state["ai_notice"] = success
    st.rerun()
    return True


def _consent_block(st, wf: IntakeWorkflow, agent: str, gen: str, call_label: str, call) -> None:
    try:
        preview = wf.preview_ai_payload(agent)
    except WorkflowError as exc:
        st.info(friendly_error(exc))
        return
    st.caption(PRIVACY_NOTICE)
    with st.expander(f"Exactly what the {agent} agent would receive", expanded=False):
        st.json(preview["payload"])
        st.text(f"Payload SHA-256: {preview['sha256']}")
    with st.form(f"ai_consent_{agent}_{gen}"):
        ticked = st.checkbox(f"I consent to sending exactly this payload (SHA-256 {preview['sha256'][:12]}…) to the "
                             f"{agent} agent (OpenAI). This consent is for this payload only.")
        sent = st.form_submit_button(call_label, type="primary")
    if sent:
        person = st.session_state.get("ai_person", "")
        if not consent_ready(ticked, person, preview["sha256"], wf.preview_ai_payload(agent)["sha256"]):
            st.error("Tick the consent box and enter your name or role above first. Nothing was sent.")
            return

        def go():
            wf.grant_consent(agent, granted_by=person, payload_sha256=preview["sha256"])
            call()
        _act(st, go, success="Proposal received. Review it below; nothing is accepted automatically.")


def _clarification_forms(st, wf: IntakeWorkflow, stage: str, gen: str, person: str) -> None:
    for c in wf.clarifications(stage):
        st.markdown(f"**Clarification {c['id']}** ({'assistant' if c['origin'] != 'system' else 'system'})")
        st.text(c["text"])
        if c["answer"] is not None:
            st.caption("Answered. Changing it reopens the later steps.")
        with st.form(f"ai_clar_{c['id']}_{gen}"):
            ans = st.text_area("Your answer", value=c["answer"] or "", key=f"ai_clar_txt_{c['id']}_{gen}")
            if st.form_submit_button("Save answer"):
                _act(st, wf.answer_clarification, c["id"], ans, answered_by=person)


def _target_label(t: str) -> str:
    return t if t == UNMAPPED else f"{t} · {ag.CLINICAL_TARGETS[t]}"


def _mapping_screen(st, wf: IntakeWorkflow, gen: str, person: str) -> None:
    v = wf.mapping_view()
    st.caption(v["note"])
    for e in v["agent_errors"]:
        st.warning(f"Assistant output problem: {e}")
    for r in v["rejected"]:
        st.warning(f"Discarded an invalid proposal ({', '.join(r['reasons'])}).")
    targets = [UNMAPPED] + list(ag.CLINICAL_TARGETS)
    decided = v["decisions"]
    with st.form(f"ai_map_{gen}"):
        if v["origin"] == "manual":
            st.markdown("Choose a field for each column, or leave it unmapped. Values are never changed.")
            choices = {}
            for col in v["source_columns"]:
                cur = (decided.get(col) or {}).get("target") or (col if col in ag.CLINICAL_TARGETS else UNMAPPED)
                choices[col] = st.selectbox(f"Column: {col}", targets, index=targets.index(cur),
                                            format_func=_target_label, key=f"ai_man_{col}_{gen}")
            calls = None
        else:
            choices, edits = {}, {}
            for p in v["proposals"]:
                st.markdown("---")
                st.text(f"{p['source']}  →  {p['target'] or '(no target)'}   confidence (self-reported): "
                        f"{p['confidence']}")
                if p["rationale"]:
                    st.caption("Assistant's reason:")
                    st.text(p["rationale"])
                prev = (decided.get(p["source"]) or {}).get("decision", "")
                opts = ["", "accept", "reject", "edit"]
                choices[p["source"]] = st.radio(
                    "Decision", opts, index=opts.index(prev), horizontal=True, key=f"ai_dec_{p['source']}_{gen}",
                    format_func=lambda d: {"": "Undecided", "accept": "Accept", "reject": "Reject (leave unmapped)",
                                           "edit": "Edit target"}[d])
                edits[p["source"]] = st.selectbox("Edited target (used only with Edit)", targets,
                                                  format_func=_target_label, key=f"ai_edit_{p['source']}_{gen}")
            calls = proposal_decisions(choices, edits)
        saved = st.form_submit_button("Save decisions")
    if saved:
        calls = manual_decisions(choices) if calls is None else calls

        def go():
            for src, d, tgt in calls:
                prev = decided.get(src) or {}
                if prev.get("decision") == d and (d != "edit" or prev.get("target") == tgt):
                    continue  # unchanged; don't reopen later steps
                wf.decide_mapping(src, d, tgt, decided_by=person)
        _act(st, go, success="Decisions saved.")
    if v["undecided"]:
        st.warning(f"Still undecided: {', '.join(v['undecided'])}")
    _clarification_forms(st, wf, "mapping", gen, person)
    if st.button("Complete mapping review", type="primary", key=f"ai_done_map_{gen}"):
        _act(st, wf.complete_mapping_review, reviewed_by=person, success="Mapping review complete.")


def _question_screen(st, wf: IntakeWorkflow, ev: dict, gen: str, person: str) -> None:
    rel = ev["releases"]
    if rel:
        st.success(f"Trusted A: {rel['trusted_name']} · candidate B: {rel['candidate_name']} "
                   f"({len(rel['candidate_files'])} files; clinical.tsv will be replaced by the prepared copy)")
    with st.form(f"ai_rel_{gen}"):
        st.markdown("**Releases** (folders on this machine; nothing in them is modified)")
        a = st.text_input("Trusted release A folder", value=rel["trusted"] if rel else "")
        b = st.text_input("Candidate release B folder", value=rel["candidate"] if rel else "")
        belongs = st.checkbox(BELONGS_STATEMENT)
        if st.form_submit_button("Bind releases"):
            _act(st, wf.bind_releases, a.strip(), b.strip(), upload_belongs_to_candidate=belongs,
                 confirmed_by=person, success="Releases bound.")
    q = ev["question"]
    with st.form(f"ai_q_{gen}"):
        text = st.text_area("Research question", value=q["text"] if q else "", max_chars=2000)
        if st.form_submit_button("Save question"):
            _act(st, wf.set_question, text, success="Question saved.")
    if not (rel and q):
        st.info("Bind the releases and save the question to continue.")
        return
    cards = ag.card_catalogue()
    view = wf.question_view()
    p = view["proposal"]
    if p:
        st.markdown("**Question agent's proposal** (a proposal only)")
        st.text(f"Card: {view['proposed_card']['title'] if view['proposed_card'] else 'none fits'}")
        if p["explanation"]:
            st.text(p["explanation"])
        for e in p["agent_errors"]:
            st.warning(f"Assistant output problem: {e}")
        _clarification_forms(st, wf, "question", gen, person)
    else:
        st.markdown("**Optional: ask the question agent** (separate consent)")
        _consent_block(st, wf, ag.QUESTION, gen, "Send to question agent", wf.propose_question)
    st.markdown("**Choose the supported question card**")
    ids = [c["id"] for c in cards]
    if not ids:
        st.error("No question cards are installed.")
        return
    options = [""] + ids
    default = options.index(p["card_id"]) if p and p["card_id"] in ids else 0
    with st.form(f"ai_card_{gen}"):
        cid = st.selectbox("Card", options, index=default,
                           format_func=lambda i: next((c["title"] for c in cards if c["id"] == i), "Choose a card…"))
        chosen = next((c for c in cards if c["id"] == cid), None)
        if chosen:
            st.caption(f"Intended use: {chosen['intended_use']}")
        ok = st.checkbox("I confirm this card matches my question. Only the listed cards are supported.")
        if st.form_submit_button("Confirm card", type="primary"):
            if not ok or not cid:
                st.error("Choose a supported card and tick the confirmation box first.")
            else:
                _act(st, wf.confirm_question, cid, confirmed_by=person, success="Card confirmed.")


def _result_screen(st, wf: IntakeWorkflow, ev: dict, gen: str, person: str) -> None:
    run = ev["run"]
    s = verdict_summary(run, ag.card_catalogue())
    c1, c2 = st.columns(2)
    c1.metric(f"Your question: {s['card_title']}" if s["card_title"] else "Your question", s["question"] or "—")
    c2.metric("Assessment verdict", s["overall"] or "—")
    st.caption("Both values refer to the confirmed question card; this is not a separate overall release verdict. "
               "A person must review the result.")
    st.markdown("**Evidence**")
    st.text(f"Run {run['run_id']} · findings: {run.get('n_findings')} · flagged for review: "
            f"{run.get('flagged_for_review')} · originals unchanged: {run.get('originals_unchanged')}")
    try:
        findings_doc = wf.findings()
        relevant = next((q for q in findings_doc.get("questions", []) if q.get("id") == run.get("card_id")), None)
        if relevant and relevant.get("why"):
            st.markdown("**Why this verdict**")
            st.text(relevant["why"])
        for finding in findings_doc.get("findings", [])[:5]:
            st.markdown(f"**{finding.get('id', 'Finding')}**")
            st.text(finding.get("summary", ""))
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Evidence could not be displayed ({type(exc).__name__}).")
    if run.get("sample_overlap"):
        st.json(run["sample_overlap"])
    for w in run["warnings"]:
        st.warning(w)
    with st.expander("findings.json (local only, never sent to a model)"):
        try:
            st.json(wf.findings())
        except Exception as exc:  # noqa: BLE001
            st.error(friendly_error(exc))
    if ev["review"]:
        st.info(f"Last review: {REVIEW_LABELS[ev['review']['decision']]}. Record another decision when ready.")
    if ev["state"] != "review_pending":
        return
    with st.form(f"ai_review_{gen}"):
        d = st.radio("Decision", ["", *REVIEW_DECISIONS], horizontal=True,
                     format_func=lambda x: REVIEW_LABELS.get(x, "Choose…"))
        reason = st.text_area("Reason")
        if st.form_submit_button("Record review", type="primary"):
            if not d:
                st.error("Choose a decision; nothing is accepted by default.")
            else:
                _act(st, wf.record_review, d, reason=reason, reviewer_role=person, success="Review recorded.")


def render(st, html, ui) -> None:  # html/ui accepted for symmetry with prepare_tab; text is never raw HTML here
    ss = st.session_state
    wf: Optional[IntakeWorkflow] = ss.get(WF_KEY)
    st.caption("Experimental research prototype. " + SCOPE_NOTE)
    person = st.text_input("Your name or role (recorded with each decision)", key="ai_person")
    if ss.get("ai_error"):
        st.error(ss["ai_error"])
    if ss.get("ai_notice"):
        st.success(ss.pop("ai_notice"))
    state = wf.state if wf else "created"
    st.subheader(step_title(state))

    if wf is None or state == "created":
        up = st.file_uploader("Clinical table", type=UPLOAD_TYPES, key="ai_upload")
        if st.button("Upload", type="primary", disabled=up is None):
            def go():
                w = ss.get(WF_KEY) or IntakeWorkflow.create()
                ss[WF_KEY] = w
                w.upload(up.getvalue(), up.name, up.type)
            _act(st, go, success="Upload stored in this session's folder.")
        return

    ev = wf.evidence()
    gen = f"{ev['session_id']}_{len(ev['history'])}"  # new widget keys after every step: no stale choices
    if state == "uploaded":
        u = ev["upload"]
        st.text(f"{u['n_rows']} rows · {u['n_columns']} columns · format {u['format']}")
        _consent_block(st, wf, ag.PREPARATION, gen, "Send to preparation agent", wf.propose_mappings)
        if st.button("Map columns myself (no AI)", key=f"ai_manual_{gen}"):
            _act(st, wf.start_manual_mapping)
    elif state == "mapping_proposed":
        _mapping_screen(st, wf, gen, person)
    elif state == "mapping_reviewed":
        r = ev["mapping_review"]
        st.markdown("**Renames to apply** (to a copy; values unchanged)")
        st.table([{"from": x["source"], "to": x["target"]} for x in r["renames"]] or [{"from": "—", "to": "—"}])
        st.text(f"Unmapped columns kept as is: {', '.join(r['unmapped_columns']) or 'none'}")
        with st.form(f"ai_approve_{gen}"):
            ok = st.checkbox(APPROVAL_STATEMENT)
            if st.form_submit_button("Approve as data owner", type="primary"):
                _act(st, wf.approve, data_owner_confirmed=ok, approved_by=person, success="Approved.")
    elif state == "approved":
        if st.button("Create prepared copy", type="primary", key=f"ai_prep_{gen}"):
            _act(st, wf.prepare, success="Prepared copy written; values checked unchanged.")
    elif state in ("prepared", "question_proposed"):
        _question_screen(st, wf, ev, gen, person)
    elif state in ("question_confirmed", "firewall_failed"):
        qc = ev["question_confirmation"]
        st.text(f"Confirmed card: {qc['card_id']}")
        if state == "firewall_failed":
            st.error(f"Last run produced no verdict: {ev['run']['error']}")
        if st.button("Run the firewall", type="primary", key=f"ai_run_{gen}"):
            _act(st, wf.run_firewall, success="Run finished.")
    elif state in ("review_pending", "reviewed"):
        _result_screen(st, wf, ev, gen, person)
        if state == "reviewed":
            with st.form(f"ai_close_{gen}"):
                purge = st.checkbox("Also delete the findings (results folder)")
                if st.form_submit_button("Close session (deletes upload and prepared data)"):
                    _act(st, wf.close, purge_findings=purge, success="Session closed.")
    elif state == "closed":
        st.json(ev["closed"])
        if st.button("Start a new session", key=f"ai_new_{gen}"):
            for k in [k for k in ss.keys() if str(k).startswith("ai_")]:
                del ss[k]
            st.rerun()
    with st.expander("Limitations"):
        for l in LIMITATIONS:
            st.markdown(f"- {l}")
