"""Repair preview: what each proposed repair would do to the analyses, if a reviewer approved it.

Computed on an in-memory copy of release B. Nothing on disk changes and nothing is applied: it only helps a reviewer
size the decision ("A1 moves back to within 0.1% of release A").
"""
from __future__ import annotations

from .analyses import ANALYSES, public
from .contract import norm_id
from .release import Release
from .verdicts import release_verdict

PREVIEWABLE = {"exclude", "restore_from_previous_release"}
FILES = {"protein_rppa.tsv.gz", "clinical.tsv"}  # what the reference analyses read


def _overlay(a: Release, b: Release, action: str, targets: list[dict]) -> Release:
    ov = Release(b.path, name=f"{b.name} (preview)")
    prot, clin = b.protein.copy(), b.clinical.copy()
    restored = {}  # A's profiles to put back, added in one step (column-by-column inserts fragment the frame)
    a_prot = {norm_id(s): s for s in a.protein.columns}
    a_clin = a.clinical.set_index(a.clinical["sampleID"].map(norm_id))
    for t in targets:
        if t.get("kind") != "sample":
            continue
        sid, f = t["id"], t.get("file")
        b_cols = [c for c in prot.columns if norm_id(c) == norm_id(sid)]
        if f == "protein_rppa.tsv.gz":
            if action == "exclude":
                prot = prot.drop(columns=b_cols)
            elif norm_id(sid) in a_prot:  # restore A's profile under A's ID
                prot = prot.drop(columns=b_cols)
                restored[a_prot[norm_id(sid)]] = a.protein[a_prot[norm_id(sid)]]
            else:
                prot = prot.drop(columns=b_cols)
        elif f == "clinical.tsv":
            mask = clin["sampleID"].map(norm_id) == norm_id(sid)
            if action == "exclude" or norm_id(sid) not in a_clin.index:
                clin = clin[~mask]
            else:
                row = a_clin.loc[[norm_id(sid)]].reset_index(drop=True)
                clin = clin[~mask]
                clin = clin._append(row, ignore_index=True) if hasattr(clin, "_append") else \
                    __import__("pandas").concat([clin, row], ignore_index=True)
    if restored:
        import pandas as pd
        prot = pd.concat([prot.drop(columns=[c for c in restored if c in prot.columns]),
                          pd.DataFrame(restored).reindex(prot.index)], axis=1)
    ov.__dict__["protein"], ov.__dict__["clinical"] = prot, clin
    return ov


def preview(repair: dict, a: Release, b: Release) -> dict:
    files = {t.get("file") for t in repair.get("targets", []) if t.get("kind") == "sample"}
    if repair["action"] not in PREVIEWABLE:
        return {"note": "Nothing to compute: this repair asks a person to check something first."}
    if not files & FILES:
        return {"note": "No reference analysis reads the files this repair touches, so no result would move."}
    ov = _overlay(a, b, repair["action"], repair.get("targets", []))
    out = []
    for an in ANALYSES:
        if not set(an.files) & files:
            continue
        before, now, fixed = an.run(a), an.run(b), an.run(ov)
        mv_now, mv_fixed = an.compare(before, now), an.compare(before, fixed)
        v_now = release_verdict(True, mv_now).verdict if mv_now.moved else "Ready"
        v_fixed = release_verdict(True, mv_fixed).verdict if mv_fixed.moved else "Ready"
        out.append({"analysis": an.id, "now": public(now), "if_approved": public(fixed),
                    "verdict_now": v_now, "verdict_if_approved": v_fixed,
                    "summary": f"{an.id}: now {mv_now.magnitude}; if approved {mv_fixed.magnitude}, vs release {a.name}."})
    return {"analyses": out, "note": "This repair on its own, on a copy of the new release; other changes stay. "
                                     "Nothing is applied."} if out else \
        {"note": "No reference analysis is affected by this repair."}


def preview_all(repairs: list[dict], a: Release, b: Release) -> dict:
    """Every previewable repair approved together, on one copy of release B."""
    usable = [r for r in repairs if r["action"] in PREVIEWABLE and
              {t.get("file") for t in r.get("targets", [])} & FILES]
    if not usable:
        return {"note": "No proposed repair changes data a reference analysis reads."}
    ov = b
    for r in usable:
        ov = _overlay(a, ov, r["action"], r.get("targets", []))
    open_ids = [r["id"] for r in repairs if r not in usable]
    out = []
    for an in ANALYSES:
        before, fixed = an.run(a), an.run(ov)
        mv = an.compare(before, fixed)
        verdict = release_verdict(True, mv).verdict if mv.moved else "Ready"
        row = {"analysis": an.id, "if_approved": public(fixed), "verdict_if_approved": verdict,
               "summary": f"{an.id}: {mv.magnitude} vs release {a.name}."}
        if verdict != "Ready":
            row["why_not_ready"] = _why_not_ready(before, fixed, open_ids)
            row["summary"] += f" Stays {verdict}: {row['why_not_ready']}"
        out.append(row)
    return {"repairs": [r["id"] for r in usable], "analyses": out,
            "note": "All of these repairs approved together, on a copy of the new release; nothing is applied. "
                    "Repairs that only ask for a check (flag_for_review) can't be previewed."}


def _why_not_ready(before, fixed, open_ids: list[str]) -> str:
    """Why an analysis whose number is back to release A's still isn't Ready: its inputs still differ from A's."""
    n_a, n_f = public(before).get("n_samples"), public(fixed).get("n_samples")
    bits = []
    if isinstance(n_a, int) and isinstance(n_f, int) and n_a != n_f:
        bits.append(f"it would read {n_f} samples, release A has {n_a}")
    if open_ids:
        bits.append(f"{', '.join(open_ids)} only asks for a check, so it can't be previewed and is still open")
    why = "; ".join(bits) or "its inputs still differ from release A's"
    return f"the result matches, but {why}. Ready needs the same inputs, so a person signs off on the rest."
