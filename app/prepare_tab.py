"""Prepare data with AI: upload a CSV/TSV, map its columns to the fields Driftwire reads, approve, get a prepared copy.

A separate entry point; the release comparison and demo flow are unchanged. Nothing here runs the firewall or shows a
verdict: it only produces a prepared copy and a mapping record.

AI is opt-in. Only column names, file metadata (name, size, row and column counts) and the research question are
sent, never dataset rows. The suggestion backend is plugged in at one hook (`_backend()` below) and is being built
separately; until it's there, "Suggest mappings" says AI is unavailable and the manual path works the same way.
No API key is read or stored by this screen.
"""
from __future__ import annotations

import csv
import datetime
import hashlib
import io
import json
import pathlib
import tempfile

SUPPORTED = {".csv": ",", ".tsv": "\t", ".txt": "\t"}
UNSUPPORTED_NOTE = "Excel (.xlsx/.xls), Parquet, JSON, compressed (.gz/.zip) and other formats aren't supported here yet."
MAX_UPLOAD_MB = 200  # Streamlit's default upload limit

# The fields Driftwire's analyses and question cards read, by target file.
FIELDS = {
    "clinical.tsv": {
        "sampleID": "Sample ID (TCGA barcode, e.g. TCGA-A1-A0SB-01)",
        "breast_carcinoma_estrogen_receptor_status": "ER status (Positive / Negative)",
        "HER2_Final_Status_nature2012": "HER2 status (Positive / Negative)",
        "PAM50Call_RNAseq": "PAM50 subtype (LumA, LumB, Her2, Basal, Normal)",
    },
    "survival.tsv": {
        "sample": "Sample ID (TCGA barcode)",
        "OS": "Overall-survival event (1 = died, 0 = censored)",
        "OS.time": "Overall-survival time (days)",
    },
}
NOT_USED = "(not used)"
AI_STATUS = "AI proposed — review required"
UNCERTAIN = "Uncertain — answer the question below"
MANUAL = "Set by you"


# ---------------------------------------------------------------- pure helpers (tested without Streamlit)

def file_support(name: str) -> tuple[bool, str]:
    ext = pathlib.Path(name).suffix.lower()
    if ext in SUPPORTED:
        return True, f"{ext} is supported"
    return False, f"{ext or 'this file type'} is not supported. Use .csv or .tsv. {UNSUPPORTED_NOTE}"


def read_header(data: bytes, name: str) -> tuple[list[str], int]:
    """Column names and data-row count. Raises ValueError with a plain-language message."""
    ok, why = file_support(name)
    if not ok:
        raise ValueError(why)
    text = data.decode("utf-8-sig", errors="strict") if data else ""
    if not text.strip():
        raise ValueError("The file is empty.")
    delim = SUPPORTED[pathlib.Path(name).suffix.lower()]
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    header = rows[0]
    if len(header) < 2:
        raise ValueError(f"Only one column found; check the file really is {'comma' if delim == ',' else 'tab'}-separated.")
    dup = sorted({c for c in header if header.count(c) > 1})
    if dup:
        raise ValueError(f"Duplicate column names: {', '.join(dup)}. Rename them before preparing.")
    return header, len([r for r in rows[1:] if any(cell.strip() for cell in r)])


def metadata(name: str, data: bytes, header: list[str], n_rows: int, question: str) -> dict:
    """Exactly what an opted-in AI request may contain: no dataset rows."""
    return {"file_name": name, "size_bytes": len(data), "n_rows": n_rows, "n_columns": len(header),
            "columns": header, "research_question": question}


def _backend():
    """The AI suggestion function, once the separately built backend is installed. Contract:
    suggest(meta: dict, fields: dict) -> {"target": "clinical.tsv"|"survival.tsv",
        "mappings": [{"column", "field", "confidence": 0..1, "reason"}], "questions": ["..."]}"""
    try:
        from tripwire.prepare import suggest_mappings  # provided by the backend; not part of this screen
        return suggest_mappings
    except Exception:  # noqa: BLE001  missing or broken backend means "AI unavailable", never a crash
        return None


def blockers(target: str, mapping: dict[str, str], questions: list[str], answers: dict[str, str]) -> list[str]:
    """What stops approval: duplicate targets, missing ID column, unanswered clarification questions."""
    used = [f for f in mapping.values() if f != NOT_USED]
    out = [f"Two columns are mapped to {f}; keep one." for f in sorted({f for f in used if used.count(f) > 1})]
    id_field = "sampleID" if target == "clinical.tsv" else "sample"
    if id_field not in used:
        out.append(f"No column is mapped to the sample ID ({id_field}); Driftwire can't line samples up without it.")
    out += [f"Unanswered question: {q}" for q in questions if not (answers.get(q) or "").strip()]
    return out


def limitations(target: str, mapping: dict[str, str]) -> list[str]:
    used = set(mapping.values())
    return [f"{field} ({desc}) isn't mapped: questions that need it will say Insufficient Evidence."
            for field, desc in FIELDS[target].items() if field not in used]


def prepare_copy(data: bytes, name: str, target: str, mapping: dict[str, str], out_dir: pathlib.Path,
                 source: str, answers: dict[str, str]) -> tuple[pathlib.Path, pathlib.Path]:
    """Write a prepared copy (headers renamed, values untouched, tab-separated) and a mapping record.
    The original upload is never modified; no row is deleted, filled in or relabelled."""
    delim = SUPPORTED[pathlib.Path(name).suffix.lower()]
    rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig")), delimiter=delim))
    header = rows[0]
    renamed = [mapping.get(c, NOT_USED) if mapping.get(c, NOT_USED) != NOT_USED else c for c in header]
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / target
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(renamed)
        w.writerows(rows[1:])
    record = {
        "prepared_file": out.name, "original_file": name,
        "original_sha256": hashlib.sha256(data).hexdigest(),
        "prepared_sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
        "header_changes": [{"from": c, "to": mapping[c]} for c in header if mapping.get(c, NOT_USED) not in (NOT_USED, c)],
        "unchanged_columns": [c for c in header if mapping.get(c, NOT_USED) in (NOT_USED, c)],
        "rows": len(rows) - 1, "rows_changed": 0,
        "mapping_source": source, "clarifications": answers,
        "approved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "note": "Headers renamed only. No rows deleted, filled in or clinically relabelled. The firewall hasn't run.",
    }
    rec = out_dir / "mapping_record.json"
    rec.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return out, rec


# ---------------------------------------------------------------- the screens

def render(st, html, ui) -> None:
    ss = st.session_state
    step = ss.setdefault("prep_step", 1)
    html(f'<div class="tw-cm"><b>Prepare data with AI</b> · step {step} of 4: '
         + " → ".join(f"<b>{t}</b>" if i + 1 == step else t
                      for i, t in enumerate(["Upload and question", "Review suggestions", "Approve", "Next step"]))
         + "</div>")

    if step == 1:
        st.subheader("1 · Upload and question")
        st.caption(f"Supported: **.csv**, **.tsv** (up to {MAX_UPLOAD_MB} MB). {UNSUPPORTED_NOTE}")
        up = st.file_uploader("Dataset", type=None, key="prep_file")
        target = st.radio("This file holds", list(FIELDS), format_func=lambda t: {"clinical.tsv": "clinical data (per sample)",
                          "survival.tsv": "survival data (per sample)"}[t], horizontal=True, key="prep_target")
        question = st.text_area("Your research question", key="prep_question",
                                placeholder="e.g. Does ER-alpha protein differ between ER-positive and ER-negative tumors?")
        opt_in = st.checkbox("Send column names, file metadata, and my research question to OpenAI to suggest mappings.",
                             key="prep_optin")
        st.caption("Dataset rows are never sent: only the column names, the file name, its size and row/column counts, "
                   "and your question. Leave this off to map the columns yourself.")
        if up is None:
            return
        data = up.getvalue()
        ok, why = file_support(up.name)
        if not ok:
            st.error(f"Unsupported file: {why}")
            return
        try:
            header, n_rows = read_header(data, up.name)
        except (ValueError, UnicodeDecodeError) as e:
            st.error(f"Can't read {up.name}: {e if isinstance(e, ValueError) else 'it is not valid UTF-8 text.'}")
            return
        st.success(f"{up.name}: {n_rows} rows, {len(header)} columns.")
        c1, c2 = st.columns(2)
        backend = _backend()
        if c1.button("Suggest mappings", type="primary", disabled=not opt_in,
                     help=None if opt_in else "Tick the opt-in box above to use AI suggestions."):
            if backend is None:
                st.warning("AI suggestions are unavailable right now. Use **Map columns myself**; it works the same way.")
            else:
                try:
                    res = backend(metadata(up.name, data, header, n_rows, question), FIELDS)
                    ss.update(prep_data=data, prep_name=up.name, prep_header=header, prep_rows=n_rows,
                              prep_target=res.get("target", target), prep_source="ai",
                              prep_map={m["column"]: m["field"] for m in res.get("mappings", []) if m.get("column") in header},
                              prep_conf={m["column"]: float(m.get("confidence", 0)) for m in res.get("mappings", [])},
                              prep_reason={m["column"]: m.get("reason", "") for m in res.get("mappings", [])},
                              prep_questions=list(res.get("questions", [])), prep_step=2)
                    st.rerun()
                except Exception as e:  # noqa: BLE001  an AI failure falls back to the manual path
                    st.error(f"The AI suggestion failed ({type(e).__name__}). Use **Map columns myself** instead.")
        if c2.button("Map columns myself"):
            ss.update(prep_data=data, prep_name=up.name, prep_header=header, prep_rows=n_rows, prep_target=target,
                      prep_source="manual", prep_map={c: (c if c in FIELDS[target] else NOT_USED) for c in header},
                      prep_conf={}, prep_reason={}, prep_questions=[], prep_step=2)
            st.rerun()
        return

    target, header = ss["prep_target"], ss["prep_header"]
    if step == 2:
        st.subheader("2 · Review suggestions")
        options = [NOT_USED] + list(FIELDS[target])
        mapping, rows = {}, []
        for col in header:
            proposed = ss["prep_map"].get(col, NOT_USED)
            conf = ss["prep_conf"].get(col)
            if ss["prep_source"] == "ai" and proposed != NOT_USED:
                status = UNCERTAIN if conf is not None and conf < 0.8 else AI_STATUS
            else:
                status = MANUAL
            c1, c2, c3 = st.columns([2, 3, 3])
            c1.markdown(f"`{col}`")
            choice = c2.selectbox(f"Driftwire field for {col}", options, index=options.index(proposed) if proposed in options else 0,
                                  key=f"prep_sel_{col}", label_visibility="collapsed",
                                  format_func=lambda f: f if f == NOT_USED else f"{f} · {FIELDS[target][f]}")
            if choice != proposed:
                status = MANUAL
            c3.markdown(("⚠️ " if status == UNCERTAIN else "") + status
                        + (f"<br><span style='font-size:12px;opacity:.7'>{ss['prep_reason'].get(col, '')}</span>"
                           if ss["prep_reason"].get(col) else ""), unsafe_allow_html=True)
            mapping[col] = choice
            rows.append(status)
        questions = list(ss["prep_questions"]) + [f"Please confirm the mapping for `{c}`." for c, s in zip(header, rows)
                                                  if s == UNCERTAIN]
        answers = ss.setdefault("prep_answers", {})
        if questions:
            st.markdown("#### Questions that need your answer")
            for q in questions:
                answers[q] = st.text_input(q, value=answers.get(q, ""), key=f"prep_q_{hash(q)}")
        blk, lim = blockers(target, mapping, questions, answers), limitations(target, mapping)
        for b in blk:
            st.error(f"Blocker: {b}")
        for l in lim:
            st.warning(f"Limitation: {l}")
        c1, c2 = st.columns(2)
        if c1.button("Back"):
            ss["prep_step"] = 1
            st.rerun()
        if c2.button("Continue to approval", type="primary", disabled=bool(blk)):
            ss.update(prep_final=mapping, prep_final_answers={q: answers.get(q, "") for q in questions}, prep_step=3)
            st.rerun()
        return

    mapping = ss["prep_final"]
    if step == 3:
        st.subheader("3 · Approve preparation")
        changes = [(c, f) for c, f in mapping.items() if f not in (NOT_USED, c)]
        st.markdown("**Header changes:**" if changes else "**No header changes** (columns already use Driftwire's names).")
        for c, f in changes:
            st.markdown(f"- `{c}` → `{f}`")
        st.info(f"The original upload is not changed. No rows are deleted, filled in, or clinically relabeled. "
                f"The prepared copy keeps all {ss['prep_rows']} rows and every value as uploaded.")
        approved = st.checkbox("I have reviewed and approve these mappings.", key="prep_ok")
        c1, c2 = st.columns(2)
        if c1.button("Back to review"):
            ss["prep_step"] = 2
            st.rerun()
        if c2.button("Create prepared copy", type="primary", disabled=not approved):
            out_dir = pathlib.Path(tempfile.mkdtemp(prefix="driftwire-prepared-"))
            out, rec = prepare_copy(ss["prep_data"], ss["prep_name"], target, mapping, out_dir,
                                    ss["prep_source"], ss["prep_final_answers"])
            ss.update(prep_out=str(out), prep_rec=str(rec), prep_step=4)
            st.rerun()
        return

    st.subheader("4 · Next step")
    st.success("Preparation complete; firewall assessment has not run yet.")
    out, rec = pathlib.Path(ss["prep_out"]), pathlib.Path(ss["prep_rec"])
    st.markdown(f"Prepared file: `{out}`")
    st.download_button("Download prepared file", out.read_bytes(), file_name=out.name)
    st.markdown("Mapping record:")
    st.json(json.loads(rec.read_text(encoding="utf-8")))
    st.download_button("Download mapping record", rec.read_bytes(), file_name=rec.name)
    st.info("To get a verdict, run the release comparison: it needs a supported release A and release B, each a folder "
            "with Driftwire's files (put this prepared file in the new release's folder, next to the others).")
    c1, c2 = st.columns(2)
    if c1.button("Go to the release comparison", type="primary"):
        ss["view"] = "Release check"
        st.rerun()
    if c2.button("Prepare another file"):
        for k in [k for k in ss.keys() if str(k).startswith("prep_")]:
            del ss[k]
        st.rerun()
