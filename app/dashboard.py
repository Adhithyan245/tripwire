"""Driftwire dashboard (Role 4). Run from the repo root:  streamlit run app/dashboard.py

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

PRACTICE_CODE = ["orange", "meadow", "pilot", "lantern"]  # public code, published in the challenge repo
VERDICT_HELP = {
    "Ready": "Nothing this result depends on changed.",
    "Conditional": "Its inputs changed, but the result stayed within the stated tolerance. Usable, with care.",
    "Blocked": "The result moved beyond tolerance, its conclusion flipped, or something changed that nothing explains.",
    "Insufficient Evidence": "Too few samples, missing data, or a required check that didn't run. Never read as a pass.",
}
TOUR = [
    ("Welcome to Driftwire",
     "A new data release can keep the **same sample count** while samples are swapped, copied or dropped underneath. "
     "Driftwire compares two releases, finds what changed, works out which results that breaks, and says what it "
     "can't see.\n\nThis tour takes under a minute. *Research use only: no diagnosis or clinical claims.*"),
    ("1 · Pick the releases",
     "In the **sidebar**: release A is your trusted baseline. Release B is the new release: pick a folder, or open a "
     "**sealed envelope** with its number and four-word code. You can also upload a findings.json from another "
     "tool, or load the labelled synthetic example."),
    ("2 · Choose a research question",
     "The same release can be fine for one question and not for another. Pick a question in the sidebar, and every "
     "verdict cites the rule that produced it."),
    ("3 · Compare and read the verdicts",
     "Press **Compare releases**. Verdicts come first:\n\n" +
     "\n".join(f"- **{k}**: {v}" for k, v in VERDICT_HELP.items())),
    ("4 · Check the evidence",
     "**Findings & evidence** lists every change with the exact samples, files and fields, why its severity is what "
     "it is, and its limitation. **Trace one sample** follows a sample from the file to the result it moved."),
    ("5 · Review, don't auto-fix",
     "In **Review**, a person approves, rejects or asks for more evidence on each proposed repair, with a reason. "
     "Driftwire never applies a repair or changes source data. Decisions go into the exported findings.json."),
    ("6 · Test it, and know its limits",
     "The **Mutation Lab** (sidebar → View) plants a known change and scores whether Driftwire finds it. **What "
     "Driftwire can't see** lists its blind spots. **Data & export** downloads findings.json and the HTML report.\n\n"
     "Ready? Run the practice demo to see it all on real data."),
]
VERDICT_COLOR = {"Ready": "green", "Conditional": "orange", "Insufficient Evidence": "orange", "Blocked": "red"}
SEV_ICON = {"high": "🔴", "medium": "🟠", "low": "⚪", "none": "⚪"}
LIMITS = [
    "An error present in **both** releases is invisible to a release comparison: Driftwire needs a correct earlier "
    "baseline.",
    "A profile that several samples already share in release A identifies nobody, so matching it is never called a "
    "swap or a copy. A real copy of such a profile is reported only as a value change.",
    "Near-identical copies are called at Pearson r ≥ 0.999 on continuous data (protein, RNA). Copies with more noise "
    "are reported as value changes, not copies.",
    "The RNA file is not compared when the new release leaves it out (the envelopes do this by design).",
    "Tolerances and minimum sample counts are prototype policy choices, not clinical standards (see Data tab).",
    "A swap or copy is inferred from the data; Driftwire can't know why it happened. Every one needs a curator.",
    "Readiness checks that haven't been built are shown as unavailable and never count as a pass.",
]

st.set_page_config(page_title="Driftwire", page_icon="🧭", layout="wide")
sys.path.insert(0, str(ROOT / "app"))
import ui  # noqa: E402  (the visual layer: stylesheet and HTML building blocks)

st.markdown(ui.CSS, unsafe_allow_html=True)


def html(s: str) -> None:
    st.markdown(s, unsafe_allow_html=True)


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
    """HTML status pill (icon + word); render with html() / unsafe_allow_html."""
    return ui.pill(v)


def practice_demo(root: pathlib.Path | None, a_path: str) -> None:
    """One click: open the public practice envelope if needed, compare it, show the result."""
    if root is None or not a_path:
        st.session_state["demo_error"] = "The challenge repo or release A wasn't found; run `python -m driftwire doctor`."
        return
    opened = root / "envelopes" / "opened" / "practice" / "release"
    if not opened.is_dir():
        ok, log = unseal(root, "practice", PRACTICE_CODE)
        if not ok:
            st.session_state["demo_error"] = "Couldn't open the practice envelope:\n" + log[-800:]
            return
    doc, secs = compare(a_path, str(opened), None, None)
    set_document(doc, "comparison", secs)
    st.session_state["demo_error"] = None


@st.dialog("Tour", width="large")
def tour() -> None:
    i = st.session_state.setdefault("tour_step", 0)
    title, body = TOUR[i]
    st.progress((i + 1) / len(TOUR), text=f"Step {i + 1} of {len(TOUR)}")
    st.subheader(title)
    st.markdown(body)
    c1, c2, c3 = st.columns(3)
    if c1.button("Back", disabled=i == 0, use_container_width=True):
        st.session_state["tour_step"] = i - 1
        st.rerun(scope="fragment")
    if i < len(TOUR) - 1:
        if c2.button("Next", type="primary", use_container_width=True):
            st.session_state["tour_step"] = i + 1
            st.rerun(scope="fragment")
        if c3.button("Skip tour", use_container_width=True):
            st.session_state.update(toured=True, tour_step=0)
            st.rerun()
    else:
        if c2.button("Run the practice demo", type="primary", use_container_width=True):
            st.session_state.update(toured=True, tour_step=0, run_demo=True)
            st.rerun()
        if c3.button("Close", use_container_width=True):
            st.session_state.update(toured=True, tour_step=0)
            st.rerun()


# ------------------------------------------------------------------ sidebar: inputs

if st.session_state.get("run_demo"):  # a demo needs the release-check view in compare mode
    st.session_state.update(view="Release check", source="Compare releases")
root = challenge_dir()
if root is None:  # hosted only: fetch the organizers' public data once per server (see app/hosted_bootstrap.py)
    sys.path.insert(0, str(ROOT / "app"))
    from hosted_bootstrap import ensure_challenge_repo

    @st.cache_resource(show_spinner="First start on this server: downloading the organizers' public data…")
    def _bootstrap():
        return ensure_challenge_repo()
    _boot_root, _boot_log = _bootstrap()
    os.environ.setdefault("TRIPWIRE_CHALLENGE_DIR", str(_boot_root or ""))
    root = challenge_dir()
    if root is None:
        st.sidebar.caption("Data download failed on this server: " + (_boot_log[-300:] or "no details"))
st.sidebar.markdown(ui.brand("Skill issue"), unsafe_allow_html=True)
view = st.sidebar.radio("View", ["Release check", "Run on your data", "Mutation Lab", "Prepare data with AI"], horizontal=True, key="view")
t1, t2 = st.sidebar.columns(2)
if t1.button("Take the tour", use_container_width=True):
    st.session_state.update(tour_step=0, show_tour=True)
if t2.button("Practice demo", use_container_width=True,
             help="Open the public practice envelope and compare it with release A, in one click."):
    st.session_state["run_demo"] = True
    st.rerun()
st.sidebar.markdown(ui.section("1 · Source"), unsafe_allow_html=True)
source = st.sidebar.radio("Findings source", ["Compare releases", "Upload findings.json", "Synthetic example"],
                          key="source", disabled=view != "Release check", label_visibility="collapsed")
st.sidebar.markdown(ui.section("2 · Releases"), unsafe_allow_html=True)
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

st.sidebar.markdown(ui.section("3 · Question"), unsafe_allow_html=True)
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

def clear_document():
    """Prevent a failed replacement from leaving an old result available for review/export."""
    st.session_state.update(doc=None, secs=None, decisions={}, document_origin=None,
                            upload_fingerprint=None, demo_error=None)


def set_document(document, origin, seconds=None):
    generation = st.session_state.get("document_generation", 0) + 1
    existing = {d["repair_id"]: {k: d[k] for k in ("decision", "reason", "reviewer_role")}
                for d in document.get("decisions", [])}
    st.session_state.update(doc=document, secs=seconds, decisions=existing, document_origin=origin,
                            document_generation=generation)


if run:
    clear_document()
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
        clear_document()
        try:
            set_document(parse_findings(upload.getvalue()), "upload")
            st.session_state["upload_fingerprint"] = fingerprint
        except ValueError as e:
            st.error(f"Couldn't load findings: {e}")
            st.stop()
if load_example:
    set_document(parse_findings((ROOT / "app" / "synthetic.json").read_bytes()), "synthetic")

if st.session_state.pop("run_demo", False):
    clear_document()
    with st.spinner("Opening the practice envelope and comparing it with release A…"):
        try:
            practice_demo(root, a_path)
        except Exception as e:
            st.session_state["demo_error"] = str(e)

# first visit: the tour opens by itself once
if st.session_state.pop("show_tour", False) or not st.session_state.get("toured"):
    st.session_state["toured"] = True
    tour()

doc = st.session_state.get("doc")

# ------------------------------------------------------------------ main: nothing yet

if view == "Release check":
    html(ui.app_bar())
if st.session_state.get("demo_error"):
    st.error(st.session_state["demo_error"])

if view == "Run on your data":
    try:
        from own_data_tab import render as render_own
    except ImportError:
        sys.path.insert(0, str(ROOT / "app"))
        from own_data_tab import render as render_own
    render_own(st, html, ui, a_path)
    st.stop()

if view == "Prepare data with AI":
    try:
        from prepare_tab import render as render_prepare
    except ImportError:
        sys.path.insert(0, str(ROOT / "app"))
        from prepare_tab import render as render_prepare
    render_prepare(st, html, ui)
    st.stop()

if view == "Mutation Lab":
    try:
        from mutation_tab import render as render_lab
    except ImportError:
        sys.path.insert(0, str(ROOT / "app"))
        from mutation_tab import render as render_lab
    render_lab(st, a_path)
    st.stop()

if source == "Compare releases" and doc is None:
    html(ui.home("Catch the silent changes in a data release",
                 "A new release can keep the same number of samples while some are swapped, copied or dropped. "
                 "Driftwire detects supported changes, checks which results they affect, and gives each one a verdict "
                 "with the evidence behind it."))
    c1, c2, c3 = st.columns(3)
    with c1.container(border=True):
        html('<div class="tw-step">Try it</div><div class="tw-ct">See it work in one click</div>'
             '<div class="tw-cm">Opens the public practice envelope and compares it with release A.</div>')
        if st.button("Run the practice demo", type="primary", use_container_width=True, key="demo_main"):
            st.session_state["run_demo"] = True
            st.rerun()
    with c2.container(border=True):
        html('<div class="tw-step">Your data</div><div class="tw-ct">Check your own release</div>'
             '<div class="tw-cm">Pick release B in the sidebar, or open a sealed envelope with its number and four '
             'words, then press Compare releases. You can also upload a findings.json.</div>')
    with c3.container(border=True):
        html('<div class="tw-step">Proof</div><div class="tw-ct">Prove it catches changes</div>'
             '<div class="tw-cm">Switch the sidebar View to Mutation Lab: plant a known change and watch Driftwire '
             'find it blind.</div>')
    st.markdown("#### What the verdicts mean")
    html(ui.legend(VERDICT_HELP))
    st.caption("New here? Press **Take the tour** in the sidebar.")
    st.stop()

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
rel = doc["data"]["releases"]
secs = st.session_state.get("secs")
verdict = doc.get("verdict", "")
html(ui.hero(verdict, VERDICT_HELP.get(verdict, ""), doc.get("question", ""),
             f"{rel[0]['name']} → {rel[-1]['name']}" + (f" · compared in {secs:.1f} s" if secs is not None else "")))
qs = doc.get("questions", [])
html(ui.tiles([("findings", str(len(doc.get("findings", [])))),
               ("awaiting human review", str(len(status["open"]))),
               ("research questions blocked", f"{sum(q.get('verdict') == 'Blocked' for q in qs)} of {len(qs)}")
               if qs else ("analyses checked", str(len(doc.get("analyses", [])))),
               ("repairs applied automatically", "0")]))
html(ui.note("Research use only.", "Every swap or duplicate needs a curator's review. Repairs are proposals and are "
                                   "never applied automatically."))
_plan = doc.get("next_steps")
if _plan:
    p1, p2 = st.columns([3, 2])
    with p1:
        html(ui.plan(_plan))
    with p2:
        html(ui.cannot_tell(_plan))

tabs = st.tabs(["Verdicts", "Findings & evidence", f"Review ({len(status['open'])} open)", "What Driftwire can't see",
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
                use = "model training" if q.get("intended_use") == "model_training" else q.get("intended_use", "")
                html(ui.card_head(q["verdict"], q["title"], f"{use} · {q['cohort']}", q["why"]))
                if gaps:
                    st.caption(f"Checks not run (not a pass): {', '.join(gaps)}")
                ran = [c for c in q.get("checks", []) if c.get("status") not in ("skipped", "unavailable")]
                if ran:
                    icon = {"pass": "✅", "fixable": "🟠", "insufficient": "⚪", "fail": "🔴"}
                    with st.expander(f"Readiness checks ({len(ran)})"):
                        for c in ran:
                            st.markdown(f"{icon.get(c['status'], '•')} **{c['name']}** ({c['status']}): {c['summary']}"
                                        + (f"  \n**Fix:** {c['fix']}" if c.get("fix") else ""))
                if q.get("relevant_findings"):
                    st.caption(f"Relevant findings: {', '.join(q['relevant_findings'])}")
    st.subheader("Analyses")
    for a in doc.get("analyses", []):
        with st.container(border=True):
            html(ui.card_head(a["verdict"], f"{a['id']} · {a.get('title', '')}", f"result {a['status']}", a["why"]))
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
            html(ui.sev_pill(f.get("severity", "none")) + (" <span class='tw-pill warn'><i>!</i>needs human review"
                                                            "</span>" if f.get("needs_human_review") else "")
                 + f"<div class='tw-cb'>{ui.esc(f['summary'])}</div>")
            if f.get("severity_reason"):
                st.markdown(f"**Why this severity:** {f['severity_reason']}")
            st.markdown(f"**Affects:** {', '.join(f.get('affects_analyses', [])) or 'none'} · **Not affected:** "
                        f"{', '.join(f.get('not_affected_analyses', [])) or 'none'}")
            if f.get("relevant_questions"):
                st.markdown(f"**Questions:** {', '.join(f['relevant_questions'])}")
            if f.get("limitation"):
                st.caption(f"Limitation: {f['limitation']}")
            evdf = pd.DataFrame(f.get("evidence", []))
            cfg = {"url": st.column_config.LinkColumn("slide", display_text="View slide",
                                                      help="The sample's tissue slide in NCI's public IDC viewer")} \
                if "url" in evdf.columns else None
            st.dataframe(evdf, hide_index=True, use_container_width=True, column_config=cfg)

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
    allp = doc.get("repair_preview_all") or {}
    if allp.get("analyses"):
        with st.container(border=True):
            st.markdown(f"**If every proposed repair were approved** ({', '.join(allp.get('repairs', []))})")
            for x in allp["analyses"]:
                html(f"{verdict_badge(x['verdict_if_approved'])} {ui.esc(x['summary'])}")
            st.caption(allp.get("note", ""))
    role = st.text_input("Your role", st.session_state.get("role", ""), placeholder="e.g. data curator")
    st.session_state["role"] = role
    for r in doc.get("repairs", []):
        with st.container(border=True):
            done = r["id"] in decisions
            st.markdown(f"**{r['id']} · {r['action']}** for {', '.join(r.get('addresses', []))}"
                        + ("  :green[✓ decided]" if done else ""))
            st.write(r["justification"])
            st.caption("Targets: " + ", ".join(t["id"] for t in r.get("targets", []))[:400])
            pv = r.get("preview") or {}
            for x in pv.get("analyses", []):
                html(f"<div class='tw-cm'>If approved</div>{verdict_badge(x['verdict_now'])} → "
                     f"{verdict_badge(x['verdict_if_approved'])} <span class='tw-cm'>{ui.esc(x['summary'])}</span>")
            if pv.get("note"):
                st.caption(pv["note"])
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
    st.subheader("What Driftwire can't see")
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
