"""Turn changes + impact + reruns into findings.json (shared format v0.2). Repairs are proposals only."""
from __future__ import annotations

from collections import Counter, defaultdict

from . import __version__
from .analyses import ANALYSES, ER_COL, PAM50_COL, public, slice_diff
from .config import CONFIG, worst
from .contract import Change, norm_id
from .impact import map_impact
from .release import Release
from .verdicts import release_verdict

FEATURE_KIND = {"protein_rppa.tsv.gz": "protein", "mutation_gene_level.tsv.gz": "gene",
                "copy_number_gistic.tsv.gz": "gene", "rna_hiseq.tsv.gz": "gene"}

BASE_SEVERITY = {"swap": "high", "duplicate": "high", "label_change": "high", "sample_type_change": "high",
                 "appeared": "medium", "disappeared": "medium", "value_shift": "medium",
                 "coverage_loss": "medium", "id_format_change": "low"}

LIMITATION = {
    "swap": "A swap is inferred from two profiles trading places between releases; the release doesn't say why.",
    "duplicate": "Identical or near-identical profiles strongly suggest copies, not new measurements.",
    "appeared": "New samples may be legitimate additions; Tripwire can't tell additions from substitutions on its own.",
    "disappeared": "A dropped sample may be a deliberate withdrawal; ask the data provider.",
    "label_change": "Tripwire sees that the value changed, not which value is correct.",
    "sample_type_change": "The sample-type code changed, which moves the sample in or out of primary-tumor cohorts.",
    "id_format_change": "Same sample under a reformatted ID; exact-match joins will silently drop it.",
    "value_shift": "Values moved without a swap or copy; could be a unit or normalisation change.",
    "coverage_loss": "Coverage dropped for a subgroup; per-subgroup results using this file are affected.",
}

REPAIR = {
    "swap": ("restore_from_previous_release", "A", "Restore both profiles as they were in {A} until the swap is explained."),
    "duplicate": ("exclude", "B", "Exclude the duplicated profiles from analyses that read {file}."),
    "appeared": ("flag_for_review", "B", "Confirm with the data provider that these samples are genuine additions."),
    "disappeared": ("flag_for_review", "A", "Ask the data provider why these samples lost data in {file}."),
    "label_change": ("restore_from_previous_release", "A", "Keep the {A} values until the change is confirmed."),
    "sample_type_change": ("restore_from_previous_release", "A", "Keep the {A} sample-type codes until the change is confirmed."),
    "id_format_change": ("relabel", "B", "Map the reformatted IDs back to their {A} form."),
    "value_shift": ("flag_for_review", "B", "Check units and normalisation of {file} for these samples."),
    "coverage_loss": ("flag_for_review", "A", "Ask the data provider why this subgroup lost coverage in {file}."),
}


def _group(changes: list[Change]) -> list[list[int]]:
    """Swaps: one finding per pair. Everything else: one finding per (type, file)."""
    by_key: dict[tuple, list[int]] = defaultdict(list)  # insertion-ordered
    for i, ch in enumerate(changes):
        key = (ch.change_type, ch.file)
        if ch.change_type == "swap":
            key += (frozenset({norm_id(ch.sample_id), norm_id(ch.related_sample_id or ch.sample_id)}),)
        by_key[key].append(i)
    return list(by_key.values())


def _subgroups(ids, clinical) -> str:
    """'4 of 5 Her2; ER: 3 Positive, 2 Negative' from release A clinical labels."""
    c = clinical.assign(_k=clinical["sampleID"].map(norm_id)).set_index("_k")
    keys = [norm_id(i) for i in ids if norm_id(i) in c.index]
    if not keys:
        return ""
    bits = []
    for col, label in ((PAM50_COL, "subtype"), (ER_COL, "ER")):
        if col in c.columns:
            vals = Counter(str(v) for v in c.loc[keys, col] if isinstance(v, str) and v)
            if vals:
                bits.append(f"{label}: " + ", ".join(f"{n} {v}" for v, n in vals.most_common()))
    return "; ".join(bits)


def _summary(kind: str, chs: list[Change], file: str, sub: str, count_note: str) -> str:
    n = len(chs)
    ids = sorted({c.sample_id for c in chs})
    s = {
        "swap": lambda: f"Profiles of {chs[0].sample_id} and {chs[0].related_sample_id or '?'} in {file} appear exchanged between releases.",
        "duplicate": lambda: f"{n} sample(s) in {file} carry profiles identical or near-identical to other samples.",
        "appeared": lambda: f"{n} sample(s) appear in {file} that were not in the previous release.",
        "disappeared": lambda: f"{n} sample(s) lost their data in {file}.",
        "label_change": lambda: f"{n} sample(s) changed value in {file} ({', '.join(sorted({f for c in chs for f in c.fields}))[:120]}).",
        "sample_type_change": lambda: f"{n} sample(s) changed sample-type code in {file}.",
        "id_format_change": lambda: f"{n} sample ID(s) in {file} changed case or whitespace.",
        "value_shift": lambda: f"{n} sample(s) in {file} changed values without a swap or copy.",
        "coverage_loss": lambda: f"Missing data rose for a subgroup in {file} ({n} sample(s)).",
    }[kind]()
    if sub and kind == "duplicate" and sub.startswith("copied"):
        s += f" By release-A labels: {sub}."
    elif sub:
        s += f" Affected samples by release-A labels: {sub}."
    if count_note:
        s += f" {count_note}"
    if kind != "swap" and n <= 6:
        s += f" Samples: {', '.join(ids)}."
    return s


def _ref(ch: Change, release_name: str, note: str | None = None) -> dict:
    r = {"kind": "sample", "id": ch.sample_id, "release": release_name, "file": ch.file}
    if note:
        r["note"] = note[:300]
    return r


def build(changes: list[Change], release_a: Release, release_b: Release,
          hash_a: str = "file", hash_b: str = "content", verify_unaffected: bool | None = None,
          question: str | None = None) -> dict:
    """question: a question-card id. When given, the top-level question and verdict are that card's.
    Every supported card is always assessed and listed under "questions"."""
    from .questions import BY_ID, CARDS, assess
    if question is not None and question not in BY_ID:
        raise ValueError(f"unknown question card {question!r}; supported: {', '.join(BY_ID)}")
    verify = CONFIG["verify_unaffected"] if verify_unaffected is None else verify_unaffected
    change_finding: dict[int, str] = {}
    A, B = release_a.name, release_b.name
    impacts = map_impact(changes, release_a, release_b)

    # ---- reruns + verdicts
    analyses_out, verdicts, unexplained = [], {}, []
    for a in ANALYSES:
        imp = impacts[a.id]
        rerun = imp.affected or verify
        if not all(release_a.has(f) and release_b.has(f) for f in a.files):
            analyses_out.append({"id": a.id, "status": "not_rerun", "verdict": "Insufficient Evidence",
                                 "why": f"Missing input file(s): {a.files}", "title": a.title})
            verdicts[a.id] = "Insufficient Evidence"
            continue
        before = after = mv = sd = None
        if rerun:
            before, after = a.run(release_a), a.run(release_b)
            mv = a.compare(before, after)
            sd = slice_diff(a.slice(release_a), a.slice(release_b))
        v = release_verdict(imp.affected, mv, sd)
        verdicts[a.id] = v.verdict
        if mv is not None and not imp.affected and (mv.moved or sd.any):
            unexplained.append((a, mv, sd))
        entry = {"id": a.id, "status": "not_rerun" if mv is None else ("changed" if mv.moved else "unchanged"),
                 "title": a.title, "verdict": v.verdict, "why": v.reason, "impact": imp.why(len(changes)),
                 "inputs": a.files, "cohort": a.cohort}
        if mv is not None:
            entry["before"], entry["after"] = public(before), public(after)
            entry["rerun_reason"] = "affected by detected changes" if imp.affected else \
                "verification rerun: the impact map said unaffected"
            entry["input_changes"] = sd.counts()  # sample by sample, exactly what it reads
        analyses_out.append(entry)

    # ---- findings + repairs
    findings, repairs = [], []
    a_count = {f: _count(release_a, f) for f in {c.file for c in changes}}
    b_count = {f: _count(release_b, f) for f in {c.file for c in changes}}
    for idx in _group(changes):
        chs = [changes[i] for i in idx]
        ch0, kind, file = chs[0], chs[0].change_type, chs[0].file
        fid = f"F{len(findings) + 1}"
        change_finding.update({i: fid for i in idx})
        affects = sorted({aid for aid, imp in impacts.items() if set(idx) & set(imp.touched_by)})
        not_aff = sorted(set(impacts) - set(affects))
        ids = {c.sample_id for c in chs} | {c.related_sample_id for c in chs if c.related_sample_id}
        sub = ""
        if release_a.has("clinical.tsv"):
            if kind == "duplicate" and any(c.related_sample_id for c in chs):
                src = _subgroups({c.related_sample_id for c in chs if c.related_sample_id}, release_a.clinical)
                own = _subgroups({c.sample_id for c in chs}, release_a.clinical)
                sub = f"copied from samples labelled {src}" + (f"; the copies sit under IDs labelled {own}" if own else "")
            else:
                sub = _subgroups(ids, release_a.clinical)
        count_note = ""
        if kind in ("appeared", "disappeared") and a_count.get(file) is not None and a_count.get(file) == b_count.get(file):
            count_note = f"The total sample count in {file} is unchanged ({a_count[file]}), so a count check would miss this."
        side = A if kind in ("disappeared", "coverage_loss") else B
        evidence = []
        for c in chs:
            evidence.append(_ref(c, side, c.evidence or None))
            if c.related_sample_id and kind == "swap":
                evidence.append({"kind": "sample", "id": c.related_sample_id, "release": B, "file": file})
        fk = FEATURE_KIND.get(file)
        for f in sorted({f for c in chs for f in c.fields})[:20]:
            evidence.append({"kind": fk, "id": f} if fk else {"kind": "file", "id": file, "note": f"column {f}"})
        evidence = _dedupe(evidence)
        severity = BASE_SEVERITY[kind] if affects else "low"  # provisional; _rate_severity sets the final value
        findings.append({
            "id": fid, "kind": ch0.finding_kind, "summary": _summary(kind, chs, file, sub, count_note),
            "severity": severity, "confidence": "high" if kind != "value_shift" else "medium",
            "evidence": evidence, "affects_analyses": affects, "not_affected_analyses": not_aff,
            "limitation": LIMITATION[kind], "needs_human_review": True,
        })
        action, rside, just = REPAIR[kind]
        rname = A if rside == "A" else B
        targets = _dedupe([{"kind": "sample", "id": i, "release": rname, "file": file} for i in sorted(ids)])
        repairs.append({"id": f"R{len(repairs) + 1}", "action": action, "targets": targets,
                        "justification": just.format(A=A, file=file) + " Proposed only; never applied automatically.",
                        "addresses": [fid]})

    unexplained_finding: dict[str, str] = {}
    for a, mv, sd in unexplained:
        fid = f"F{len(findings) + 1}"
        unexplained_finding[a.id] = fid
        moved = f"moved between releases ({mv.magnitude})" if mv.moved else "didn't move, but its inputs changed"
        ev = [{"kind": "analysis", "id": a.id, "note": f"inputs: {', '.join(a.files)}"}]
        ev += [{"kind": "sample", "id": s, "release": B, "note": "entered the data this analysis reads"} for s in sd.added]
        ev += [{"kind": "sample", "id": s, "release": A, "note": "left the data this analysis reads"} for s in sd.removed]
        ev += [{"kind": "sample", "id": s, "release": B, "note": f"{x} -> {y}"} for s, x, y in sd.changed]
        findings.append({
            "id": fid, "kind": "other",
            "summary": f"{a.id} ({a.title}) {moved}, and no detected change explains it. Sample by sample, the data it "
                       f"reads changed for {len(sd.added) + len(sd.removed) + len(sd.changed)} sample(s): "
                       f"{len(sd.added)} entered, {len(sd.removed)} left, {len(sd.changed)} with different values; "
                       f"{sd.identical} are identical.",
            "severity": "high", "confidence": "high",
            "evidence": ev,
            "affects_analyses": [a.id], "not_affected_analyses": sorted(set(impacts) - {a.id}),
            "limitation": "Caught by Tripwire's own check of what each analysis reads, not by the detector: every "
                          "changed sample is listed, but the kind of change (swap, copy, relabel) isn't classified.",
            "needs_human_review": True,
        })
        repairs.append({"id": f"R{len(repairs) + 1}", "action": "flag_for_review",
                        "targets": [{"kind": "analysis", "id": a.id}],
                        "justification": f"Hold {a.id} results until a curator finds what changed in {', '.join(a.files)}. "
                                         "Proposed only; never applied automatically.", "addresses": [fid]})

    # ---- question cards: same release, a verdict per supported question
    by_analysis = {x["id"]: x for x in analyses_out}
    questions = []
    for card in CARDS:
        q = assess(card, changes, release_a, release_b, by_analysis)
        rel = {change_finding[i] for i in q.pop("relevant_changes") if i in change_finding}
        if card.analysis_id in unexplained_finding:
            rel.add(unexplained_finding[card.analysis_id])
        q["relevant_findings"] = sorted(rel, key=lambda f: int(f[1:]))
        questions.append(q)
    for f in findings:
        f["relevant_questions"] = [q["id"] for q in questions if f["id"] in q["relevant_findings"]]
        _rate_severity(f, by_analysis, {q["id"]: q for q in questions})

    names = " and ".join(f"{a.id} ({a.title})" for a in ANALYSES)
    top_q = f"Did release {B} change anything that affects analyses {names}?"
    top_v = worst(verdicts.values())
    if question is not None:
        card_q = next(q for q in questions if q["id"] == question)
        top_q = f"Given release {B}: {card_q['title']} (intended use: {card_q['intended_use']})"
        top_v = card_q["verdict"]
    return {
        "format_version": "0.2",
        "producer": {"team": CONFIG["producer_team"], "product": "Cohort Control Tower", "track": "cohort-firewall",
                     "tool": f"Tripwire {__version__}"},
        "data": {"dataset": "TCGA-BRCA", "releases": [
            {"name": A, "files": release_a.fingerprints(hash_a)},
            {"name": B, "files": release_b.fingerprints(hash_b)}]},
        "question": top_q,
        "verdict": top_v,
        "findings": findings,
        "analyses": analyses_out,
        "repairs": repairs,
        "questions": questions,
        "settings": {k: v for k, v in CONFIG.items() if k != "producer_team"},
        "research_use_only": "Research output. Not a diagnosis, treatment advice, risk score or clinical claim.",
    }


def _rate_severity(f: dict, analyses: dict, questions: dict) -> None:
    """Severity = how much the change could move a research answer, with the reason written down.

    Uses the verdicts of the analyses it touches and the release part of the questions it touches (not check gaps).
    Those verdicts reflect all changes together, so the reason says "overall"."""
    hits = [(aid, analyses[aid]["verdict"]) for aid in f.get("affects_analyses", []) if aid in analyses]
    hits += [(qid, questions[qid]["release_part"]["verdict"]) for qid in f.get("relevant_questions", []) if qid in questions]
    blocked = [n for n, v in hits if v == "Blocked"]
    shaky = [n for n, v in hits if v in ("Conditional", "Insufficient Evidence")]
    if blocked:
        f["severity"] = "high"
        f["severity_reason"] = f"It feeds results that are Blocked overall: {', '.join(blocked)}."
    elif shaky:
        f["severity"] = "medium"
        f["severity_reason"] = (f"It changes inputs of {', '.join(shaky)}; those results stay within tolerance "
                                "or lose samples, but aren't blocked.")
    elif hits:
        f["severity"] = "low"
        f["severity_reason"] = f"It touches {', '.join(n for n, _ in hits)}, but none of their answers moved."
    else:
        f["severity"] = "low"
        f["severity_reason"] = "It touches no reference analysis or supported research question."


def _count(r: Release, file: str):
    try:
        if file == "clinical.tsv":
            return int(len(r.clinical))
        if file == "protein_rppa.tsv.gz":
            return int(r.protein.shape[1])
    except FileNotFoundError:
        return None
    return None


def _dedupe(refs: list[dict]) -> list[dict]:
    seen, out = set(), []
    for r in refs:
        k = (r.get("kind"), r.get("id"), r.get("release"), r.get("file"))
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out
