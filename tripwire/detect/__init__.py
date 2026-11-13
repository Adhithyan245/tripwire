"""Detection engine (Role 1). Baseline written by Role 2 at the repo owner's request; Role 1 reviews and owns it.

Finds what changed between two releases, file by file, without being told what to look for:

  molecular files (samples as columns): ID format changes, appeared / disappeared samples, swaps, copies of another
      sample's profile (exact or near-identical), sample-type code changes, and value changes with the fields affected
  row files (clinical.tsv, survival.tsv: one row per sample): appeared / disappeared rows, changed values per column,
      sample-type code changes

Conservative by design: a profile that several samples already share in release A carries no identity, so matching
it is never called a swap or a copy. A file missing from the new release is a finding, except the RNA file that
envelopes leave out by design.
"""
from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from ..contract import Change, norm_id
from ..release import Release, content_sha256

ROW_FILES = {"clinical.tsv": "sampleID", "survival.tsv": "sample"}
NEAR_DUP_R = 0.999          # Pearson r above which two continuous profiles count as near-identical
CONTINUOUS_MIN_UNIQUE = 50  # a file is "continuous" if a typical sample has at least this many distinct values
MAX_FIELDS = 200            # cap on fields listed for one change


# Envelope releases leave this file out by design; its absence is not a finding.
EXPECTED_ABSENT = {"rna_hiseq.tsv.gz"}


def detect_changes(release_a: Release, release_b: Release) -> list[Change]:
    out: list[Change] = []
    for name in sorted(set(release_a.files) - set(release_b.files) - EXPECTED_ABSENT):
        out += _vanished_file(release_a, name)
    for name in sorted(set(release_a.files) & set(release_b.files)):
        if content_sha256(release_a.path / name) == content_sha256(release_b.path / name):
            continue  # identical content (line endings aside): nothing can have changed
        if name in ROW_FILES:
            out += _diff_rows(name, _read_rows(release_a, name), _read_rows(release_b, name), ROW_FILES[name])
        else:
            out += _diff_matrix(name, _read_matrix(release_a, name), _read_matrix(release_b, name))
    return out


def _vanished_file(r: Release, name: str) -> list[Change]:
    """A whole file missing from the new release: every sample in it lost that data."""
    if name in ROW_FILES:
        ids = _read_rows(r, name)[ROW_FILES[name]].tolist()
    else:
        ids = list(_read_matrix(r, name).columns)
    return [Change(s, "disappeared", name, [], f"the whole file {name} is missing from the new release", "present", None)
            for s in ids]


# ---------------------------------------------------------------- helpers

def _patient(s: str) -> str:
    return norm_id(s)[:12]


def _type_code(s: str) -> str:
    return norm_id(s)[13:15]


def _id_maps(ids) -> dict[str, str]:
    return {norm_id(s): s for s in ids}


def _hash(col: np.ndarray) -> str:
    v = np.round(col.astype(float), 6)
    v = np.where(np.isnan(v), np.inf, v)  # NaN-safe and stable
    return hashlib.sha1(v.tobytes()).hexdigest()[:16]


def _informative(col: np.ndarray) -> bool:
    v = col[~np.isnan(col)]
    return v.size >= 3 and np.unique(v).size >= 2


# ---------------------------------------------------------------- molecular files

def _read_matrix(r: Release, name: str) -> pd.DataFrame:
    if name == "protein_rppa.tsv.gz":
        return r.protein
    return pd.read_csv(r.path / name, sep="	", index_col=0)


def _diff_matrix(name: str, a: pd.DataFrame, b: pd.DataFrame) -> list[Change]:
    out: list[Change] = []
    ma, mb = _id_maps(a.columns), _id_maps(b.columns)
    for k in ma.keys() & mb.keys():
        if ma[k] != mb[k]:
            out.append(Change(ma[k], "id_format_change", name, [], f"same sample, ID written as {mb[k]!r} in the new "
                              f"release (was {ma[k]!r})", ma[k], mb[k]))
    feats = a.index.intersection(b.index)
    A = a.loc[feats].rename(columns=norm_id)
    B = b.loc[feats].rename(columns=norm_id)
    A, B = A.loc[:, ~A.columns.duplicated()], B.loc[:, ~B.columns.duplicated()]
    av, bv = A.to_numpy(float), B.to_numpy(float)
    ai, bi = {s: i for i, s in enumerate(A.columns)}, {s: i for i, s in enumerate(B.columns)}
    ha = {s: _hash(av[:, i]) for s, i in ai.items()}
    hb = {s: _hash(bv[:, i]) for s, i in bi.items()}
    by_hash_a: dict[str, list[str]] = {}
    for s, h in ha.items():
        by_hash_a.setdefault(h, []).append(s)
    by_hash_b: dict[str, list[str]] = {}
    for s, h in hb.items():
        by_hash_b.setdefault(h, []).append(s)
    continuous = np.median([np.unique(av[:, i][~np.isnan(av[:, i])]).size for i in range(min(av.shape[1], 50))] or [0]) \
        >= CONTINUOUS_MIN_UNIQUE

    def a_identity(h: str, exclude: str) -> str | None:
        """The single release-A sample that owned this profile, if the profile identifies anyone."""
        owners = [s for s in by_hash_a.get(h, []) if s != exclude]
        if len(by_hash_a.get(h, [])) == 1 and owners and _informative(av[:, ai[owners[0]]]):
            return owners[0]
        return None

    def near_a(col: np.ndarray, exclude: set[str]) -> tuple[str, float] | None:
        if not continuous or not _informative(col):
            return None
        best = _nearest(col, av, list(ai), exclude)
        return best if best and best[1] >= NEAR_DUP_R else None

    raw = lambda s, side: (mb if side == "B" else ma).get(s, s)
    common = ai.keys() & bi.keys()
    appeared, disappeared = sorted(bi.keys() - ai.keys()), sorted(ai.keys() - bi.keys())
    changed = sorted(s for s in common if ha[s] != hb[s])
    done: set[str] = set()

    for s in changed:
        if s in done:
            continue
        col_b = bv[:, bi[s]]
        src, how = a_identity(hb[s], s), "identical"
        if src is None:
            nn = near_a(col_b, {s})
            if nn:
                src, how = nn[0], f"near-identical (r={nn[1]:.4f})"
        if src and src in common and (hb[src] == ha[s] or _r(bv[:, bi[src]], av[:, ai[s]]) >= NEAR_DUP_R) and src not in done:
            out.append(Change(raw(s, "B"), "swap", name, [], f"profile is {how} to {raw(src, 'A')}'s in the previous "
                              f"release, and {raw(src, 'B')} now carries this sample's old profile",
                              "own profile", f"profile of {raw(src, 'A')}", related_sample_id=raw(src, "B")))
            out.append(Change(raw(src, "B"), "swap", name, [], f"profile is {how} to {raw(s, 'A')}'s in the previous "
                              f"release (pair of the swap above)", "own profile", f"profile of {raw(s, 'A')}",
                              related_sample_id=raw(s, "B")))
            done |= {s, src}
        elif src and src in bi and hb.get(src) == ha.get(src):
            out.append(Change(raw(s, "B"), "duplicate", name, [], f"profile is {how} to {raw(src, 'B')}'s; this sample's "
                              "own profile is gone", "own profile", f"copy of {raw(src, 'B')}",
                              related_sample_id=raw(src, "B")))
            done.add(s)
        else:
            out.append(_value_change(name, raw(s, "B"), feats, av[:, ai[s]], col_b, src, how))
            done.add(s)

    gone = set(disappeared)
    for s in appeared:
        col_b = bv[:, bi[s]]
        twins = [t for t in by_hash_b.get(hb[s], []) if t != s and t in common and hb[t] == ha[t]]
        if twins and _informative(col_b):
            out.append(Change(raw(s, "B"), "duplicate", name, [], f"new sample whose profile is identical to "
                              f"{raw(twins[0], 'B')}'s", None, f"copy of {raw(twins[0], 'B')}",
                              related_sample_id=raw(twins[0], "B")))
            continue
        moved = [d for d in gone if _patient(d) == _patient(s) and ha[d] == hb[s]]
        if moved:
            d = moved[0]
            gone.discard(d)
            out.append(Change(raw(d, "A"), "sample_type_change", name, [], f"same profile and patient, sample-type code "
                              f"changed {_type_code(d)} -> {_type_code(s)}", raw(d, "A"), raw(s, "B"),
                              related_sample_id=raw(s, "B")))
            continue
        nn = near_a(col_b, gone) if continuous else None
        if nn and nn[0] in common:
            out.append(Change(raw(s, "B"), "duplicate", name, [], f"new sample whose profile is near-identical "
                              f"(r={nn[1]:.4f}) to {raw(nn[0], 'A')}'s", None, f"copy of {raw(nn[0], 'A')}",
                              related_sample_id=raw(nn[0], "B")))
            continue
        out.append(Change(raw(s, "B"), "appeared", name, [], f"in the new release's {name}, not in the previous one",
                          None, "present"))
    for d in sorted(gone):
        out.append(Change(raw(d, "A"), "disappeared", name, [], f"in the previous release's {name}, not in the new one",
                          "present", None))
    return out


def _value_change(name, sample, feats, col_a, col_b, src, how) -> Change:
    diff = ~(np.isclose(col_a, col_b, equal_nan=True))
    fields = [str(f) for f in feats[diff]][:MAX_FIELDS]
    na_a, na_b = int(np.isnan(col_a).sum()), int(np.isnan(col_b).sum())
    bits = [f"{int(diff.sum())} of {len(feats)} values changed"]
    if na_b > na_a:
        bits.append(f"missing values rose from {na_a} to {na_b}")
    if src:
        bits.append(f"now {how} to {src}'s previous profile, but that profile isn't unique enough to call a copy")
    ok = ~np.isnan(col_a) & ~np.isnan(col_b) & diff
    if ok.sum() >= 3 and np.all(col_a[ok] != 0):
        ratio = np.median(col_b[ok] / col_a[ok])
        if abs(ratio - 1) > 0.05 and np.allclose(col_b[ok] / col_a[ok], ratio, rtol=0.02):
            bits.append(f"values scaled by about {ratio:.3g} (possible unit change)")
    i = int(np.argmax(diff)) if diff.any() else 0
    return Change(sample, "value_shift", name, fields, "; ".join(bits),
                  f"{feats[i]}={col_a[i]:.4g}", f"{feats[i]}={col_b[i]:.4g}")


def _r(x: np.ndarray, y: np.ndarray) -> float:
    ok = ~np.isnan(x) & ~np.isnan(y)
    if ok.sum() < 3 or np.std(x[ok]) == 0 or np.std(y[ok]) == 0:
        return 0.0
    return float(np.corrcoef(x[ok], y[ok])[0, 1])


def _nearest(col: np.ndarray, mat: np.ndarray, names: list[str], exclude: set[str]) -> tuple[str, float] | None:
    m = np.where(np.isnan(mat), np.nanmean(mat, axis=0, keepdims=True), mat)
    x = np.where(np.isnan(col), np.nanmean(col), col)
    m = (m - m.mean(0)) / (m.std(0) + 1e-12)
    x = (x - x.mean()) / (x.std() + 1e-12)
    r = (m * x[:, None]).mean(0)
    for j in np.argsort(-r):
        if names[j] not in exclude:
            return names[j], float(r[j])
    return None


# ---------------------------------------------------------------- row files

def _read_rows(r: Release, name: str) -> pd.DataFrame:
    # exact text, so a change is a real change and not a parsing artefact
    return pd.read_csv(r.path / name, sep="\t", dtype=str, keep_default_na=False)


ID_LIKE = {"sampleID", "sample", "sample_type", "sample_type_id", "_PATIENT"}
MISSING = {"", "na", "nan", "none", "null", "n/a"}


def _canon(df: pd.DataFrame) -> np.ndarray:
    """Compare values, not formatting: '55' == '55.0', 'true' == 'True', and blank / NA / nan are all missing."""
    out = {}
    for c in df.columns:
        t = df[c].astype(str).str.strip().str.replace(r"\s+", " ", regex=True).str.lower()
        miss = t.str.lower().isin(MISSING)
        num = pd.to_numeric(t.where(~miss), errors="coerce")
        out[c] = np.where(miss, "", np.where(num.notna(), num.map(lambda v: repr(float(v))), t))
    return pd.DataFrame(out, index=df.index).to_numpy()


def _diff_rows(name: str, a: pd.DataFrame, b: pd.DataFrame, key: str) -> list[Change]:
    out: list[Change] = []
    if key not in a.columns or key not in b.columns:
        return out
    a = a.drop_duplicates(subset=[key]).set_index(key, drop=False)
    b = b.drop_duplicates(subset=[key]).set_index(key, drop=False)
    ma, mb = _id_maps(a.index), _id_maps(b.index)
    for k in ma.keys() & mb.keys():
        if ma[k] != mb[k]:
            out.append(Change(ma[k], "id_format_change", name, [key], f"same row, ID written as {mb[k]!r} (was {ma[k]!r})",
                              ma[k], mb[k]))
    cols = [c for c in a.columns if c in b.columns and c != key]
    common = sorted(ma.keys() & mb.keys())
    if common:
        A = a.loc[[ma[k] for k in common], cols].to_numpy()
        B = b.loc[[mb[k] for k in common], cols].to_numpy()
        diff = _canon(a.loc[[ma[k] for k in common], cols]) != _canon(b.loc[[mb[k] for k in common], cols])
        for r in np.nonzero(diff.any(axis=1))[0]:
            changed = [cols[j] for j in np.nonzero(diff[r])[0]]
            before = {c: A[r][cols.index(c)] for c in changed[:5]}
            after = {c: B[r][cols.index(c)] for c in changed[:5]}
            desc = "; ".join(f"{c}: {before[c]!r} -> {after[c]!r}" for c in changed[:3])
            more = f" (+{len(changed) - 3} more)" if len(changed) > 3 else ""
            out.append(Change(mb[common[r]], "label_change", name, changed, desc + more, before, after))
    appeared = sorted(mb.keys() - ma.keys())
    gone = set(ma.keys() - mb.keys())
    content = [c for c in cols if c not in ID_LIKE]
    ca = dict(zip(a.index, map(tuple, _canon(a[content])))) if content else {}
    cb = dict(zip(b.index, map(tuple, _canon(b[content])))) if content else {}
    for s in appeared:
        row_b = cb.get(mb[s], ())
        match = [d for d in gone if _patient(d) == _patient(s) and ca.get(ma[d], ()) == row_b]
        if match:
            d = match[0]
            gone.discard(d)
            out.append(Change(ma[d], "sample_type_change", name, [key], f"same patient and values, sample-type code "
                              f"changed {_type_code(d)} -> {_type_code(s)}", ma[d], mb[s], related_sample_id=mb[s]))
        else:
            out.append(Change(mb[s], "appeared", name, [], f"new row in {name}", None, "present"))
    for d in sorted(gone):
        out.append(Change(ma[d], "disappeared", name, [], f"row removed from {name}", "present", None))
    return out
