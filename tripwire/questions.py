"""Question cards: a small, fixed set of supported research questions, each declaring its intended use, cohort,
label, inputs and required checks. The same release can get a different verdict for a different question, but only
through the rules written here. Thresholds are prototype policy choices, not clinical standards.

A card that asks for data the release doesn't have says so: "this data can't answer the question". Nothing is guessed.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from .analyses import ER_COL, PAM50_COL, is_primary
from .config import CONFIG, worst
from .contract import Change, norm_id
from .impact import touches
from .release import Release, content_sha256
from .verdicts import CheckResult, coverage, question_verdict

# Changes that corrupt which label or which profile belongs to a sample. For model training they block: the model
# would learn wrong labels, or copies would sit on both sides of a train/test split.
INTEGRITY_CHANGES = {"swap", "duplicate", "label_change", "sample_type_change"}


@dataclass
class QuestionCard:
    id: str
    title: str
    intended_use: str                  # "descriptive" | "model_training"
    label: str                         # clinical column
    label_values: tuple[str, ...]      # classes the question uses
    feature_files: list[str]           # molecular inputs (empty: clinical only)
    feature_fields: dict[str, set[str] | None] = field(default_factory=dict)  # None = every row of the file
    analysis_id: str | None = None     # reference analysis that computes this question, if any
    required_checks: list[str] = field(default_factory=lambda: ["sample_size"])
    acceptable_limitations: str = ""

    @property
    def files(self) -> list[str]:
        return ["clinical.tsv"] + self.feature_files

    @property
    def fields(self) -> dict[str, set[str] | None]:
        f = {"clinical.tsv": {"sampleID", self.label}}
        for name in self.feature_files:
            f[name] = self.feature_fields.get(name)
        return f

    @property
    def cohort(self) -> str:
        inputs = f" with data in {', '.join(self.feature_files)}" if self.feature_files else ""
        return f"primary tumors (code 01){inputs}, labelled {' / '.join(self.label_values)} in {self.label}"

    def eligible(self, r: Release) -> set[str]:
        ids = {norm_id(s) for s in r.clinical["sampleID"] if is_primary(s)}
        for name in self.feature_files:
            ids &= {norm_id(s) for s in r.sample_ids(name)}
        return ids


CARDS: list[QuestionCard] = [
    QuestionCard("er_protein_by_er_status", "Does ER-alpha protein differ between ER-positive and ER-negative tumors?",
                 "descriptive", ER_COL, ("Positive", "Negative"), ["protein_rppa.tsv.gz"],
                 {"protein_rppa.tsv.gz": {"ERALPHA"}}, analysis_id="A1",
                 acceptable_limitations="Group means can shift slightly; a small move within tolerance is acceptable."),
    QuestionCard("subtype_mix", "What is the PAM50 subtype mix of primary tumors?",
                 "descriptive", PAM50_COL, ("Basal", "Her2", "LumA", "LumB", "Normal"), [], analysis_id="A2",
                 acceptable_limitations="Shares can shift slightly; a small move within tolerance is acceptable."),
    QuestionCard("predict_er_from_protein", "Train a research model to predict ER status from protein (RPPA).",
                 "model_training", ER_COL, ("Positive", "Negative"), ["protein_rppa.tsv.gz"],
                 required_checks=["sample_size", "patient_leakage", "site_confounding"],
                 acceptable_limitations="None for label or profile integrity: every training sample must carry its own data."),
    QuestionCard("predict_subtype_from_copy_number", "Train a research model to predict PAM50 subtype from copy number.",
                 "model_training", PAM50_COL, ("Basal", "Her2", "LumA", "LumB", "Normal"), ["copy_number_gistic.tsv.gz"],
                 required_checks=["sample_size", "patient_leakage", "site_confounding"],
                 acceptable_limitations="None for label or profile integrity."),
    QuestionCard("predict_er_from_rna", "Train a research model to predict ER status from RNA expression.",
                 "model_training", ER_COL, ("Positive", "Negative"), ["rna_hiseq.tsv.gz"],
                 required_checks=["sample_size", "patient_leakage", "site_confounding"],
                 acceptable_limitations="None for label or profile integrity."),
]
BY_ID = {c.id: c for c in CARDS}

# ---------- readiness checks ----------
# Role 1 registers patient_leakage and site_confounding here. A required check that isn't registered is reported as
# "unavailable" and keeps the verdict at Insufficient Evidence; it is never treated as a pass.
CHECKS: dict[str, Callable[[QuestionCard, Release], CheckResult]] = {}


def register_check(name: str):
    def deco(fn):
        CHECKS[name] = fn
        return fn
    return deco


@register_check("sample_size")
def sample_size(card: QuestionCard, r: Release) -> CheckResult:
    counts = labelled_counts(card, r)
    need = CONFIG["min_samples_per_group"]
    per = ", ".join(f"{v}: {counts.get(v, 0)}" for v in card.label_values)
    low = [v for v in card.label_values if counts.get(v, 0) < need]
    if low:
        return CheckResult("sample_size", "insufficient", f"fewer than {need} labelled samples for {', '.join(low)} ({per})")
    return CheckResult("sample_size", "pass", f"at least {need} labelled samples per class ({per})")


def labelled_counts(card: QuestionCard, r: Release) -> Counter:
    elig = card.eligible(r)
    c = r.clinical
    lab = c[c["sampleID"].map(norm_id).isin(elig)][card.label]
    return Counter(v for v in lab if v in card.label_values)


# ---------- validation ----------

def problems(card: QuestionCard, r: Release) -> list[dict]:
    out = []
    for name in card.files:
        if not r.has(name):
            out.append({"kind": "unavailable", "text": f"{name} is not in release {r.name}"})
    if out:
        return out
    if card.label not in r.clinical.columns:
        out.append({"kind": "missing_field", "text": f"clinical.tsv has no column {card.label}"})
    for name, rows in card.fields.items():
        if name != "clinical.tsv" and rows:
            missing = sorted(set(rows) - set(r.table(name).index))
            if missing:
                out.append({"kind": "missing_field", "text": f"{name} has no row(s) {', '.join(missing)}"})
    if not out and not card.eligible(r):
        out.append({"kind": "empty_cohort", "text": f"no samples match the cohort: {card.cohort}"})
    return out


def _inputs_equal(card: QuestionCard, a: Release, b: Release) -> bool:
    """Do the data this card reads match between releases, ignoring row and column order?"""
    if all(content_sha256(a.path / f) == content_sha256(b.path / f) for f in card.files):
        return True  # identical files (line endings aside): nothing to compare
    ids = card.eligible(a) | card.eligible(b)

    def lab(r):
        c = r.clinical.assign(_k=r.clinical["sampleID"].map(norm_id))
        return c[c._k.isin(ids)].set_index("_k")[card.label].astype(str).sort_index()

    if not lab(a).equals(lab(b)):
        return False
    for name in card.feature_files:
        rows = card.fields[name]

        def sub(r):
            t = r.table(name)
            t = t[[s for s in t.columns if norm_id(s) in ids]]
            if rows:
                t = t.loc[sorted(rows & set(t.index))]
            t = t.rename(columns=norm_id)
            return t.sort_index().sort_index(axis=1)

        x, y = sub(a), sub(b)
        if list(x.columns) != list(y.columns) or list(x.index) != list(y.index):
            return False
        try:
            same = np.array_equal(x.to_numpy(float), y.to_numpy(float), equal_nan=True)
        except (TypeError, ValueError):  # non-numeric cells
            same = x.astype(str).equals(y.astype(str))
        if not same:
            return False
    return True


# ---------- assessment ----------

def assess(card: QuestionCard, changes: list[Change], a: Release, b: Release, analyses: dict[str, dict]) -> dict:
    """analyses: findings.json analyses entries by id (for cards backed by a reference analysis)."""
    out = {"id": card.id, "title": card.title, "intended_use": card.intended_use, "cohort": card.cohort,
           "inputs": card.files, "label": card.label, "acceptable_limitations": card.acceptable_limitations,
           "required_checks": card.required_checks}
    probs = problems(card, b) or problems(card, a)
    if probs:
        checks = [CheckResult(n, "unavailable", "inputs missing") for n in card.required_checks]
        out.update(problems=probs, verdict="Insufficient Evidence", relevant_changes=[],
                   why="This data can't answer the question: " + "; ".join(p["text"] for p in probs) + ".",
                   release_part={"verdict": "Insufficient Evidence", "why": "inputs missing"},
                   checks=[_check_dict(c) for c in checks], coverage=coverage(checks, card.required_checks))
        return out

    eligible = card.eligible(a) | card.eligible(b)
    touched = [i for i, ch in enumerate(changes) if touches(ch, card, eligible)[0]]
    kinds = sorted({changes[i].change_type for i in touched})

    if card.analysis_id and card.analysis_id in analyses:
        an = analyses[card.analysis_id]
        rel = {"verdict": an["verdict"], "why": f"Computed by {card.analysis_id}: {an['why']}"}
    elif touched and set(kinds) & INTEGRITY_CHANGES:
        rel = {"verdict": "Blocked", "why": f"{len(touched)} detected change(s) touch this question's inputs, including "
               f"{', '.join(sorted(set(kinds) & INTEGRITY_CHANGES))}. For model training that means wrong labels or "
               "copies across a train/test split; a curator must review them first."}
    elif touched:
        rel = {"verdict": "Conditional", "why": f"{len(touched)} detected change(s) touch this question's inputs "
               f"({', '.join(kinds)}); none corrupt labels or profiles, but the training set differs from release {a.name}."}
    elif not _inputs_equal(card, a, b):
        rel = {"verdict": "Blocked", "why": "The data this question reads changed between releases, but no detected "
               "change explains it. Hold until a curator finds what changed."}
    else:
        rel = {"verdict": "Ready", "why": "Nothing this question reads changed between releases."}

    checks = []
    for name in card.required_checks:
        fn = CHECKS.get(name)
        checks.append(fn(card, b) if fn else CheckResult(name, "unavailable", "check not built yet"))
    qv = question_verdict(checks, card.required_checks)
    verdict = worst([rel["verdict"], qv.verdict])
    why = rel["why"] if verdict == rel["verdict"] else qv.reason
    out.update(problems=[], verdict=verdict, why=why, relevant_changes=touched, release_part=rel,
               checks=[_check_dict(c) for c in checks], coverage=coverage(checks, card.required_checks))
    return out


def _check_dict(c: CheckResult) -> dict:
    d = {"name": c.name, "status": c.status, "summary": c.summary}
    if c.evidence:
        d["evidence"] = c.evidence
    if c.fix:
        d["fix"] = c.fix
    return d


# Built-in readiness checks register themselves on import.
from . import checks as _checks  # noqa: E402,F401
