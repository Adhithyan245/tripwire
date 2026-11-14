"""Run the organizers' validator (challenge repo format/validate.py) on a findings document."""
from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import tempfile

HERE = pathlib.Path(__file__).resolve().parent.parent
CANDIDATES = ["oncosys-challenge", "oncosys-hackathon-challenge"]


def challenge_dir(explicit: str | None = None) -> pathlib.Path | None:
    for p in [explicit, os.environ.get("TRIPWIRE_CHALLENGE_DIR")] + [str(HERE.parent / c) for c in CANDIDATES]:
        if p and (pathlib.Path(p) / "format" / "validate.py").exists():
            return pathlib.Path(p)
    return None


def validate(doc: dict, challenge: str | None = None) -> list[str]:
    root = challenge_dir(challenge)
    if root is None:
        raise FileNotFoundError("challenge repo not found; clone it next to this repo or set TRIPWIRE_CHALLENGE_DIR")
    spec = importlib.util.spec_from_file_location("_oncosys_validate", root / "format" / "validate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(doc, f)
    try:
        return mod.check(f.name)
    finally:
        os.unlink(f.name)
