"""What to do next, and what Driftwire can't tell you: a short, ordered plan built only from findings.json content.

The organizers' brief for Saturday: every working Control Tower finds the same changes, so show why they matter, what
the user should do next, and what the tool can't tell them. Every step here cites the finding, repair or question it
comes from, and its effect is taken from the repair preview, never guessed.
"""
from __future__ import annotations

SEV_RANK = {"high": 0, "medium": 1, "low": 2, "none": 3}
WHO = {"restore_from_previous_release": "Curator", "exclude": "Curator", "relabel": "Curator",
       "flag_for_review": "Data provider", "other": "Curator"}


def _effect(preview: dict) -> str:
    rows = preview.get("analyses") or []
    bits = []
    for x in rows:
        now, then = x.get("verdict_now"), x.get("verdict_if_approved")
        moved = x.get("summary", "").split("if approved ")[-1].split(", vs release")[0]
        bits.append(f"{x['analysis']} {now} → {then} ({moved})" if now and now != then else f"{x['analysis']}: {moved}")
    return "; ".join(bits)


def build_plan(doc: dict) -> dict:
    findings = {f["id"]: f for f in doc.get("findings", [])}
    steps = []

    # 1. decide on each proposed repair, most serious finding first
    for r in doc.get("repairs", []):
        fs = [findings[i] for i in r.get("addresses", []) if i in findings]
        rank = min((SEV_RANK.get(f.get("severity"), 3) for f in fs), default=3)
        targets = [t["id"] for t in r.get("targets", []) if t.get("kind") == "sample"]
        who = WHO.get(r["action"], "Curator")
        if r["action"] == "flag_for_review":
            what = fs[0]["summary"].split(". ")[0].rstrip(".") if fs else f"{len(targets)} sample(s) changed"
            action = f"Ask the data provider to explain: {what}"
        else:
            verb = {"restore_from_previous_release": "Approve or reject restoring", "exclude": "Approve or reject excluding",
                    "relabel": "Approve or reject relabelling"}.get(r["action"], "Decide on")
            action = f"{verb} {len(targets)} sample(s) ({', '.join(targets[:3])}{'…' if len(targets) > 3 else ''})"
        why = "; ".join(f["summary"].split(". ")[0] for f in fs)[:300]
        if r["action"] == "flag_for_review":
            hit = sorted({a for f in fs for a in f.get("affects_analyses", [])})
            verdicts = {a["id"]: a.get("verdict") for a in doc.get("analyses", [])}
            blocked = [a for a in hit if verdicts.get(a) == "Blocked"]
            usable = [a for a in hit if a not in blocked]
            bits = []
            if blocked:
                bits.append(f"keep {', '.join(blocked)} on hold (Blocked)")
            if usable:
                bits.append(f"{', '.join(usable)} can be used with care ({'/'.join(sorted({verdicts.get(a) or 'Conditional' for a in usable}))}), "
                            "but don't build new work on these samples")
            why = ("Until it's explained, " + "; ".join(bits) + "." if bits else
                   "Until it's explained, don't build new work on these samples.")
        steps.append({"rank": rank, "who": who, "action": action, "why": why,
                      "effect": _effect(r.get("preview") or {}) or None,
                      "refs": [r["id"]] + r.get("addresses", [])})

    # 2. what all approvals together would achieve
    allp = doc.get("repair_preview_all") or {}
    together = "; ".join(x["summary"].replace(" vs release", " against release") for x in allp.get("analyses", []))

    # 3. research questions that need work before use
    for q in doc.get("questions", []):
        if q.get("verdict") in ("Ready",):
            continue
        fixes = [c["fix"] for c in q.get("checks", []) if c.get("fix")]
        if q.get("verdict") == "Insufficient Evidence" and not fixes:
            steps.append({"rank": 4, "who": "Researcher", "action": f"Don't use this release for: {q['title']}",
                          "why": q.get("why", ""), "effect": None, "refs": [q["id"]]})
        elif q.get("verdict") == "Blocked":
            steps.append({"rank": 1, "who": "Researcher", "action": f"Hold: {q['title']}",
                          "why": q.get("why", ""), "effect": "; ".join(fixes) or None, "refs": [q["id"]]})
        elif fixes:
            steps.append({"rank": 3, "who": "Researcher", "action": f"Before: {q['title']} " + "; ".join(fixes),
                          "why": q.get("why", ""), "effect": None, "refs": [q["id"]]})

    steps.sort(key=lambda s: s["rank"])
    for i, s in enumerate(steps, 1):
        s["step"] = i
        s.pop("rank")
    if not steps:
        steps = [{"step": 1, "who": "Researcher", "action": "No action needed for the supported analyses and questions",
                  "why": "Nothing they depend on changed.", "effect": None, "refs": []}]

    cannot = [
        "Why a change happened. Driftwire sees that profiles moved or were copied, not the cause; the data provider "
        "has to say.",
        "Errors already present in release A. A comparison only sees what differs between the two releases.",
        "Which of two conflicting values is correct (a relabel shows the old and the new value, not the truth).",
    ]
    gaps = sorted({c for q in doc.get("questions", []) if not q.get("problems")  # skip questions the data can't answer
                   for k in ("unavailable", "missing") for c in q.get("coverage", {}).get(k, [])})
    if gaps:
        cannot.append(f"Anything that needs a check that couldn't run here: {', '.join(gaps)}.")
    if any(f.get("kind") == "other" for f in doc.get("findings", [])):
        cannot.append("What exactly caused an unexplained change: an analysis moved without a detected change behind "
                      "it, so a curator has to look at the listed samples.")
    return {"steps": steps, "all_repairs_together": together or None, "cannot_tell": cannot}
