"""Generate controlled copies and score contract changes; never modify the source release."""
from __future__ import annotations

import csv
import gzip
import math
import random
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

from tripwire.contract import Change, norm_id

PROTEIN = "protein_rppa.tsv.gz"
CLINICAL = "clinical.tsv"
ER_COL = "breast_carcinoma_estrogen_receptor_status"
SHIFT_FEATURE = "ERALPHA"
SHIFT = 10.0
# Barcode sample-type codes the lab rewrites, and what each becomes (primary tumour,
# metastatic, solid normal: the codes the contract names).
TYPE_CODE_CHANGE = {"01": "06", "06": "01", "11": "01"}
BARCODE = re.compile(r"^TCGA-[A-Za-z0-9]{2}-[A-Za-z0-9]{4}-(\d{2})")
COVERAGE_FRACTION = 0.25  # share of one ER subgroup's protein profiles that lose all values
MISSING_TOKEN = "NA"
# Original scenarios first and in their original order (backwards compatible).
SCENARIOS = ("unchanged", "reordered", "swap", "duplicate", "disappeared", "label_change", "value_shift",
             "id_case_change", "id_whitespace", "sample_type_change", "coverage_loss")
CONTROLS = ("unchanged", "reordered")
DESCRIPTIONS = {
    "unchanged": "no-change control: an exact copy",
    "reordered": "no-change control: same data, rows and columns in reverse order",
    "swap": "two samples' protein profiles exchanged",
    "duplicate": "one sample's protein profile overwritten with another's",
    "disappeared": "one sample's protein profile removed",
    "label_change": "one sample's ER status flipped in clinical.tsv",
    "value_shift": "one ER-alpha value shifted by +10",
    "id_case_change": "one protein sample ID re-written in different letter case",
    "id_whitespace": "one protein sample ID padded with a leading or trailing space",
    "sample_type_change": "one protein sample's barcode type code changed (01->06, 06->01 or 11->01)",
    "coverage_loss": "a quarter of one ER subgroup's protein profiles blanked to NA; other subgroups untouched",
}


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


def _pick_type_change(protein: pd.DataFrame, clinical: pd.DataFrame, numeric: pd.DataFrame,
                      rng: random.Random) -> tuple[str, str]:
    """Choose a barcode whose type code can change without the planted change becoming ambiguous.

    Skipped: IDs that are not TCGA barcodes or carry another type code; new IDs that already
    exist (by comparison key) in the protein header or clinical.tsv; profiles with no values
    or that exactly equal another profile, so the moved profile identifies one sample only.
    """
    taken = {norm_id(c) for c in protein.columns} | {norm_id(s) for s in clinical["sampleID"]}
    keys = Counter(norm_id(c) for c in protein.columns)
    shared = numeric.T.duplicated(keep=False)  # numerically identical profiles, NaN positions included
    eligible = []
    for c in protein.columns:
        m = BARCODE.match(c)
        if not m or m.group(1) not in TYPE_CODE_CHANGE or keys[norm_id(c)] != 1:
            continue
        new = c[:13] + TYPE_CODE_CHANGE[m.group(1)] + c[15:]
        if norm_id(new) not in taken and numeric[c].notna().any() and not shared[c]:
            eligible.append((c, new))
    if not eligible:
        raise ValueError("need a TCGA barcode with type code 01, 06 or 11, a unique nonempty profile, "
                         "and a free target ID")
    return rng.choice(eligible)


def _blank_subgroup(protein: pd.DataFrame, clinical: pd.DataFrame, numeric: pd.DataFrame,
                    rng: random.Random) -> tuple[pd.DataFrame, list[Change]]:
    """Concentrate missing data in one ER subgroup: blank every present value of some of its profiles.

    Only cells that parse as numbers are blanked (to ``NA``); text and existing blanks are left
    as they were. Profiles of other subgroups and of unlabelled samples are not touched.
    """
    if ER_COL not in clinical:
        raise ValueError(f"clinical file missing {ER_COL}")
    status = dict(zip(clinical["sampleID"], clinical[ER_COL]))
    groups = defaultdict(list)
    for c in protein.columns:
        if status.get(c) in ("Positive", "Negative") and numeric[c].notna().any():
            groups[status[c]].append(c)
    if not groups:
        raise ValueError("need protein profiles with values for samples labelled ER Positive or Negative")
    group = rng.choice(sorted(groups))
    members = groups[group]
    order = {c: i for i, c in enumerate(protein.columns)}
    chosen = sorted(rng.sample(members, max(1, math.ceil(COVERAGE_FRACTION * len(members)))), key=order.get)
    protein = protein.copy()
    changes = []
    for c in chosen:
        present = numeric[c].notna()
        protein.loc[present, c] = MISSING_TOKEN
        changes.append(Change(c, "coverage_loss", PROTEIN, [str(f) for f in protein.index[present]],
                              f"ER {group} subgroup: {len(chosen)} of {len(members)} profiles with values were "
                              "blanked; other subgroups untouched",
                              f"{int(present.sum())} of {len(present)} values present",
                              f"0 of {len(present)} values present"))
    return protein, changes


def generate(source: Path, target: Path, scenario: str, seed: int = 0) -> list[Change]:
    """Make a new release copy and return planted changes in the shared contract.

    A swap has two sample-level expected changes; a duplicate is the overwritten
    target only. ID-format and sample-type scenarios rename one protein header and
    keep its values; coverage loss has one record per blanked profile. Exact profile
    equality does not establish biological identity. Unplanted cells are written
    back as their original text.
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
    elif scenario in {"id_case_change", "id_whitespace"}:
        # Same sample, same values: only the header text changes. Skip IDs that already
        # share a comparison key with another column, where "same sample" is ambiguous.
        keys = Counter(norm_id(c) for c in protein.columns)
        renames = {}
        for c in protein.columns:
            if keys[norm_id(c)] != 1:
                continue
            if scenario == "id_case_change":
                new = c.lower() if c.lower() != c else c.upper()
                if new != c:
                    renames[c] = new
            else:
                renames[c] = None  # padding side chosen after the sample, for a stable seed sequence
        if not renames:
            what = "letters whose case can change" if scenario == "id_case_change" else "an unambiguous ID"
            raise ValueError(f"need a protein sample ID with {what}")
        sample = rng.choice(list(renames))
        new = renames[sample] or (rng.choice([" " + sample, sample + " "]))
        how = "letter case" if scenario == "id_case_change" else "surrounding whitespace"
        protein = protein.rename(columns={sample: new})
        changes = [Change(sample, "id_format_change", PROTEIN, [],
                          f"same sample and values; ID {how} changed from {sample!r} to {new!r}", sample, new)]
        protein_changed = True
    elif scenario == "sample_type_change":
        sample, new = _pick_type_change(protein, clinical, numeric, rng)
        protein = protein.rename(columns={sample: new})
        changes = [Change(sample, "sample_type_change", PROTEIN, [],
                          f"same patient and profile; barcode type code changed {sample[13:15]} -> {new[13:15]}",
                          sample, new, related_sample_id=new)]
        protein_changed = True
    elif scenario == "coverage_loss":
        protein, changes = _blank_subgroup(protein, clinical, numeric, rng)
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
    not scored. A miss that the detector reported for the same file and sample under
    another change type stays a false negative (and the report a false positive), but
    is also listed in ``reported_as_other_type`` so an interpretation difference is
    visible rather than hidden. These metrics do not establish biological
    interpretation or downstream analysis correctness.
    """
    expected_counts, observed_counts = Counter(map(_key, expected)), Counter(map(_key, observed))
    other_type = _other_type(expected_counts - observed_counts, observed_counts - expected_counts)
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
                        "partner_matches": sum(min(n, observed_partner[k]) for k, n in partnered.items()),
                        "missed_but_reported_as_other_type": sum(n for (e, _), n in other_type.items() if e == kind)})
    return {"matching": "exact change_type, file and sample_id; partner scored separately; fields not scored",
            "expected_total": len(expected), "reported_total": len(observed),
            "false_positives_on_no_change": len(observed) if not expected else None,
            "by_change_type": results,
            "reported_as_other_type": [{"expected_type": e, "reported_type": r, "count": n}
                                       for (e, r), n in sorted(other_type.items())]}


def _other_type(missed: Counter, extra: Counter) -> Counter:
    """Pair each missed expected change with an unmatched report for the same file and sample."""
    pool: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for (kind, file, sample), n in extra.items():
        pool[file, sample][kind] += n
    pairs: Counter = Counter()
    for (kind, file, sample), n in sorted(missed.items()):
        reports = pool[file, sample]
        for other in sorted(reports):
            take = min(n, reports[other])
            pairs[kind, other] += take
            reports[other] -= take
            n -= take
            if not n:
                break
    return +pairs
