"""The analyses Tripwire protects. Each one declares what it reads, so the impact map can decide from logic, not
hardcoding, whether a change touches it.

A1 and A2 reproduce data/tcga-brca/reference_analyses.py exactly (tests/test_analyses.py checks this against the
challenge repo when it is present)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .config import CONFIG
from .contract import norm_id
from .release import Release

ER_COL = "breast_carcinoma_estrogen_receptor_status"
PAM50_COL = "PAM50Call_RNAseq"


def is_primary(sample_id) -> bool:
    return str(sample_id)[13:15] == "01"


@dataclass
class Movement:
    moved: bool            # any output or membership differs
    beyond_tolerance: bool
    flipped: bool          # the conclusion changed direction
    insufficient: bool     # too few samples after the change
    magnitude: str         # human-readable "how far it moved"


@dataclass
class SliceDiff:
    """Sample-by-sample comparison of exactly what an analysis reads, in release A and B."""
    added: list[str]                          # in B's slice only
    removed: list[str]                        # in A's slice only
    changed: list[tuple[str, str, str]]       # (sample, before, after)
    identical: int

    @property
    def any(self) -> bool:
        return bool(self.added or self.removed or self.changed)

    def counts(self) -> dict:
        return {"added": len(self.added), "removed": len(self.removed), "values_changed": len(self.changed),
                "identical": self.identical}


def slice_diff(a: dict[str, tuple], b: dict[str, tuple]) -> SliceDiff:
    """a, b: sample -> (comparison key, display text)."""
    ka, kb = {norm_id(s): s for s in a}, {norm_id(s): s for s in b}
    common = ka.keys() & kb.keys()
    changed = sorted((kb[k], a[ka[k]][1], b[kb[k]][1]) for k in common if a[ka[k]][0] != b[kb[k]][0])
    return SliceDiff(sorted(kb[k] for k in kb.keys() - ka.keys()), sorted(ka[k] for k in ka.keys() - kb.keys()),
                     changed, len(common) - len(changed))


@dataclass
class Analysis:
    id: str
    title: str
    files: list[str]
    fields: dict[str, set[str]]  # file -> rows/columns it reads
    cohort: str                  # plain-English sample filter
    eligible: Callable[[Release], set[str]]  # normalised IDs that could enter it
    run: Callable[[Release], dict]
    compare: Callable[[dict, dict], Movement]
    slice: Callable[[Release], dict[str, tuple]]  # sample -> (key, display): exactly what it reads per sample


# ---------- A1: ER-alpha protein by clinical ER status ----------

def a1_run(r: Release) -> dict:
    er = r.clinical.set_index("sampleID")[ER_COL]
    samples = [s for s in r.protein.columns if is_primary(s) and er.get(s) in ("Positive", "Negative")]
    vals = r.protein.loc["ERALPHA", samples]
    pos = vals[[s for s in samples if er[s] == "Positive"]]
    neg = vals[[s for s in samples if er[s] == "Negative"]]
    mp, mn = float(pos.mean()), float(neg.mean())
    return {"n_samples": len(samples), "n_positive": int(pos.size), "n_negative": int(neg.size),
            "mean_positive": round(mp, 3), "mean_negative": round(mn, 3), "difference": round(mp - mn, 3),
            "sample_ids": sorted(samples)}


def a1_slice(r: Release) -> dict[str, tuple]:
    er = r.clinical.set_index("sampleID")[ER_COL]
    row = r.protein.loc["ERALPHA"]
    out = {}
    for s in r.protein.columns:
        if is_primary(s) and er.get(s) in ("Positive", "Negative"):
            v = float(row[s])
            out[s] = ((er[s], repr(v)), f"ER {er[s]}, ERALPHA {v:.3f}")
    return out


def a1_eligible(r: Release) -> set[str]:
    in_clinical = {norm_id(s) for s in r.clinical["sampleID"]}
    return {norm_id(s) for s in r.protein.columns if is_primary(s) and norm_id(s) in in_clinical}


def a1_compare(b: dict, a: dict) -> Movement:
    db, da = b["difference"], a["difference"]
    rel = abs(da - db) / abs(db) if db else float("inf")
    tol = CONFIG["A1_difference_rel_tolerance"]
    flipped = (db > 0) != (da > 0)
    moved = _strip(b) != _strip(a) or set(b["sample_ids"]) != set(a["sample_ids"])
    insufficient = min(a["n_positive"], a["n_negative"]) < CONFIG["min_samples_per_group"]
    return Movement(moved, rel > tol, flipped, insufficient,
                    f"difference {db} -> {da} ({rel:.1%} relative; tolerance {tol:.0%})")


# ---------- A2: RNA subtype mix of primary tumors ----------

def a2_run(r: Release) -> dict:
    c = r.clinical[r.clinical.sampleID.str[13:15] == "01"].dropna(subset=[PAM50_COL])
    counts = c[PAM50_COL].value_counts().sort_index()
    total = int(counts.sum())
    return {"n_samples": total, "counts": {k: int(v) for k, v in counts.items()},
            "percent": {k: round(100 * v / total, 1) for k, v in counts.items()} if total else {},
            "sample_ids": sorted(c.sampleID)}


def a2_slice(r: Release) -> dict[str, tuple]:
    c = r.clinical[r.clinical.sampleID.str[13:15] == "01"].dropna(subset=[PAM50_COL])
    return {s: (v, f"PAM50 {v}") for s, v in zip(c.sampleID, c[PAM50_COL])}


def a2_eligible(r: Release) -> set[str]:
    return {norm_id(s) for s in r.clinical["sampleID"] if is_primary(s)}


def a2_compare(b: dict, a: dict) -> Movement:
    keys = set(b["percent"]) | set(a["percent"])
    shift = max((abs(a["percent"].get(k, 0) - b["percent"].get(k, 0)) for k in keys), default=0.0)
    tol = CONFIG["A2_percent_pp_tolerance"]
    top = lambda d: max(d, key=d.get) if d else None
    flipped = top(b["counts"]) != top(a["counts"])
    moved = _strip(b) != _strip(a) or set(b["sample_ids"]) != set(a["sample_ids"])
    insufficient = a["n_samples"] < CONFIG["min_samples_per_group"]
    return Movement(moved, shift > tol, flipped, insufficient,
                    f"largest subtype share shift {shift:.1f} pp (tolerance {tol} pp)")


def _strip(result: dict) -> dict:
    return {k: v for k, v in result.items() if k != "sample_ids"}


ANALYSES: list[Analysis] = [
    Analysis("A1", "ER-alpha protein by clinical ER status",
             ["clinical.tsv", "protein_rppa.tsv.gz"],
             {"clinical.tsv": {"sampleID", ER_COL}, "protein_rppa.tsv.gz": {"ERALPHA"}},
             "primary tumors (code 01) with protein data and clinical ER status Positive or Negative",
             a1_eligible, a1_run, a1_compare, a1_slice),
    Analysis("A2", "RNA subtype mix of primary tumors",
             ["clinical.tsv"],
             {"clinical.tsv": {"sampleID", PAM50_COL}},
             "primary tumors (code 01) in clinical.tsv with a PAM50 RNA-seq call",
             a2_eligible, a2_run, a2_compare, a2_slice),
]


def public(result: dict) -> dict:
    """What goes into findings.json: everything but the full sample list."""
    return _strip(result)
