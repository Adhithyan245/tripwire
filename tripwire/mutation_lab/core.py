"""Generate controlled copies and score contract changes; never modify the source release."""
from __future__ import annotations

import csv
import gzip
import math
import random
import shutil
from collections import Counter
from pathlib import Path

import pandas as pd

from tripwire.contract import Change

PROTEIN = "protein_rppa.tsv.gz"
CLINICAL = "clinical.tsv"
ER_COL = "breast_carcinoma_estrogen_receptor_status"
SHIFT_FEATURE = "ERALPHA"
SHIFT = 10.0
SCENARIOS = ("unchanged", "reordered", "swap", "duplicate", "disappeared", "label_change", "value_shift")


def _header(path: Path) -> list[str]:
    opener = gzip.open if path.name.endswith(".gz") else open
    with opener(path, "rt", newline="", encoding="utf-8") as f:
        return next(csv.reader(f, delimiter="\t"), [])


def _read_text(path: Path, **kwargs) -> pd.DataFrame:
    # Keep every cell as its original text: a rewritten file then differs from the
    # source only in planted cells (no 45 -> 45.0, "NA" -> "", or float reformatting).
    header = _header(path)
    if len(set(header)) != len(header):
        # pandas silently renames repeated headers (X -> X.1), which would plant an
        # unrecorded ID change in the output.
        raise ValueError(f"{path.name} has repeated column names")
    return pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False, na_filter=False, **kwargs)


def generate(source: Path, target: Path, scenario: str, seed: int = 0) -> list[Change]:
    """Make a new release copy and return planted changes in the shared contract.

    A swap has two sample-level expected changes; a duplicate is the overwritten
    target only. Exact profile equality does not establish biological identity.
    Unplanted cells are written back as their original text.
    """
    if Path(target).is_symlink():  # checked before resolve(), which follows dangling links
        raise FileExistsError(f"target already exists as a symlink: {target}")
    source, target = Path(source).resolve(), Path(target).resolve()
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario {scenario!r}")
    if not source.is_dir():
        raise FileNotFoundError(f"source release not found: {source}")
    if source == target or source in target.parents or target in source.parents:
        raise ValueError("source and target must be separate, non-nested directories")
    if target.exists():
        raise FileExistsError(f"target already exists: {target}")
    for p in source.rglob("*"):
        if p.is_symlink() or not (p.is_file() or p.is_dir()):
            raise ValueError(f"source release may contain only regular files and directories: {p.name}")
    if not (source / CLINICAL).is_file() or not (source / PROTEIN).is_file():
        raise FileNotFoundError("source must contain clinical.tsv and protein_rppa.tsv.gz")

    # Validate and mutate in memory before creating the output directory.
    clinical = _read_text(source / CLINICAL)
    protein = _read_text(source / PROTEIN, index_col=0)
    if "sampleID" not in clinical or clinical["sampleID"].str.strip().eq("").any() \
            or clinical["sampleID"].duplicated().any():
        raise ValueError("clinical sampleID must exist, be populated and unique")
    if protein.columns.has_duplicates or protein.index.has_duplicates:
        raise ValueError("protein sample IDs and feature names must be unique")
    # Numeric view for choosing observable mutations; edits go to the text frame.
    # Cast to float so "1" and "1.0" compare equal (Series.equals is dtype-strict).
    numeric = protein.apply(pd.to_numeric, errors="coerce").astype(float)
    rng = random.Random(seed)
    changes: list[Change] = []
    protein_changed = clinical_changed = False

    if scenario in {"swap", "duplicate"}:
        # Non-identical profiles avoid a planted mutation with no observable effect.
        candidates = [c for c in protein.columns if numeric[c].notna().any()]
        rng.shuffle(candidates)
        if len(candidates) < 2:
            raise ValueError("need two distinct nonempty protein profiles")
        x = candidates[0]
        y = next((c for c in candidates[1:] if not numeric[x].equals(numeric[c])), None)
        if y is None:
            raise ValueError("need two distinct nonempty protein profiles")
        if scenario == "swap":
            protein[x], protein[y] = protein[y].copy(), protein[x].copy()
            changes = [Change(x, "swap", PROTEIN, related_sample_id=y),
                       Change(y, "swap", PROTEIN, related_sample_id=x)]
        else:
            protein[x] = protein[y].copy()
            changes = [Change(x, "duplicate", PROTEIN, related_sample_id=y)]
        protein_changed = True
    elif scenario == "disappeared":
        if len(protein.columns) < 1:
            raise ValueError("need at least one protein profile")
        sample = rng.choice(list(protein.columns))
        protein = protein.drop(columns=[sample])
        changes = [Change(sample, "disappeared", PROTEIN)]
        protein_changed = True
    elif scenario == "label_change":
        if ER_COL not in clinical:
            raise ValueError(f"clinical file missing {ER_COL}")
        eligible = clinical.index[clinical[ER_COL].isin(["Positive", "Negative"])].tolist()
        if not eligible:
            raise ValueError("need a Positive or Negative ER label")
        idx = rng.choice(eligible)
        old = clinical.at[idx, ER_COL]
        new = "Negative" if old == "Positive" else "Positive"
        clinical.at[idx, ER_COL] = new
        changes = [Change(clinical.at[idx, "sampleID"], "label_change", CLINICAL, [ER_COL], before=old, after=new)]
        clinical_changed = True
    elif scenario == "value_shift":
        # Shift a finite ER-alpha value by an amount that is representable, so the
        # mutation is observable (inf + 10 or 1e20 + 10 would leave it unchanged).
        if SHIFT_FEATURE not in protein.index:
            raise ValueError(f"protein file missing {SHIFT_FEATURE}")
        row = numeric.loc[SHIFT_FEATURE]
        eligible = [c for c in protein.columns
                    if math.isfinite(row[c]) and math.isfinite(row[c] + SHIFT) and row[c] + SHIFT != row[c]]
        if not eligible:
            raise ValueError(f"need a finite {SHIFT_FEATURE} value")
        sample = rng.choice(eligible)
        old = float(row[sample])
        new = old + SHIFT
        protein.at[SHIFT_FEATURE, sample] = repr(new)
        changes = [Change(sample, "value_shift", PROTEIN, [SHIFT_FEATURE], before=old, after=new)]
        protein_changed = True
    elif scenario == "reordered":
        clinical = clinical.iloc[::-1]
        protein = protein.iloc[::-1, ::-1]
        clinical_changed = protein_changed = True

    # Exclusively create the directory; never clean up a pre-existing target.
    target.mkdir()
    try:
        shutil.copytree(source, target, dirs_exist_ok=True)
        if clinical_changed:
            clinical.to_csv(target / CLINICAL, sep="\t", index=False, lineterminator="\n")
        if protein_changed:
            protein.to_csv(target / PROTEIN, sep="\t", lineterminator="\n",
                           compression={"method": "gzip", "mtime": 0})
    except BaseException:  # includes Ctrl-C: never leave a half-written release behind
        if target.is_dir():
            shutil.rmtree(target)
        raise
    return changes


def _key(change: Change) -> tuple[str, str, str]:
    return change.change_type, change.file, change.sample_id


def evaluate(expected: list[Change], observed: list[Change]) -> dict:
    """Strict per-sample/type/file matching, reported separately for each change type.

    Duplicate identical reports count as extra false positives. Swap partners and
    duplicate sources are scored separately (``partner_matches``); affected fields are
    not scored. These metrics do not establish biological interpretation or
    downstream analysis correctness.
    """
    expected_counts, observed_counts = Counter(map(_key, expected)), Counter(map(_key, observed))
    # A partner match needs the same key and the same related_sample_id.
    expected_partner = Counter((_key(c), c.related_sample_id) for c in expected if c.related_sample_id is not None)
    observed_partner = Counter((_key(c), c.related_sample_id) for c in observed if c.related_sample_id is not None)
    types = sorted({k[0] for k in expected_counts} | {k[0] for k in observed_counts})
    results = []
    for kind in types:
        keys = {k for k in expected_counts | observed_counts if k[0] == kind}
        tp = sum(min(expected_counts[k], observed_counts[k]) for k in keys)
        fp = sum(max(0, observed_counts[k] - expected_counts[k]) for k in keys)
        fn = sum(max(0, expected_counts[k] - observed_counts[k]) for k in keys)
        partnered = {k: n for k, n in expected_partner.items() if k[0][0] == kind}
        results.append({"change_type": kind, "expected": tp + fn, "reported": tp + fp,
                        "true_positives": tp, "false_positives": fp, "false_negatives": fn,
                        "precision": tp / (tp + fp) if tp + fp else None,
                        "recall": tp / (tp + fn) if tp + fn else None,
                        "expected_with_partner": sum(partnered.values()),
                        "partner_matches": sum(min(n, observed_partner[k]) for k, n in partnered.items())})
    return {"matching": "exact change_type, file and sample_id; partner scored separately; fields not scored",
            "expected_total": len(expected), "reported_total": len(observed),
            "false_positives_on_no_change": len(observed) if not expected else None,
            "by_change_type": results}
