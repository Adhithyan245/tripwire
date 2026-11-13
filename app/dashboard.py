"""Tripwire dashboard (Role 4). Run from the repo root:  streamlit run app/dashboard.py

Pick release A and B (or open a sealed envelope), compare, see verdicts first, trace any finding to its evidence,
record a review decision for every proposed repair, and download findings.json. Research use only.
"""
from __future__ import annotations

import inspect
import json
import os
import pathlib
import subprocess
import sys
import time

import pandas as pd
import streamlit as st

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tripwire.contract import load_changes  # noqa: E402
from tripwire.dashboard_input import parse_findings  # noqa: E402
from tripwire.findings import build  # noqa: E402
from tripwire.release import Release  # noqa: E402
from tripwire.review import DECISIONS, LABELS, apply_decisions, review_status  # noqa: E402
from tripwire.validate import challenge_dir, validate  # noqa: E402

try:  # question cards (PR #5) may not be merged yet
    from tripwire.questions import CARDS
except ImportError:
    CARDS = []
try:  # HTML report (PR #11) may not be merged yet
    from tripwire.report import render as render_report
except ImportError:
    render_report = None

VERDICT_COLOR = {"Ready": "green", "Conditional": "orange", "Insufficient Evidence": "orange", "Blocked": "red"}
SEV_ICON = {"high": "🔴", "medium": "🟠", "low": "⚪", "none": "⚪"}
LIMITS = [
    "An error present in **both** releases is invisible to a release comparison: Tripwire needs a correct earlier "
    "baseline.",
    "A profile that several samples already share in release A identifies nobody, so matching it is never called a "
    "swap or a copy. A real copy of such a profile is reported only as a value change.",
    "Near-identical copies are called at Pearson r ≥ 0.999 on continuous data (protein, RNA). Copies with more noise "
    "are reported as value changes, not copies.",
    "The RNA file is not compared when the new release leaves it out (the envelopes do this by design).",
    "Tolerances and minimum sample counts are prototype policy choices, not clinical standards (see Data tab).",
    "A swap or copy is inferred from the data; Tripwire can't know why it happened. Every one needs a curator.",
    "Readiness checks that haven't been built are shown as unavailable and never count as a pass.",
]

st.set_page_config(page_title="Tripwire", page_icon="🧭", layout="wide")


# ------------------------------------------------------------------ data helpers

def releases_on_disk(root: pathlib.Path | None) -> dict[str, pathlib.Path]:
    found = {}
    if root is None:
        return found
    for p in sorted((root / "data" / "tcga-brca" / "releases").glob("*")):
        if (p / "clinical.tsv").exists():
            found[f"release · {p.name}"] = p
    for p in sorted((root / "envelopes" / "opened").glob("*/release")):
        if (p / "clinical.tsv").exists():
            found[f"envelope · {p.parent.name}"] = p
    return found


def unseal(root: pathlib.Path, number: str, words: list[str]) -> tuple[bool, str]:
    env = dict(os.environ, PYTHONUTF8="1", PYTHONPATH=str(ROOT))
    lf = (ROOT / "tripwire" / "unseal_lf.py").exists()  # LF line endings so the organizers' check passes on Windows
    cmd = [sys.executable, "-m", "tripwire.unseal_lf"] if lf else [sys.executable, "envelopes/unseal.py"]
    r = subprocess.run(cmd + [number, *words], cwd=root, env=env, capture_output=True, text=True, encoding="utf-8")
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def compare(a_path: str, b_path: str, question: str | None, changes_file: str | None) -> tuple[dict, float]:
    t0 = time.time()
    a, b = Release(a_path), Release(b_path)
    if changes_file:
        changes = load_changes(changes_file)
    else:
        from tripwire.detect import detect_changes
        changes = detect_changes(a, b)
    kw = {"question": question} if question and "question" in inspect.signature(build).parameters else {}
    return build(changes, a, b, **kw), time.time() - t0


def verdict_badge(v: str) -> str:
    return f":{VERDICT_COLOR.get(v, 'gray')}-background[**{v}**]"


# ------------------------------------------------------------------ sidebar: inputs

root = challenge_dir()
st.sidebar.title("🧭 Tripwire")
st.sidebar.caption("Cohort Control Tower · team Skill issue")
source = st.sidebar.radio("Findings source", ["Compare releases", "Upload findings.json", "Synthetic example"])
if root is None:
    st.sidebar.error("Challenge repo not found. Clone it next to this repo, or set TRIPWIRE_CHALLENGE_DIR.")
default_a = str(root / "data" / "tcga-brca" / "raw") if root else ""
a_path = st.sidebar.text_input("Release A (trusted baseline)", default_a)

with st.sidebar.expander("Open a sealed envelope", expanded=False):
    num = st.text_input("Envelope number", placeholder="07 or practice")
    code = st.text_input("Four-word code", placeholder="amber falcon river quartz")
    if st.button("Open envelope", disabled=root is None):
        words = code.replace("-", " ").split()
        if not num or len(words) != 4:
            st.warning("Enter the envelope number and exactly four words.")
        else:
            with st.spinner("Opening with the organizers' unseal.py…"):
                ok, log = unseal(root, num.strip(), words)
            (st.success if ok else st.error)("Envelope opened." if ok else "Couldn't open it; see the log.")
            st.code(log[-1500:] or "(no output)")

found = releases_on_disk(root)
choice = st.sidebar.selectbox("Release B (new)", list(found) + ["Other folder…"], index=0 if found else None)
b_path = st.sidebar.text_input("Folder", "") if choice == "Other folder…" or not found else str(found[choice])

q_options = ["Release check: does it affect A1 and A2?"] + [c.title for c in CARDS]
q_pick = st.sidebar.selectbox("Research question", q_options)
question = None if q_pick == q_options[0] else next(c.id for c in CARDS if c.title == q_pick)
if not CARDS:
    st.sidebar.caption("Question cards arrive with PR #5.")

with st.sidebar.expander("Advanced"):
    changes_file = st.text_input("Use a changes file instead of the detector (testing)", "")

run = st.sidebar.button("Compare releases", type="primary", disabled=source != "Compare releases" or not (a_path and b_path), use_container_width=True)
upload = st.sidebar.file_uploader("Upload findings.json", type=["json"]) if source == "Upload findings.json" else None
load_example = st.sidebar.button("Load synthetic example") if source == "Synthetic example" else False
st.sidebar.divider()
st.sidebar.caption("Research use only. Not a diagnosis, treatment advice, risk score or clinical claim.")

def set_document(document, origin, seconds=None):
    generation = st.session_state.get("document_generation", 0) + 1
    existing = {d["repair_id"]: {k: d[k] for k in ("decision", "reason", "reviewer_role")}
                for d in document.get("decisions", [])}
    st.session_state.update(doc=document, secs=seconds, decisions=existing, document_origin=origin,
                            document_generation=generation)


if run:
    try:
        with st.spinner("Comparing every file, mapping impact, rerunning analyses…"):
            doc, secs = compare(a_path, b_path, question, changes_file or None)
        set_document(doc, "comparison", secs)
    except Exception as e:  # show the problem instead of a stack trace
        st.error(f"Couldn't compare these releases: {e}")

if upload is not None:
    import hashlib
    fingerprint = hashlib.sha256(upload.getvalue()).hexdigest()
    if fingerprint != st.session_state.get("upload_fingerprint") or st.session_state.get("document_origin") != "upload":
        try:
            set_document(parse_findings(upload.getvalue()), "upload")
            st.session_state["upload_fingerprint"] = fingerprint
        except ValueError as e:
            st.error(f"Couldn't load findings: {e}")
            st.stop()
if load_example:
    set_document(parse_findings((ROOT / "app" / "synthetic.json").read_bytes()), "synthetic")

doc = st.session_state.get("doc")

# ------------------------------------------------------------------ main: nothing yet

st.title("Tripwire")
st.markdown("**Same sample count, different data.** Tripwire tells you what changed, what it breaks, and what it "
            "can't see.")
if source == "Upload findings.json" and upload is None:
    st.info("Choose a findings JSON file in the sidebar.")
    st.stop()
if source == "Synthetic example" and st.session_state.get("document_origin") != "synthetic":
    st.info("Select **Load synthetic example** in the sidebar.")
    st.stop()
if source == "Compare releases" and st.session_state.get("document_origin") not in (None, "comparison"):
    st.info("Choose releases and select **Compare releases** in the sidebar.")
    st.stop()
if doc is None:
    st.info("Compare releases, upload a findings file, or load the synthetic example from the sidebar.")
    st.stop()
if st.session_state.get("document_origin") == "synthetic":
    st.warning("Synthetic demonstration data: invented results, not a real release comparison.")
elif st.session_state.get("document_origin") == "upload":
    st.info("Uploaded findings: displaying the supplied results; structural checks do not verify their correctness.")

# ------------------------------------------------------------------ verdict first

decisions: dict = st.session_state.setdefault("decisions", {})
status = review_status(apply_decisions(doc, decisions) if decisions else doc)
c1, c2 = st.columns([3, 2])
with c1:
    st.markdown(f"### {verdict_badge(doc.get('verdict', ''))}")
    st.markdown(f"**{doc.get('question', '')}**")
    rel = doc["data"]["releases"]
    secs = st.session_state.get("secs")
    st.caption(f"{rel[0]['name']} → {rel[-1]['name']}" + (f" · compared in {secs:.1f} s" if secs is not None else ""))
with c2:
    m1, m2, m3 = st.columns(3)
    m1.metric("Findings", len(doc.get("findings", [])))
    m2.metric("Awaiting review", len(status["open"]))
    m3.metric("Repairs applied", 0, help="Repairs are proposals for a reviewer. Tripwire never applies them.")
st.warning("**Research use only.** Every swap or duplicate needs a curator's review. Repairs are proposals and are "
           "never applied automatically.", icon="⚠️")

tabs = st.tabs(["Verdicts", "Findings & evidence", f"Review ({len(status['open'])} open)", "What Tripwire can't see",
                "Data & export"])

# ------------------------------------------------------------------ verdicts

with tabs[0]:
    if doc.get("questions"):
        st.subheader("Research questions")
        st.caption("The same release can be fine for one question and not for another. Each verdict cites its rule.")
        for q in doc["questions"]:
            cov = q.get("coverage", {})
            gaps = [c for k in ("skipped", "unavailable", "missing") for c in cov.get(k, [])]
            with st.container(border=True):
                st.markdown(f"{verdict_badge(q['verdict'])} **{q['title']}**  \n"
                            f":gray[{q['intended_use']} · {q['cohort']}]")
                st.write(q["why"])
                if gaps:
                    st.caption(f"Checks not run (not a pass): {', '.join(gaps)}")
                if q.get("relevant_findings"):
                    st.caption(f"Relevant findings: {', '.join(q['relevant_findings'])}")
    st.subheader("Analyses")
    for a in doc.get("analyses", []):
        with st.container(border=True):
            st.markdown(f"{verdict_badge(a['verdict'])} **{a['id']} · {a.get('title', '')}** :gray[({a['status']})]")
            st.write(a["why"])
            if a.get("impact"):
                st.caption(a["impact"])
            ic = a.get("input_changes")
            if ic:
                st.caption(f"Sample by sample, what it reads: {ic['identical']} identical, {ic['added']} entered, "
                           f"{ic['removed']} left, {ic['values_changed']} changed value.")
            if a.get("before"):
                after = a.get("after") or {}
                keys = list(dict.fromkeys(list(a["before"]) + list(after)))
                rows = [{"result": k, "before": json.dumps(a["before"].get(k)), "after": json.dumps(after.get(k)),
                         "moved": "←" if a["before"].get(k) != after.get(k) else ""} for k in keys]
                st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

# ------------------------------------------------------------------ findings and evidence

with tabs[1]:
    findings = doc.get("findings", [])
    if not findings:
        st.info("No findings were provided. This does not prove the release is error-free.")
    sev_filter = st.multiselect("Severity", ["high", "medium", "low"], default=["high", "medium", "low"])
    for f in findings:
        if f.get("severity") not in sev_filter:
            continue
        with st.expander(f"{SEV_ICON.get(f.get('severity'), '')} {f['id']} · {f.get('kind')} · "
                         f"{f.get('severity')} severity" + (" · needs review" if f.get("needs_human_review") else "")):
            st.write(f["summary"])
            if f.get("severity_reason"):
                st.markdown(f"**Why this severity:** {f['severity_reason']}")
            st.markdown(f"**Affects:** {', '.join(f.get('affects_analyses', [])) or 'none'} · **Not affected:** "
                        f"{', '.join(f.get('not_affected_analyses', [])) or 'none'}")
            if f.get("relevant_questions"):
                st.markdown(f"**Questions:** {', '.join(f['relevant_questions'])}")
            if f.get("limitation"):
                st.caption(f"Limitation: {f['limitation']}")
            st.dataframe(pd.DataFrame(f.get("evidence", [])), hide_index=True, use_container_width=True)

    st.subheader("Trace one sample")
    samples = sorted({e["id"] for f in findings for e in f.get("evidence", []) if e.get("kind") == "sample"})
    pick = st.selectbox("Sample", samples, index=None, placeholder="Pick a sample cited in the findings")
    if pick:
        rows = [{"finding": f["id"], "kind": f.get("kind"), "affects": ", ".join(f.get("affects_analyses", [])),
                 "release": e.get("release"), "file": e.get("file"), "note": e.get("note", "")}
                for f in findings for e in f.get("evidence", []) if e.get("id") == pick]
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        touched = sorted({a for r in rows for a in r["affects"].split(", ") if a})
        for a in doc.get("analyses", []):
            if a["id"] in touched and a.get("before"):
                st.caption(f"{a['id']} reads {', '.join(a.get('inputs', []))} for: {a.get('cohort', '')}. "
                           f"Result before → after: {json.dumps(a['before'])} → {json.dumps(a['after'])}")

# ------------------------------------------------------------------ review

with tabs[2]:
    st.caption("A reviewer decides on each proposed repair. Recording a decision never applies the repair or changes "
               "source data.")
    role = st.text_input("Your role", st.session_state.get("role", ""), placeholder="e.g. data curator")
    st.session_state["role"] = role
    for r in doc.get("repairs", []):
        with st.container(border=True):
            done = r["id"] in decisions
            st.markdown(f"**{r['id']} · {r['action']}** for {', '.join(r.get('addresses', []))}"
                        + ("  :green[✓ decided]" if done else ""))
            st.write(r["justification"])
            st.caption("Targets: " + ", ".join(t["id"] for t in r.get("targets", []))[:400])
            prev = decisions.get(r["id"], {})
            widget_id = f"{st.session_state['document_generation']}_{r['id']}"
            d = st.radio("Decision", DECISIONS, format_func=LABELS.get, key=f"d_{widget_id}", horizontal=True,
                         index=DECISIONS.index(prev["decision"]) if prev else None)
            reason = st.text_input("Reason", prev.get("reason", ""), key=f"r_{widget_id}")
            if st.button("Record decision", key=f"b_{widget_id}"):
                try:
                    trial = {**decisions, r["id"]: {"decision": d, "reason": reason, "reviewer_role": role}}
                    apply_decisions(doc, trial)
                    decisions.update(trial)
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
    if not doc.get("repairs"):
        st.info("Nothing to review: no repairs were proposed.")

# ------------------------------------------------------------------ limitations

with tabs[3]:
    st.subheader("What Tripwire can't see")
    for item in LIMITS:
        st.markdown(f"- {item}")
    gaps = sorted({c for q in doc.get("questions", []) for k in ("skipped", "unavailable", "missing")
                   for c in q.get("coverage", {}).get(k, [])})
    if gaps:
        st.markdown(f"- In this run, these checks didn't run: **{', '.join(gaps)}**.")
    st.markdown("- Per-finding limitations are listed on each finding.")

# ------------------------------------------------------------------ data and export

with tabs[4]:
    final = apply_decisions(doc, decisions) if decisions else doc
    try:
        errs = validate(final)
        (st.success if not errs else st.error)("findings.json passes the organizers' validator." if not errs else
                                               "Validator errors: " + "; ".join(errs))
    except FileNotFoundError:
        st.warning("Validator not found: the challenge repo isn't next to this one.")
    name = rel[-1]["name"]
    cols = st.columns(2)
    cols[0].download_button("Download findings.json", json.dumps(final, indent=2), f"findings-{name}.json",
                            "application/json", use_container_width=True)
    if render_report:
        try:
            report = render_report(final)
            cols[1].download_button("Download HTML report", report, f"findings-{name}.html", "text/html", use_container_width=True)
        except (KeyError, TypeError, ValueError) as e:
            cols[1].warning(f"HTML report unavailable for this file: {e}")
    if final.get("settings"):
        st.caption("Tolerances and minimums (prototype policy, not clinical standards)")
        st.json(final["settings"])
    for r in rel:
        st.caption(f"Release {r['name']}: file fingerprints")
        st.dataframe(pd.DataFrame(r.get("files", [])), hide_index=True, use_container_width=True)
