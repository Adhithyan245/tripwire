"""python -m driftwire inspect <folder>: check a release folder's layout before comparing anything.

For each file: its role (clinical, survival, protein, copy number, mutation, RNA, or unrecognized), its row and column
counts, and the sample-ID column. Then the expected files that are missing, and which reference analyses and question
cards can run on this folder, with the exact missing file or field for each one that can't.

Roles come from the file name Driftwire's analyses expect. A file with any other name is reported as unrecognized,
with what its contents look like, never silently treated as one of the expected files. Nothing is changed.
"""
from __future__ import annotations

import gzip
import pathlib
import re

ROLES = {
    "clinical.tsv": "clinical",
    "survival.tsv": "survival",
    "protein_rppa.tsv.gz": "protein",
    "copy_number_gistic.tsv.gz": "copy number",
    "mutation_gene_level.tsv.gz": "mutation",
    "rna_hiseq.tsv.gz": "RNA",
}
OPTIONAL = {"rna_hiseq.tsv.gz"}          # envelopes leave RNA out by design
ID_COLUMNS = {"clinical.tsv": "sampleID", "survival.tsv": "sample"}
BARCODE = re.compile(r"^TCGA-[A-Z0-9]{2}-[A-Z0-9]{4}-\d{2}", re.I)


def _head(path: pathlib.Path, n: int = 6) -> list[str]:
    opener = gzip.open if path.name.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8", errors="replace", newline="") as f:
        return [f.readline().rstrip("\r\n") for _ in range(n)]


def _count_rows(path: pathlib.Path) -> int:
    opener = gzip.open if path.name.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8", errors="replace", newline="") as f:
        return max(sum(1 for _ in f) - 1, 0)


def describe_file(path: pathlib.Path) -> dict:
    """Role, shape and sample-ID column of one file. Never raises: problems are reported as text."""
    out = {"file": path.name, "role": ROLES.get(path.name, "unrecognized"), "rows": None, "columns": None,
           "sample_id": None, "note": ""}
    try:
        head = [h for h in _head(path) if h != ""]
        if not head:
            out.update(role="unrecognized", note="empty file")
            return out
        delim = "\t" if "\t" in head[0] else ("," if "," in head[0] else None)
        if delim is None:
            out.update(role="unrecognized" if out["role"] == "unrecognized" else out["role"],
                       note="no tab or comma delimiter in the header line")
            return out
        cols = head[0].split(delim)
        out["columns"] = len(cols)
        out["rows"] = _count_rows(path)
        barcode_cols = sum(bool(BARCODE.match(c.strip())) for c in cols[1:])
        if path.name in ID_COLUMNS:
            want = ID_COLUMNS[path.name]
            out["sample_id"] = want if want in cols else None
            if want not in cols:
                out["note"] = f"expected sample-ID column '{want}' not found"
        elif out["role"] != "unrecognized":
            out["sample_id"] = "column headers" if barcode_cols else None
            if not barcode_cols:
                out["note"] = "column headers don't look like TCGA sample barcodes"
        if out["role"] == "unrecognized":
            if delim == ",":
                looks = "comma-separated; Driftwire reads tab-separated .tsv files"
            elif barcode_cols > len(cols) // 2:
                looks = f"looks like a sample-by-feature matrix ({barcode_cols} barcode columns), but the name doesn't say which data type"
            elif any(c in ("sampleID", "sample") for c in cols):
                looks = "has a sample column, but the name doesn't say which data type"
            else:
                looks = "no recognizable sample-ID column or barcode headers"
            out["note"] = f"not one of the expected file names; {looks}"
    except (OSError, EOFError, UnicodeError) as e:
        out.update(role="unrecognized" if out["role"] == "unrecognized" else out["role"],
                   note=f"can't be read: {type(e).__name__}: {e}")
    return out


def inspect_folder(folder) -> dict:
    """Layout report for a release folder. Never raises for a readable folder."""
    from .analyses import ANALYSES, missing_inputs
    from .questions import CARDS, circular_inputs, problems
    from .release import Release

    root = pathlib.Path(folder)
    if not root.is_dir():
        return {"folder": str(root), "error": f"not a folder: {root}", "files": [], "missing": [], "analyses": [], "questions": []}
    files = [describe_file(p) for p in sorted(root.iterdir()) if p.is_file()]
    present = {f["file"] for f in files}
    missing = [n for n in ROLES if n not in present and n not in OPTIONAL]
    rel = None
    try:
        rel = Release(root)
    except Exception as e:  # noqa: BLE001  report, don't crash
        load_error = f"{type(e).__name__}: {e}"
    else:
        load_error = None

    def _why(fn):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001  a file the release can't read is a reason, not a crash
            return [f"can't read the inputs: {type(e).__name__}: {str(e)[:120]}"]

    analyses = []
    for a in ANALYSES:
        need = [f"{n} is not in this folder" for n in a.files if n not in present]
        if not need and rel is not None:
            need = _why(lambda a=a: [f"missing field {x}" for x in missing_inputs(a, rel)])
        analyses.append({"id": a.id, "title": a.title, "can_run": not need, "why_not": need})
    questions = []
    for c in CARDS:
        if circular_inputs(c):
            questions.append({"id": c.id, "title": c.title, "can_run": True,
                              "why_not": [], "note": "runs, and is Blocked as circular by design"})
            continue
        need = [f"{n} is not in this folder" for n in (["clinical.tsv"] + list(c.files)) if n not in present]
        if not need and rel is not None:
            need = _why(lambda c=c: [p["text"] for p in problems(c, rel)])
        questions.append({"id": c.id, "title": c.title, "can_run": not need, "why_not": need})
    return {"folder": str(root), "error": load_error, "files": files, "missing": missing,
            "analyses": analyses, "questions": questions}


def print_report(rep: dict) -> None:
    print(f"Driftwire inspect: {rep['folder']}")
    if rep.get("error") and not rep["files"]:
        print(f"  {rep['error']}")
        return
    if not rep["files"]:
        print("  no files in this folder")
    for f in rep["files"]:
        shape = f"{f['rows']} rows x {f['columns']} columns" if f["rows"] is not None else "shape unknown"
        sid = f"sample IDs: {f['sample_id']}" if f["sample_id"] else "sample IDs: not found"
        print(f"  {f['file']:<30} {f['role']:<13} {shape:<26} {sid}" + (f"   ({f['note']})" if f["note"] else ""))
    if rep["missing"]:
        print(f"  missing expected files: {', '.join(rep['missing'])}")
    print("  Reference analyses:")
    for a in rep["analyses"]:
        print(f"    {a['id']:<4} {'can run' if a['can_run'] else 'cannot run: ' + '; '.join(a['why_not'])}")
    print("  Question cards:")
    for q in rep["questions"]:
        state = "can run" if q["can_run"] else "cannot run: " + "; ".join(q["why_not"])
        print(f"    {q['id']:<34} {state}" + (f" ({q['note']})" if q.get("note") else ""))
    print("  Anything that can't run is reported as Insufficient Evidence with this reason; never Ready.")
