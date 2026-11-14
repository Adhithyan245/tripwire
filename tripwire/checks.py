"""Readiness checks for model-training questions: patient leakage and site confounding.

Both report a *risk in this data*, not a demonstrated problem: Driftwire never sees the user's actual train/test split
or model. Thresholds are stated in config.py and are prototype policy, not clinical standards.
"""
from __future__ import annotations

from collections import Counter, defaultdict

import numpy as np
import pandas as pd

from .config import CONFIG
from .contract import norm_id
from .questions import QuestionCard, register_check
from .release import Release
from .verdicts import CheckResult


def _labelled(card: QuestionCard, r: Release) -> pd.DataFrame:
    """sampleID, patient, site, label for the card's eligible samples that carry one of its label values."""
    elig = card.eligible(r)
    c = r.clinical.drop_duplicates(subset=["sampleID"])
    d = c[c["sampleID"].map(norm_id).isin(elig) & c[card.label].isin(card.label_values)]
    return pd.DataFrame({"sampleID": d["sampleID"].values, "patient": d["sampleID"].str[:12].str.upper().values,
                         "site": d["sampleID"].str[5:7].str.upper().values, "label": d[card.label].values})


@register_check("patient_leakage")
def patient_leakage(card: QuestionCard, r: Release) -> CheckResult:
    """Two ways the same patient can land on both sides of a train/test split:
    several samples from one patient, or one profile copied under several sample IDs."""
    d = _labelled(card, r)
    if d.empty:
        return CheckResult("patient_leakage", "insufficient", "no labelled samples to check")
    multi = d.groupby("patient")["sampleID"].apply(list)
    multi = multi[multi.map(len) > 1]
    copies: list[list[str]] = []
    ids = set(d["sampleID"])
    for name in card.feature_files:
        t = r.table(name)
        cols = [s for s in t.columns if s in ids]
        groups = defaultdict(list)
        for s in cols:
            v = t[s].to_numpy(float)
            ok = v[~np.isnan(v)]
            if ok.size >= 3 and np.unique(ok).size >= 2:  # a flat or empty profile identifies nobody
                groups[np.round(np.nan_to_num(v, nan=np.inf), 6).tobytes()].append(s)
        copies += [g for g in groups.values() if len(g) > 1]
    ev = [{"kind": "patient", "id": p, "note": f"{len(s)} samples: {', '.join(s)}"} for p, s in multi.items()][:20]
    ev += [{"kind": "sample", "id": g[0], "release": r.name, "note": f"identical profile to {', '.join(g[1:])}"}
           for g in copies][:20]
    n = len(d)
    if multi.empty and not copies:
        return CheckResult("patient_leakage", "pass", f"none of the {n} labelled samples shares a patient or a profile "
                           "with another, so a random split can't put one patient on both sides")
    bits = []
    if not multi.empty:
        bits.append(f"{len(multi)} patient(s) have more than one sample")
    if copies:
        bits.append(f"{sum(len(g) for g in copies)} samples share {len(copies)} identical profile(s)")
    return CheckResult("patient_leakage", "fixable", "; ".join(bits) + f" (of {n}). Potential leakage, not demonstrated: "
                       "it depends on how you split", ev,
                       fix="split by patient_id, and remove copied profiles before splitting")


def cramers_v(labels, sites) -> float:
    t = pd.crosstab(pd.Series(list(labels)), pd.Series(list(sites))).to_numpy(float)
    if t.shape[0] < 2 or t.shape[1] < 2:
        return 0.0
    n = t.sum()
    e = np.outer(t.sum(1), t.sum(0)) / n
    chi2 = ((t - e) ** 2 / e).sum()
    return float(np.sqrt(chi2 / (n * (min(t.shape) - 1))))


@register_check("site_confounding")
def site_confounding(card: QuestionCard, r: Release) -> CheckResult:
    """Is the label spread unevenly across tissue source sites? Then a model could learn the hospital, not the biology."""
    d = _labelled(card, r)
    if len(d) < CONFIG["min_samples_per_group"]:
        return CheckResult("site_confounding", "insufficient", f"only {len(d)} labelled samples")
    counts = d["site"].value_counts()
    site = d["site"].where(d["site"].map(counts) >= CONFIG["site_min_samples"], "other")
    if site.nunique() < 2:
        return CheckResult("site_confounding", "insufficient", "fewer than two sites with enough samples to compare")
    v = cramers_v(d["label"], site)
    lo, hi = CONFIG["site_confounding_v_pass"], CONFIG["site_confounding_v_fail"]
    per_site = (pd.crosstab(site, d["label"], normalize="index") * 100).round(0)
    top = Counter({s: int(counts.get(s, 0)) for s in per_site.index if s != "other"}).most_common(3)
    ev = [{"kind": "row", "id": f"site {s}", "note": f"{n} samples; " +
           ", ".join(f"{lab} {int(per_site.loc[s, lab])}%" for lab in per_site.columns)} for s, n in top]
    base = (f"label vs tissue source site: Cramer's V = {v:.2f} over {site.nunique()} site groups "
            f"({len(d)} samples; sites under {CONFIG['site_min_samples']} pooled). Assumes the barcode's site code "
            "marks the submitting hospital")
    if v < lo:
        return CheckResult("site_confounding", "pass", base + f"; below {lo}, negligible", ev)
    if v < hi:
        return CheckResult("site_confounding", "fixable", base + f"; between {lo} and {hi}, a model could partly learn "
                           "the site", ev, fix="evaluate with whole sites held out, and report performance per site")
    return CheckResult("site_confounding", "fail", base + f"; {hi} or more, the label is largely predictable from the "
                       "site, which this data can't separate from biology", ev)


@register_check("event_count")
def event_count(card: QuestionCard, r: Release) -> CheckResult:
    """Survival questions: enough events (deaths) per group to compare, how long follow-up is, and redacted rows."""
    if not card.event or not r.has("survival.tsv"):
        return CheckResult("event_count", "unavailable", "no survival data for this question")
    ev_col, t_col = card.event
    d = _labelled(card, r)
    sv = r.table("survival.tsv")
    sv = sv.assign(_k=[norm_id(i) for i in sv.index]).drop_duplicates("_k").set_index("_k")
    d = d.assign(_k=d["sampleID"].map(norm_id)).join(sv[[ev_col, t_col] + (["Redaction"] if "Redaction" in sv else [])],
                                                     on="_k")
    d = d.dropna(subset=[ev_col, t_col])
    need = CONFIG["min_events_per_group"]
    per = d.groupby("label").agg(n=(ev_col, "size"), events=(ev_col, "sum"), months=(t_col, "median"))
    per["months"] = (per["months"] / 30.44).round(1)
    text = ", ".join(f"{k}: {int(v.events)} events of {int(v.n)}, median follow-up {v.months} mo" for k, v in per.iterrows())
    redacted = int((d.get("Redaction", "").astype(str) == "Redacted").sum()) if "Redaction" in d else 0
    ev = [{"kind": "row", "id": f"subtype {k}", "note": f"{int(v.events)} {ev_col} events, n={int(v.n)}"} for k, v in per.iterrows()]
    if redacted:
        ev.append({"kind": "file", "id": "survival.tsv",
                   "note": f"{redacted} row(s) marked Redaction = Redacted but kept, as the organizers advise; check them"})
    low = [k for k, v in per.iterrows() if v.events < need] + [k for k in card.label_values if k not in per.index]
    tail = f"; {redacted} redacted row(s) flagged for a person" if redacted else ""
    if low:
        return CheckResult("event_count", "insufficient",
                           f"fewer than {need} {ev_col} events for {', '.join(low)} ({text}){tail}", ev)
    return CheckResult("event_count", "pass", f"at least {need} {ev_col} events per group ({text}){tail}", ev)


@register_check("label_concordance")
def label_concordance(card: QuestionCard, r: Release) -> CheckResult:
    """Receptor labels that contradict the sample's own molecular data (see concordance.py). A mislabelled training
    sample teaches a model the wrong answer; in a descriptive comparison it sits in the wrong group."""
    from .concordance import ER_COL, HER2_COL, discordances
    marker = {ER_COL: "ER", HER2_COL: "HER2"}.get(card.label)
    if marker is None:
        return CheckResult("label_concordance", "skipped", f"no molecular cross-check is defined for {card.label}")
    elig = card.eligible(r)
    flagged = [d for d in discordances(r) if d.marker == marker and norm_id(d.sample) in elig]
    if not flagged:
        return CheckResult("label_concordance", "pass",
                           f"no {marker} label strongly contradicts its own molecular data among this question's samples")
    ev = [{"kind": "sample", "id": d.sample, "file": "clinical.tsv", "note": d.evidence} for d in flagged]
    return CheckResult("label_concordance", "fixable",
                       f"{len(flagged)} {marker} label(s) contradict the sample's own molecular data "
                       f"({', '.join(d.sample for d in flagged[:4])}{'…' if len(flagged) > 4 else ''})",
                       ev, fix=f"have the {marker} status of these samples re-checked, or leave them out until confirmed")
