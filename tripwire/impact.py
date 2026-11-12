"""Impact map: which analyses does each detected change touch, and why are the others left alone?

A change touches an analysis when all three hold:
  1. the analysis reads the changed file,
  2. the changed fields are ones it reads (or the whole sample profile changed),
  3. the changed sample could be in its cohort, in release A or B.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .analyses import ANALYSES, Analysis
from .contract import Change, norm_id
from .release import Release


@dataclass
class Impact:
    analysis: Analysis
    touched_by: list[int] = field(default_factory=list)      # indices into the change list
    skipped: Counter = field(default_factory=Counter)        # reason -> number of changes

    @property
    def affected(self) -> bool:
        return bool(self.touched_by)

    def why(self, n_changes: int) -> str:
        a = self.analysis
        if self.affected:
            return (f"{len(self.touched_by)} of {n_changes} detected changes touch what {a.id} reads "
                    f"({', '.join(a.files)}; cohort: {a.cohort}).")
        if not n_changes:
            return f"No detected changes. {a.id} reads {', '.join(a.files)}."
        parts = [f"{n} {reason}" for reason, n in self.skipped.most_common()]
        return f"None of the {n_changes} detected changes touch {a.id}: " + "; ".join(parts) + "."


def _ids(ch: Change) -> set[str]:
    ids = {ch.sample_id, ch.related_sample_id}
    for v in (ch.before, ch.after):  # sample_type / id changes carry the other form of the ID
        if isinstance(v, str) and v.upper().startswith("TCGA-"):
            ids.add(v)
    return {norm_id(i) for i in ids if i}


def touches(ch: Change, a: Analysis, eligible: set[str]) -> tuple[bool, str]:
    if ch.file not in a.files:
        return False, f"in a file it doesn't read ({ch.file})"
    used = a.fields.get(ch.file, set())
    if ch.fields and not (set(ch.fields) & used):
        return False, f"change fields it doesn't use ({ch.file}: {', '.join(sorted(ch.fields))[:80]})"
    if not (_ids(ch) & eligible):
        return False, "are samples outside its cohort"
    return True, ""


def map_impact(changes: list[Change], release_a: Release, release_b: Release,
               analyses: list[Analysis] = ANALYSES) -> dict[str, Impact]:
    out = {}
    for a in analyses:
        eligible = a.eligible(release_a) | a.eligible(release_b)
        imp = Impact(a)
        for i, ch in enumerate(changes):
            hit, reason = touches(ch, a, eligible)
            if hit:
                imp.touched_by.append(i)
            else:
                imp.skipped[reason] += 1
        out[a.id] = imp
    return out
