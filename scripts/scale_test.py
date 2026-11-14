"""Synthetic scale test: a release pair with about 10x the practice release's samples, then one timed diff.

    python scripts/scale_test.py <practice release folder> <work folder> [--factor 10]

SYNTHETIC. Samples are resampled (with replacement) from the practice release and given new, made-up IDs
(TCGA-Z<digit>-<4 base-36 chars>-01, a site code no real TCGA sample uses), so nothing here is real data presented as real. Release B is release A with two protein profiles
swapped, so the detector has one known change to find. clinical.tsv, survival.tsv and protein_rppa.tsv.gz are
scaled; the copy-number and mutation files are left out (at 10x they would be 250 to 320 million cells each).
Prints wall time, peak memory and what was found.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import pathlib
import sys
import time

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def synthetic_id(i: int) -> str:
    """A barcode-shaped made-up ID: site Z0..Z9 (not real TCGA sites), four base-36 characters, primary tumor (-01)."""
    digits = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    q, code = i, ""
    for _ in range(4):
        q, r = divmod(q, 36)
        code = digits[r] + code
    return f"TCGA-Z{q % 10}-{code}-01"


def build(src: pathlib.Path, dest: pathlib.Path, factor: int, seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    clin = pd.read_csv(src / "clinical.tsv", sep="\t", low_memory=False)
    surv = pd.read_csv(src / "survival.tsv", sep="\t")
    prot = pd.read_csv(src / "protein_rppa.tsv.gz", sep="\t", index_col=0)
    n = len(clin) * factor
    pick = rng.integers(0, len(clin), n)
    new_ids = [synthetic_id(i) for i in range(n)]
    src_ids = clin["sampleID"].to_numpy()[pick]
    big_clin = clin.iloc[pick].copy()
    big_clin["sampleID"] = new_ids
    s = surv.set_index("sample")
    keep = [k for k, sid in enumerate(src_ids) if sid in s.index]
    big_surv = s.loc[[src_ids[k] for k in keep]].reset_index(drop=True)
    big_surv.insert(0, "sample", [new_ids[k] for k in keep])
    pk = [k for k, sid in enumerate(src_ids) if sid in prot.columns]
    big_prot = prot[[src_ids[k] for k in pk]].copy()
    big_prot.columns = [new_ids[k] for k in pk]
    big_prot = big_prot + rng.normal(0, 0.05, big_prot.shape)  # resampled duplicates would otherwise be exact copies
    a, b = dest / "A", dest / "B"
    for d in (a, b):
        d.mkdir(parents=True, exist_ok=True)
        big_clin.to_csv(d / "clinical.tsv", sep="\t", index=False)
        big_surv.to_csv(d / "survival.tsv", sep="\t", index=False)
    big_prot.to_csv(a / "protein_rppa.tsv.gz", sep="\t", compression={"method": "gzip", "mtime": 0})
    x, y = big_prot.columns[10], big_prot.columns[20]
    swapped = big_prot.rename(columns={x: y, y: x})[big_prot.columns]
    swapped.to_csv(b / "protein_rppa.tsv.gz", sep="\t", compression={"method": "gzip", "mtime": 0})
    return {"samples": n, "survival_rows": len(big_surv), "protein": list(big_prot.shape), "swapped": [x, y],
            "practice_samples": len(clin)}


def peak_mb() -> float | None:
    try:
        import psutil
        mi = psutil.Process().memory_info()
        return round(getattr(mi, "peak_wset", getattr(mi, "rss", 0)) / 2**20, 1)
    except ImportError:
        import resource  # POSIX
        return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("source")
    p.add_argument("work")
    p.add_argument("--factor", type=int, default=10)
    args = p.parse_args()
    work = pathlib.Path(args.work)
    t0 = time.time()
    info = build(pathlib.Path(args.source), work, args.factor)
    info["build_s"] = round(time.time() - t0, 1)
    from tripwire.__main__ import main as cli
    buf = io.StringIO()
    t1 = time.time()
    with contextlib.redirect_stdout(buf):
        rc = cli(["diff", str(work / "A"), str(work / "B"), "--out", str(work / "findings.json"), "--no-report"])
    info["diff_s"] = round(time.time() - t1, 1)
    info["exit_code"] = rc
    info["peak_memory_mb"] = peak_mb()
    doc = json.loads((work / "findings.json").read_text(encoding="utf-8"))
    info["verdict"] = doc["verdict"]
    info["findings"] = [(f["kind"], f["summary"][:120]) for f in doc["findings"]]
    info["validator"] = [l.strip() for l in buf.getvalue().splitlines() if "validate.py" in l or "validator" in l]
    print(json.dumps(info, indent=1))


if __name__ == "__main__":
    main()
