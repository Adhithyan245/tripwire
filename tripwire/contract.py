"""The shared change contract (docs/CONTRACT.md). Detector writes these, Mutation Lab uses them as its answer key,
the findings layer turns them into findings.json."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

CHANGE_TYPES = {
    "swap": "sample_swap",
    "duplicate": "duplicate",
    "appeared": "membership_change",
    "disappeared": "membership_change",
    "label_change": "label_conflict",
    "sample_type_change": "label_conflict",
    "id_format_change": "other",
    "value_shift": "other",
    "coverage_loss": "missing_data",
}


@dataclass
class Change:
    sample_id: str
    change_type: str
    file: str
    fields: list[str] = field(default_factory=list)  # empty = whole sample profile
    evidence: str = ""
    before: Any = None
    after: Any = None
    related_sample_id: str | None = None  # optional, proposed: swap partner or duplicate source

    def __post_init__(self):
        if self.change_type not in CHANGE_TYPES:
            raise ValueError(f"unknown change_type {self.change_type!r}; allowed: {sorted(CHANGE_TYPES)}")

    @property
    def finding_kind(self) -> str:
        return CHANGE_TYPES[self.change_type]

    def to_dict(self) -> dict:
        d = asdict(self)
        if d["related_sample_id"] is None:
            d.pop("related_sample_id")
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Change":
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**known)


def load_changes(path) -> list[Change]:
    data = json.load(open(path))
    if isinstance(data, dict):
        data = data.get("changes", [])
    return [Change.from_dict(d) for d in data]


def norm_id(sample_id: str) -> str:
    """Comparison key only. Never used to rewrite IDs in output."""
    return str(sample_id).strip().upper()
