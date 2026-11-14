"""Extended Mutation Lab scenarios: changes the core lab and the organizers' make_release.py don't plant.

Each scenario copies release A into a new folder, plants one kind of change, and returns the expected changes in the
shared contract, so tripwire.mutation_lab.core.evaluate scores them like the core scenarios. Unplanted cells keep
their original text. Synthetic test data only; never commit generated releases.
"""
from __future__ import annotations

import random
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from tripwire.contract import Change

PROTEIN, CLINICAL, COPY_NUMBER = "protein_rppa.tsv.gz", "clinical.tsv", "copy_number_gistic.tsv.gz"

DESCRIPTIONS = {
    "id_case": "one protein sample ID re-written in lower case",
    "type_code": "one protein sample's type code changed 01 -> 06",
    "near_copy": "one sample replaced by a near-identical copy (0.1% noise) of another, under a new ID",
    "unit_scale": "one sample's protein profile multiplied by 2 (unit change)",
    "new_sample": "a new sample with a fresh profile",
    "vanished_file": "the copy-number file missing from the new release",
    "relabel_pam50": "three samples' PAM50 subtype changed in clinical.tsv",
    "repeated_id": "one protein sample's column and one clinical row each listed twice (counted twice)",
    "resaved_clinical": "no-change control: clinical.tsv re-saved by another tool (55 -> 55.0)",
    "mixed_changes": "simultaneous swap, duplicate, lost profile and clinical label change",
}
EXTENDED = tuple(DESCRIPTIONS)


def _copy(source: Path, target: Path) -> None:
    source, target = Path(source).resolve(), Path(target).resolve()
    if target.exists():
        raise FileExistsError(f"target already exists: {target}")
    if source == target or source in target.parents or target in source.parents:
        raise ValueError("source and target must be separate, non-nested directories")
    target.mkdir(parents=True)
    for f in source.iterdir():
        if f.is_file() and f.name.endswith((".tsv", ".tsv.gz")):
            shutil.copy(f, target / f.name)


def _text(path: Path, **kw) -> pd.DataFrame:
    return pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False, na_filter=False, **kw)


def _write_matrix(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, sep="\t", lineterminator="\n", compression={"method": "gzip", "mtime": 0})


def _gz_lines(path: Path) -> list[str]:
    import gzip
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        return f.read().splitlines()


def _primary(cols) -> list[str]:
    return [c for c in cols if str(c)[13:15] == "01"]


def _mixed_changes(source: Path, target: Path, seed: int) -> list[Change]:
    """Compose changes on distinct samples, retaining independent planted truth."""
    from tripwire.mutation_lab.core import generate

    source, target = source.resolve(), target.resolve()
    if target.exists():
        raise FileExistsError(f"target already exists: {target}")
    if source == target or source in target.parents or target in source.parents:
        raise ValueError("source and target must be separate, non-nested directories")
    truth, used = [], set()
    with tempfile.TemporaryDirectory(prefix="mixed-mutation-", dir=target.parent) as work:
        work = Path(work)
        current = source
        for stage, kind in enumerate(("swap", "duplicate", "disappeared", "label_change")):
            for attempt in range(40):
                candidate = work / f"stage-{stage}-{attempt}"
                changes = generate(current, candidate, kind, seed + stage * 1000 + attempt)
                involved = {str(s).strip().upper() for c in changes
                            for s in (c.sample_id, c.related_sample_id) if s}
                if not involved.intersection(used):
                    used.update(involved)
                    truth.extend(changes)
                    current = candidate
                    break
                shutil.rmtree(candidate)
            else:
                raise ValueError("not enough distinct samples for mixed mutations")
        if target.exists():
            raise FileExistsError(f"target already exists: {target}")
        current.rename(target)
    return truth


def generate_extended(source: Path, target: Path, scenario: str, seed: int = 0) -> list[Change]:
    if scenario not in DESCRIPTIONS:
        raise ValueError(f"unknown extended scenario {scenario!r}")
    if scenario == "mixed_changes":
        return _mixed_changes(Path(source), Path(target), seed)
    rng = random.Random(seed)
    nrng = np.random.default_rng(seed)
    _copy(source, target)
    target = Path(target)
    prot_path, clin_path = target / PROTEIN, target / CLINICAL
    prot = _text(prot_path, index_col=0)
    clin = _text(clin_path)
    prim = sorted(_primary(prot.columns))
    unused = sorted(s for s in clin["sampleID"] if s[13:15] == "01" and s not in prot.columns)

    if scenario == "id_case":
        s = rng.choice(prim)
        _write_matrix(prot.rename(columns={s: s.lower()}), prot_path)
        return [Change(s, "id_format_change", PROTEIN, [], "lower-cased ID", s, s.lower())]
    if scenario == "type_code":
        s = rng.choice(prim)
        new = s[:13] + "06"
        _write_matrix(prot.rename(columns={s: new}), prot_path)
        return [Change(s, "sample_type_change", PROTEIN, [], "type code 01 -> 06", s, new, related_sample_id=new)]
    if scenario == "near_copy":
        src, drop = rng.sample(prim, 2)
        new = rng.choice(unused)
        p = prot.drop(columns=[drop])
        v = pd.to_numeric(p[src], errors="coerce")
        p[new] = (v + nrng.normal(0, 0.001, len(v)) * v.abs()).map(lambda x: f"{x:.6f}")
        _write_matrix(p, prot_path)
        return [Change(new, "duplicate", PROTEIN, [], f"near-identical copy of {src}", None, f"copy of {src}",
                       related_sample_id=src),
                Change(drop, "disappeared", PROTEIN, [], "dropped to keep the count", "present", None)]
    if scenario == "unit_scale":
        s = rng.choice(prim)
        p = prot.copy()
        p[s] = (pd.to_numeric(p[s], errors="coerce") * 2).map(lambda x: f"{x:.6f}")
        _write_matrix(p, prot_path)
        return [Change(s, "value_shift", PROTEIN, list(map(str, p.index)), "profile x2")]
    if scenario == "new_sample":
        new = rng.choice(unused)
        p = prot.copy()
        p[new] = [f"{x:.6f}" for x in nrng.normal(0, 1, len(p))]
        _write_matrix(p, prot_path)
        return [Change(new, "appeared", PROTEIN, [], "fresh profile", None, "present")]
    if scenario == "vanished_file":
        cn = target / COPY_NUMBER
        if not cn.exists():
            raise FileNotFoundError("vanished_file needs copy_number_gistic.tsv.gz in the source release")
        ids = list(pd.read_csv(cn, sep="\t", index_col=0, nrows=0).columns)
        cn.unlink()
        return [Change(s, "disappeared", COPY_NUMBER, [], "file removed", "present", None) for s in ids]
    if scenario == "relabel_pam50":
        col = "PAM50Call_RNAseq"
        rows = sorted(clin.index[(clin["sampleID"].str[13:15] == "01") & (clin[col] != "")].tolist())
        pick = rng.sample(rows, 3)
        out = []
        for r in pick:
            new = "Basal" if clin.at[r, col] != "Basal" else "LumA"
            out.append(Change(clin.at[r, "sampleID"], "label_change", CLINICAL, [col], "relabelled",
                              clin.at[r, col], new))
            clin.at[r, col] = new
        clin.to_csv(clin_path, sep="\t", index=False, lineterminator="\n")
        return out
    if scenario == "repeated_id":
        s = rng.choice(prim)
        rows = _gz_lines(prot_path)
        col = rows[0].split("\t").index(s)
        rows = [ln + "\t" + ln.split("\t")[col] for ln in rows]  # the ID again in the header, its values in rows
        import gzip
        with gzip.open(prot_path, "wt", encoding="utf-8", newline="") as f:
            f.write("\n".join(rows) + "\n")
        r = rng.choice(sorted(clin.index[clin["sampleID"].str[13:15] == "01"].tolist()))
        pd.concat([clin, clin.loc[[r]]], ignore_index=True).to_csv(clin_path, sep="\t", index=False,
                                                                  lineterminator="\n")
        sid = clin.at[r, "sampleID"]
        return [Change(s, "duplicate", PROTEIN, [], "column listed twice", 1, 2),
                Change(sid, "duplicate", CLINICAL, [], "row listed twice", 1, 2)]
    # resaved_clinical: same values, different formatting; nothing should be reported
    pd.read_csv(target / CLINICAL, sep="\t", low_memory=False).to_csv(clin_path, sep="\t", index=False,
                                                                       lineterminator="\n")
    return []
