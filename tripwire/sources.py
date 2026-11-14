"""Source links for evidence: each cited sample gets its tissue slide in NCI Imaging Data Commons' public viewer.

The shared format suggests evidence pointers carry a viewer `url` so a reviewer can find the record. The links come
from the organizers' slide_manifest.csv (public IDC viewer, CC BY 3.0); nothing is downloaded. A diagnostic (FFPE)
slide is preferred, then a frozen section.
"""
from __future__ import annotations

import csv
from functools import lru_cache

from .contract import norm_id
from .validate import challenge_dir

PREFER = ("diagnostic (FFPE)", "frozen, top section", "frozen, middle section", "frozen, bottom section")


@lru_cache(maxsize=1)
def _slides() -> dict[str, str]:
    root = challenge_dir()
    path = root / "data" / "tcga-brca" / "slide_manifest.csv" if root else None
    if not path or not path.exists():
        return {}
    best: dict[str, tuple[int, str]] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            url, kind = row.get("viewer_url"), row.get("slide_kind", "")
            if not url:
                continue
            rank = PREFER.index(kind) if kind in PREFER else len(PREFER)
            k = norm_id(row.get("sample_id", ""))
            if k and (k not in best or rank < best[k][0]):
                best[k] = (rank, url)
    return {k: u for k, (_, u) in best.items()}


def slide_url(sample_id: str) -> str | None:
    return _slides().get(norm_id(sample_id))


def add_slide_links(doc: dict) -> int:
    """Add `url` to every sample evidence pointer and repair target that has a slide. Returns how many were added."""
    n = 0
    refs = [e for f in doc.get("findings", []) for e in f.get("evidence", [])]
    refs += [t for r in doc.get("repairs", []) for t in r.get("targets", [])]
    for ref in refs:
        if ref.get("kind") == "sample" and not ref.get("url"):
            url = slide_url(ref.get("id", ""))
            if url:
                ref["url"] = url
                n += 1
    return n
