"""Dashboard view "Run on your data": two folders (or uploads, or a sealed envelope), a question, Check layout, Run.

Run calls the CLI itself (tripwire.__main__.main with the same arguments a judge would type), so the dashboard has no
comparison logic of its own and its findings.json is byte-for-byte the CLI's. Everything runs on this machine.
"""
from __future__ import annotations

import contextlib
import io
import json
import pathlib
import tempfile

UPLOAD_LIMIT_MB = 200  # Streamlit's default server.maxUploadSize; folder paths have no limit
REFERENCE_ONLY = "Reference analyses only (A1 and A2)"
EXIT_MESSAGES = {
    0: "Findings written; the organizers' format/validate.py passed.",
    1: "Findings written, but the organizers' validator found problems (listed below).",
    2: "Driftwire couldn't compare these folders: a folder is missing or a file can't be read. "
       "Press Check layout to see which.",
    3: "The envelope didn't open. Check the number and the four words; the log below says why.",
    4: "The release didn't clear the --fail-on gate (findings were still written).",
}


def run_cli(argv: list[str]) -> tuple[int, str]:
    """Run `python -m driftwire <argv>` in this process; returns (exit code, everything it printed)."""
    from tripwire.__main__ import main
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            rc = main(argv)
        except SystemExit as e:  # argparse errors
            rc = e.code if isinstance(e.code, int) else 2
    return rc, buf.getvalue()


def run_compare(a: str, b: str, question: str | None, out_dir) -> tuple[int, str, pathlib.Path]:
    """The CLI's diff command, exactly: python -m driftwire diff A B --out <out_dir>/findings.json [--question q]."""
    out = pathlib.Path(out_dir) / "findings.json"
    argv = ["diff", str(a), str(b), "--out", str(out)] + (["--question", question] if question else [])
    rc, log = run_cli(argv)
    return rc, log, out


def run_envelope(number: str, words: list[str], question: str | None, out_dir) -> tuple[int, str, pathlib.Path]:
    """The CLI's envelope command, exactly."""
    out = pathlib.Path(out_dir) / "findings.json"
    argv = ["envelope", number, *words, "--out", str(out)] + (["--question", question] if question else [])
    rc, log = run_cli(argv)
    return rc, log, out


def save_uploads(files, dest: pathlib.Path) -> pathlib.Path:
    """Write uploaded files into a fresh folder under their own names (no other change)."""
    dest.mkdir(parents=True, exist_ok=True)
    for f in files:
        (dest / pathlib.Path(f.name).name).write_bytes(f.getvalue())
    return dest


def render(st, html, ui, default_a: str = "") -> None:
    from tripwire.__main__ import verdict_table
    from tripwire.inspect import inspect_folder
    from tripwire.questions import CARDS

    st.markdown("## Run on your data")
    html(ui.note("Runs entirely on this machine.", "Your data is not uploaded anywhere. Driftwire reads the two "
                                                    "folders and writes findings.json and the report to a temporary "
                                                    "folder on this machine, for you to download."))
    mode = st.radio("Input", ["Two folders", "Upload files", "Sealed envelope"], horizontal=True, key="own_mode")
    tmp = pathlib.Path(st.session_state.setdefault("own_tmp", tempfile.mkdtemp(prefix="driftwire_")))
    a = b = None
    number, words = "", []
    if mode == "Two folders":
        c1, c2 = st.columns(2)
        a = c1.text_input("Release A (trusted) folder", default_a, key="own_a")
        b = c2.text_input("Release B (new) folder", "", key="own_b", placeholder="D:/data/release_2025_06")
    elif mode == "Upload files":
        st.caption(f"Each file can be up to {UPLOAD_LIMIT_MB} MB. For larger releases, use Two folders: folder "
                   "paths have no size limit.")
        c1, c2 = st.columns(2)
        fa = c1.file_uploader("Release A (trusted) files", accept_multiple_files=True, key="own_fa")
        fb = c2.file_uploader("Release B (new) files", accept_multiple_files=True, key="own_fb")
        if fa:
            a = str(save_uploads(fa, tmp / "upload_A"))
        if fb:
            b = str(save_uploads(fb, tmp / "upload_B"))
    else:
        c1, c2 = st.columns([1, 3])
        number = c1.text_input("Envelope number", key="own_num", placeholder="07 or practice").strip()
        words = c2.text_input("Four-word code", key="own_words", placeholder="amber falcon river quartz") \
            .replace("-", " ").split()
        st.caption("Opens the envelope with the organizers' unseal.py and compares it with release A: the same "
                   "code as `python -m driftwire envelope`.")

    labels = [REFERENCE_ONLY] + [c.title for c in CARDS]
    pick = st.selectbox("Question", labels, key="own_q")
    question = None if pick == REFERENCE_ONLY else next(c.id for c in CARDS if c.title == pick)

    ready = bool(a and b) if mode != "Sealed envelope" else bool(number and len(words) == 4)
    c1, c2, _ = st.columns([1, 1, 3])
    check = c1.button("Check layout", disabled=mode == "Sealed envelope" or not (a or b), use_container_width=True)
    run = c2.button("Run", type="primary", disabled=not ready, use_container_width=True)
    if mode == "Sealed envelope" and number and len(words) != 4:
        st.warning("Enter exactly four words.")

    if check:
        for label, folder in (("Release A", a), ("Release B", b)):
            if folder:
                show_layout(st, label, inspect_folder(folder))

    if run:
        out_dir = pathlib.Path(tempfile.mkdtemp(prefix="run_", dir=tmp))
        with st.spinner("Running the same command as the CLI…"):
            if mode == "Sealed envelope":
                rc, log, out = run_envelope(number, words, question, out_dir)
            else:
                rc, log, out = run_compare(a, b, question, out_dir)
        st.session_state["own_result"] = {"rc": rc, "log": log, "out": str(out)}

    res = st.session_state.get("own_result")
    if not res:
        return
    rc, out = res["rc"], pathlib.Path(res["out"])
    (st.success if rc == 0 else st.error)(EXIT_MESSAGES.get(rc, f"Driftwire exited with code {rc}."))
    with st.expander("Command output", expanded=rc not in (0, 4)):
        st.code(res["log"][-4000:] or "(no output)")
    if not out.exists():
        return
    doc = json.loads(out.read_text(encoding="utf-8"))
    rel = doc["data"]["releases"]
    html(ui.hero(doc["verdict"], "", doc.get("question", ""), f"{rel[0]['name']} → {rel[-1]['name']}"))
    st.markdown("#### Every question, one verdict each")
    st.markdown(verdict_table(doc))
    st.markdown(f"#### Findings ({len(doc['findings'])})")
    if not doc["findings"]:
        st.caption("No supported change was detected.")
    for f in doc["findings"]:
        with st.expander(f"{f['id']} · {f['kind']} · {f.get('severity')} severity"):
            st.write(f["summary"])
            if f.get("evidence"):
                st.dataframe([{k: e.get(k) for k in ("id", "release", "file", "note")} for e in f["evidence"]],
                             use_container_width=True, hide_index=True)
            if f.get("limitation"):
                st.caption(f"Limitation: {f['limitation']}")
    if doc.get("next_steps"):
        html(ui.cannot_tell(doc["next_steps"]))
    d1, d2 = st.columns(2)
    d1.download_button("Download findings.json", out.read_bytes(), "findings.json", "application/json",
                       use_container_width=True)
    report = out.with_suffix(".html")
    if report.exists():
        d2.download_button("Download the HTML report", report.read_bytes(), "findings.html", "text/html",
                           use_container_width=True)
    receipt = doc.get("receipt", {})
    if receipt.get("result_sha256"):
        st.caption(f"Result SHA-256 {receipt['result_sha256']}: `python -m driftwire verify` reproduces it.")


def show_layout(st, label: str, rep: dict) -> None:
    st.markdown(f"#### {label}: {rep['folder']}")
    if rep.get("error") and not rep["files"]:
        st.error(rep["error"])
        return
    if rep["files"]:
        st.dataframe([{"file": f["file"], "role": f["role"], "rows": f["rows"], "columns": f["columns"],
                       "sample IDs": f["sample_id"] or "not found", "note": f["note"]} for f in rep["files"]],
                     use_container_width=True, hide_index=True)
    else:
        st.warning("No files in this folder.")
    if rep["missing"]:
        st.warning("Missing expected files: " + ", ".join(rep["missing"]))
    rows = [{"check": x["id"], "can run": "yes" if x["can_run"] else "no",
             "why not": "; ".join(x["why_not"]) or x.get("note", "")} for x in rep["analyses"] + rep["questions"]]
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.caption("Anything that can't run is reported as Insufficient Evidence with this reason, never Ready.")
