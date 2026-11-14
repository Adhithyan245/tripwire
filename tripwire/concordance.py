"""Biological consistency: receptor labels that contradict the tumor's own molecular data.

In breast cancer, ER and HER2 status decide treatment and every downstream study, and a mislabelled sample silently
poisons a model trained on it. This check flags samples whose clinical label disagrees strongly with their own
measurement, within one release, so it also catches errors that were already in the trusted release:

  ER    breast_carcinoma_estrogen_receptor_status vs ER-alpha protein (RPPA, ERALPHA)
        Negative but ER-alpha at or above the typical ER-positive level and >= 3 robust SDs above its own group,
        or Positive but at or below the typical ER-negative level and >= 3 robust SDs below its own group.
  HER2  HER2_Final_Status_nature2012 vs ERBB2 copy number (GISTIC) and HER2 protein (RPPA)
        Negative but high-level ERBB2 amplification (GISTIC 2) and HER2 protein at or above the typical positive level,
        or Positive but no ERBB2 gain (GISTIC <= 0) and HER2 protein at or below the typical negative level.

Deliberately conservative: a flag is evidence for a person to check, never a correction. Tumor heterogeneity, assay
thresholds or a true borderline case can explain a mismatch. Research use only; not a diagnosis.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .contract import norm_id
from .release import Release

ER_COL = "breast_carcinoma_estrogen_receptor_status"
HER2_COL = "HER2_Final_Status_nature2012"
ROBUST_Z = 3.0
MARKER_TEXT = {"ER": "ER-alpha protein far on the other side of the ER-positive / ER-negative divide",
               "HER2": "ERBB2 copy number and HER2 protein both on the other side of the HER2 divide"}


@dataclass(frozen=True)
class Discordance:
    sample: str
    marker: str        # "ER" | "HER2"
    label_field: str
    label: str
    evidence: str      # what the sample's own data says, in plain words


def _labels(r: Release, col: str) -> pd.Series:
    if not r.has("clinical.tsv") or col not in r.clinical.columns:
        return pd.Series(dtype=object)
    c = r.clinical.drop_duplicates(subset=["sampleID"])
    s = pd.Series(c[col].values, index=c["sampleID"].map(norm_id))
    s = s[~s.index.duplicated(keep=False)]  # an ID listed twice (e.g. different case) is ambiguous: leave it out
    return s[s.isin(["Positive", "Negative"])]


def _row(r: Release, name: str, feature: str) -> pd.Series:
    if not r.has(name):
        return pd.Series(dtype=float)
    t = r.table(name)
    if feature not in t.index:
        return pd.Series(dtype=float)
    v = pd.to_numeric(t.loc[feature], errors="coerce")
    v.index = [norm_id(s) for s in v.index]
    return v[~v.index.duplicated()].dropna()


def _robust(x: pd.Series) -> tuple[float, float]:
    med = float(np.median(x))
    mad = float(np.median(np.abs(x - med))) * 1.4826
    return med, (mad if mad > 0 else float(np.std(x)) or 1.0)


def er_discordance(r: Release) -> list[Discordance]:
    lab, prot = _labels(r, ER_COL), _row(r, "protein_rppa.tsv.gz", "ERALPHA")
    both = lab.index.intersection(prot.index)
    if len(both) < 20:
        return []
    lab, prot = lab[both], prot[both]
    pos, neg = prot[lab == "Positive"], prot[lab == "Negative"]
    if len(pos) < 10 or len(neg) < 10:
        return []
    mp, sp = _robust(pos)
    mn, sn = _robust(neg)
    out = []
    for s in both:
        v = float(prot[s])
        if lab[s] == "Negative" and v >= mp and (v - mn) / sn >= ROBUST_Z:
            out.append(Discordance(s, "ER", ER_COL, "Negative",
                                   f"labelled ER-negative, but ER-alpha protein {v:.2f} is at or above the typical "
                                   f"ER-positive level ({mp:.2f}) and {(v - mn) / sn:.1f} robust SDs above ER-negative tumors"))
        elif lab[s] == "Positive" and v <= mn and (mp - v) / sp >= ROBUST_Z:
            out.append(Discordance(s, "ER", ER_COL, "Positive",
                                   f"labelled ER-positive, but ER-alpha protein {v:.2f} is at or below the typical "
                                   f"ER-negative level ({mn:.2f}) and {(mp - v) / sp:.1f} robust SDs below ER-positive tumors"))
    return out


def her2_discordance(r: Release) -> list[Discordance]:
    lab = _labels(r, HER2_COL)
    cn = _row(r, "copy_number_gistic.tsv.gz", "ERBB2")
    prot = _row(r, "protein_rppa.tsv.gz", "HER2")
    both = lab.index.intersection(cn.index).intersection(prot.index)
    if len(both) < 20:
        return []
    lab, cn, prot = lab[both], cn[both], prot[both]
    pos, neg = prot[lab == "Positive"], prot[lab == "Negative"]
    if len(pos) < 10 or len(neg) < 10:
        return []
    mp, mn = float(np.median(pos)), float(np.median(neg))
    out = []
    for s in both:
        c, v = float(cn[s]), float(prot[s])
        if lab[s] == "Negative" and c >= 2 and v >= mp:
            out.append(Discordance(s, "HER2", HER2_COL, "Negative",
                                   f"labelled HER2-negative, but ERBB2 is highly amplified (GISTIC {c:.0f}) and HER2 "
                                   f"protein {v:.2f} is at or above the typical HER2-positive level ({mp:.2f})"))
        elif lab[s] == "Positive" and c <= 0 and v <= mn:
            out.append(Discordance(s, "HER2", HER2_COL, "Positive",
                                   f"labelled HER2-positive, but ERBB2 shows no gain (GISTIC {c:.0f}) and HER2 protein "
                                   f"{v:.2f} is at or below the typical HER2-negative level ({mn:.2f})"))
    return out


def discordances(r: Release) -> list[Discordance]:
    return er_discordance(r) + her2_discordance(r)
