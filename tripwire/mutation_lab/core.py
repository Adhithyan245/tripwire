"""Generate controlled copies and score contract changes; never modify the source release."""
from __future__ import annotations

import random
import shutil
from pathlib import Path

import pandas as pd

from tripwire.contract import Change

PROTEIN = "protein_rppa.tsv.gz"
CLINICAL = "clinical.tsv"
SCENARIOS = ("unchanged", "reordered", "swap", "duplicate", "disappeared", "label_change", "value_shift")


def generate(source: Path, target: Path, scenario: str, seed: int = 0) -> list[Change]:
    """Make a new release copy and return planted changes in the shared contract.

    A swap has two sample-level expected changes; a duplicate is the overwritten
    target only. Exact profile equality does not establish biological identity.
    """
    source, target = Path(source).resolve(), Path(target).resolve()
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario {scenario!r}")
    if not source.is_dir():
        raise FileNotFoundError(f"source release not found: {source}")
    if source == target or source in target.parents or target in source.parents:
        raise ValueError("source and target must be separate, non-nested directories")
    if target.exists():
        raise FileExistsError(f"target already exists: {target}")
    if any(p.is_symlink() for p in source.rglob('*')):
        raise ValueError("source release cannot contain symlinks")
    if not (source / CLINICAL).is_file() or not (source / PROTEIN).is_file():
        raise FileNotFoundError("source must contain clinical.tsv and protein_rppa.tsv.gz")

    # Validate and mutate in memory before creating the output directory.
    clinical = pd.read_csv(source / CLINICAL, sep="\t", dtype={"sampleID": str}, low_memory=False)
    protein = pd.read_csv(source / PROTEIN, sep="\t", index_col=0)
    if "sampleID" not in clinical or clinical["sampleID"].isna().any() or clinical["sampleID"].duplicated().any():
        raise ValueError("clinical sampleID must exist, be populated and unique")
    if protein.columns.has_duplicates or protein.index.has_duplicates:
        raise ValueError("protein sample IDs and feature names must be unique")
    rng = random.Random(seed)
    changes: list[Change] = []
    protein_changed = clinical_changed = False

    if scenario in {"swap", "duplicate"}:
        # Non-identical profiles avoid a planted mutation with no observable effect.
        candidates = [c for c in protein.columns if protein[c].notna().any()]
        rng.shuffle(candidates)
        if len(candidates) < 2:
            raise ValueError("need two distinct nonempty protein profiles")
        x = candidates[0]
        y = next((c for c in candidates[1:] if not protein[x].equals(protein[c])), None)
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
        col = "breast_carcinoma_estrogen_receptor_status"
        if col not in clinical:
            raise ValueError(f"clinical file missing {col}")
        eligible = clinical.index[clinical[col].isin(["Positive", "Negative"])].tolist()
        if not eligible:
            raise ValueError("need a Positive or Negative ER label")
        idx = rng.choice(eligible)
        old = clinical.at[idx, col]
        new = "Negative" if old == "Positive" else "Positive"
        clinical.at[idx, col] = new
        changes = [Change(clinical.at[idx, "sampleID"], "label_change", CLINICAL, [col], before=old, after=new)]
        clinical_changed = True
    elif scenario == "value_shift":
        # Shift a non-null ER-alpha value so the mutation is observable.
        if "ERALPHA" not in protein.index:
            raise ValueError("protein file missing ERALPHA")
        eligible = [c for c in protein.columns if pd.notna(protein.at["ERALPHA", c])]
        if not eligible:
            raise ValueError("need a non-null ERALPHA value")
        sample = rng.choice(eligible)
        old = float(protein.at["ERALPHA", sample])
        protein.at["ERALPHA", sample] = old + 10.0
        changes = [Change(sample, "value_shift", PROTEIN, ["ERALPHA"], before=old, after=old + 10.0)]
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
            clinical.to_csv(target / CLINICAL, sep="\t", index=False)
        if protein_changed:
            protein.to_csv(target / PROTEIN, sep="\t", compression={"method": "gzip", "mtime": 0})
    except Exception:
        if target.is_dir():
            shutil.rmtree(target)
        raise
    return changes


def _key(change: Change) -> tuple[str, str, str]:
    return change.change_type, change.file, change.sample_id


def evaluate(expected: list[Change], observed: list[Change]) -> dict:
    """Strict per-sample/type/file matching, reported separately for each change type.

    Duplicate identical reports count as extra false positives. Related IDs and fields
    are not yet scored: these metrics do not establish that the proposed partner,
    biological interpretation, or downstream analysis is correct.
    """
    from collections import Counter
    expected_counts, observed_counts = Counter(map(_key, expected)), Counter(map(_key, observed))
    types = sorted({k[0] for k in expected_counts} | {k[0] for k in observed_counts})
    results = []
    for kind in types:
        keys = {k for k in expected_counts | observed_counts if k[0] == kind}
        tp = sum(min(expected_counts[k], observed_counts[k]) for k in keys)
        fp = sum(max(0, observed_counts[k] - expected_counts[k]) for k in keys)
        fn = sum(max(0, expected_counts[k] - observed_counts[k]) for k in keys)
        results.append({"change_type": kind, "expected": tp + fn, "reported": tp + fp,
                        "true_positives": tp, "false_positives": fp, "false_negatives": fn,
                        "precision": tp / (tp + fp) if tp + fp else None,
                        "recall": tp / (tp + fn) if tp + fn else None})
    return {"matching": "exact change_type, file and sample_id; partner and fields not scored",
            "expected_total": len(expected), "reported_total": len(observed),
            "false_positives_on_no_change": len(observed) if not expected else None,
            "by_change_type": results}
