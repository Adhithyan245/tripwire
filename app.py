"""Read and display Tripwire findings. This interface does not calculate verdicts."""
import json
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Tripwire", page_icon="🔎", layout="wide")
st.title("Tripwire")
st.caption("Research use only. Not a diagnosis, treatment advice, risk score or clinical claim.")
st.write("See what changed between releases, which analyses are affected, and what needs review.")

source = st.radio("Findings source", ["Synthetic example", "Upload findings.json"], horizontal=True)
if source == "Synthetic example":
    st.warning("Synthetic demonstration data — not a real release or detection result.")
    raw = (Path(__file__).parent / "examples" / "synthetic.json").read_bytes()
else:
    upload = st.file_uploader("Upload Tripwire findings.json", type=["json"])
    if upload is None:
        st.info("Choose a findings JSON file to view its results.")
        st.stop()
    raw = upload.getvalue()

try:
    doc = json.loads(raw)
    if not isinstance(doc, dict):
        raise ValueError("The JSON must contain an object at the top level.")
    for key in ("analyses", "findings", "repairs"):
        if key in doc and (not isinstance(doc[key], list) or not all(isinstance(item, dict) for item in doc[key])):
            raise ValueError(f"'{key}' must be a list of objects.")
    if "settings" in doc and not isinstance(doc["settings"], dict):
        raise ValueError("'settings' must be an object.")
except (ValueError, UnicodeDecodeError) as exc:
    st.error(f"Could not read findings: {exc}")
    st.stop()

st.caption("The interface displays supplied results; it does not validate their scientific correctness or run the detector.")
st.subheader("Overall verdict")
st.write(doc.get("verdict") or "Not provided")
if doc.get("question"):
    st.write(doc["question"])

st.header("Analyses")
analyses = doc.get("analyses", [])
if not analyses:
    st.info("No analysis results were provided.")
for analysis in analyses:
    title = f"{analysis.get('id', 'Analysis')} · {analysis.get('title', 'Untitled')}"
    with st.expander(title, expanded=True):
        st.write("**Verdict:**", analysis.get("verdict") or "Not provided")
        st.write("**Reason:**", analysis.get("why") or "Not provided")
        st.write("**Impact:**", analysis.get("impact") or "Not provided")
        if analysis.get("rerun_reason"):
            st.write("**Rerun:**", analysis["rerun_reason"])
        if analysis.get("inputs"):
            st.write("**Inputs:**", analysis["inputs"])
        if analysis.get("cohort"):
            st.write("**Cohort:**", analysis["cohort"])
        left, right = st.columns(2)
        for col, label, key in ((left, "Before", "before"), (right, "After", "after")):
            with col:
                st.write(f"**{label}**")
                if analysis.get(key) is None:
                    st.caption("Not available")
                else:
                    st.json(analysis[key])

st.header("Findings and evidence")
findings = doc.get("findings", [])
if not findings:
    st.info("No findings were provided. This does not prove the release is error-free.")
for finding in findings:
    with st.expander(f"{finding.get('id', 'Finding')} · {finding.get('kind', 'Change')}", expanded=True):
        st.write(finding.get("summary") or "No summary provided.")
        st.write("**Severity:**", finding.get("severity") or "Not provided")
        st.write("**Human review:**", "Required" if finding.get("needs_human_review") is True else "Not specified" if finding.get("needs_human_review") is not False else "Not flagged")
        st.write("**Affected analyses:**", finding.get("affects_analyses", []))
        st.write("**Not affected:**", finding.get("not_affected_analyses", []))
        st.write("**Evidence:**")
        if finding.get("evidence"):
            st.json(finding["evidence"])
        else:
            st.caption("No evidence provided.")
        st.write("**Limitation:**", finding.get("limitation") or "Not provided")

st.header("Limitations")
st.info("A release comparison cannot establish why a change occurred or detect errors shared by both releases. Review the evidence and the limitations on each finding.")
st.header("Proposed repairs")
st.caption("Proposals require human review; Tripwire does not apply them automatically.")
if not doc.get("repairs"):
    st.write("No proposed repairs provided.")
for repair in doc.get("repairs", []):
    with st.expander(f"{repair.get('id', 'Repair')} · {repair.get('action', 'Proposal')}"):
        st.write(repair.get("justification") or "No justification provided.")
        st.json({"targets": repair.get("targets", []), "addresses": repair.get("addresses", [])})
with st.expander("Settings and tolerances"):
    if doc.get("settings"):
        st.json(doc["settings"])
    else:
        st.write("No settings provided.")
