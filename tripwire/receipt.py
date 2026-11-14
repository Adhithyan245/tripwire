"""Reproducibility receipt: anyone with the same two releases can re-check a Driftwire result with one command.

Every findings.json carries a `receipt`: the Driftwire version and git commit, the question asked, and a SHA-256 of
the result. The fingerprints of every input file are already in `data.releases`. `python -m driftwire verify`
checks the inputs against those fingerprints, re-runs the comparison, and reports one of three outcomes:

  identical         same inputs, same result hash
  same conclusions  the hash differs only through numeric noise; every verdict and finding is unchanged
  different         says exactly which inputs, verdicts or findings differ

Review decisions are left out of the hash, because they are a person's record added after the run.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess

from . import __version__

EXCLUDE = {"receipt", "decisions"}


def result_sha256(doc: dict) -> str:
    body = {k: v for k, v in doc.items() if k not in EXCLUDE}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                          .encode("utf-8")).hexdigest()


def _commit() -> str | None:
    root = pathlib.Path(__file__).resolve().parent.parent
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=5)
        return r.stdout.strip() or None if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def stamp(doc: dict, question: str | None) -> dict:
    doc["receipt"] = {
        "tool": f"Driftwire {__version__}",
        "commit": _commit(),
        "question": question,
        "inputs": "the sha256 of every input file is in data.releases",
        "result_sha256": result_sha256(doc),
        "verify": "python -m driftwire verify findings.json <trusted release> <new release>",
    }
    return doc


def conclusions(doc: dict) -> dict:
    """What a reader acts on: verdicts and what each finding says."""
    return {
        "verdict": doc.get("verdict"),
        "analyses": {a["id"]: a["verdict"] for a in doc.get("analyses", [])},
        "questions": {q["id"]: q["verdict"] for q in doc.get("questions", [])},
        "findings": [(f["id"], f["kind"], f["summary"]) for f in doc.get("findings", [])],
    }


def verify(recorded: dict, trusted: str, new: str) -> tuple[str, list[str]]:
    """Returns (outcome, details). outcome: identical | same conclusions | different | inputs differ."""
    from .detect import detect_changes
    from .findings import build
    from .release import Release

    rels = recorded.get("data", {}).get("releases", [])
    rec = recorded.get("receipt") or {}
    if len(rels) != 2 or "result_sha256" not in rec:
        return "different", ["this findings.json has no receipt or release fingerprints to check against"]
    a, b = Release(trusted, rels[0]["name"]), Release(new, rels[1]["name"])
    problems = []
    for side, rel, r in (("trusted", rels[0], a), ("new", rels[1], b)):
        how = "content" if any(f.get("hash_of") == "content" for f in rel["files"]) else "file"
        now = {f["file"]: f["sha256"] for f in r.fingerprints(how)}
        was = {f["file"]: f["sha256"] for f in rel["files"]}
        for name in sorted(set(was) | set(now)):
            if was.get(name) != now.get(name):
                problems.append(f"{side} release, {name}: "
                                + ("missing now" if name not in now else "not in the recorded run" if name not in was
                                   else "contents differ from the recorded fingerprint"))
    if problems:
        return "inputs differ", problems
    edited = result_sha256(recorded) != rec["result_sha256"]
    hash_of = ["content" if any(f.get("hash_of") == "content" for f in r["files"]) else "file" for r in rels]
    again = build(detect_changes(a, b), a, b, hash_of[0], hash_of[1], question=rec.get("question"))
    if result_sha256(again) == rec["result_sha256"] and not edited:
        return "identical", [f"result sha256 {rec['result_sha256'][:16]}... reproduced"]
    c1, c2 = conclusions(recorded), conclusions(again)
    if c1 == c2 and not edited:
        return "same conclusions", ["every verdict and finding is unchanged; only numeric detail differs "
                                    "(different machine, library or Driftwire version)"]
    diffs = ["this findings.json was edited after the run: its contents no longer match its own receipt"] if edited else []
    for key in ("verdict", "analyses", "questions"):
        if c1[key] != c2[key]:
            diffs.append(f"{key}: recorded {c1[key]}, now {c2[key]}")
    if c1["findings"] != c2["findings"]:
        was, now = {f[0]: f for f in c1["findings"]}, {f[0]: f for f in c2["findings"]}
        for fid in sorted(set(was) | set(now), key=lambda x: int(x[1:]) if x[1:].isdigit() else 0):
            if was.get(fid) != now.get(fid):
                diffs.append(f"{fid}: recorded {was.get(fid, ('-', '-', 'absent'))[2][:90]!r}, "
                             f"now {now.get(fid, ('-', '-', 'absent'))[2][:90]!r}")
    if rec.get("commit") and rec.get("commit") != _commit():
        diffs.append(f"recorded with Driftwire commit {rec['commit'][:10]}, re-run with {(_commit() or 'unknown')[:10]}")
    return "different", diffs
