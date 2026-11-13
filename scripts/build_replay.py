"""Build the data file for the replay page (site/) from a real Tripwire run.

    python scripts/build_replay.py <release A> <release B> --out site/data/practice.replay.json

The file is Tripwire's own findings.json plus a small "replay" block: how many samples each file holds in each
release, so the page can draw every sample and show which ones tripped the wire. Nothing is invented: every number
the page shows comes from this file.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from tripwire.contract import norm_id  # noqa: E402
from tripwire.detect import ROW_FILES, detect_changes  # noqa: E402
from tripwire.findings import build  # noqa: E402
from tripwire.release import Release  # noqa: E402


def _ids(r: Release, name: str) -> list[str]:
    if name in ROW_FILES:
        t = r.table(name)
        col = ROW_FILES[name]
        return list(t[col]) if col in t.columns else list(t.index)
    return r.sample_ids(name)


def replay_block(a: Release, b: Release, seconds: float) -> dict:
    files = []
    for name in sorted(set(a.files) | set(b.files)):
        ia = {norm_id(i) for i in _ids(a, name)} if a.has(name) else set()
        ib = {norm_id(i) for i in _ids(b, name)} if b.has(name) else set()
        files.append({"file": name, "n_a": len(ia), "n_b": len(ib), "in_b": b.has(name)})
    return {"files": files, "seconds": round(seconds, 1),
            "generated_by": "scripts/build_replay.py", "release_a": a.name, "release_b": b.name}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("release_a")
    p.add_argument("release_b")
    p.add_argument("--name-a")
    p.add_argument("--name-b")
    p.add_argument("--out", required=True)
    args = p.parse_args(argv)
    t0 = time.time()
    a, b = Release(args.release_a, args.name_a), Release(args.release_b, args.name_b)
    doc = build(detect_changes(a, b), a, b)
    doc["replay"] = replay_block(a, b, time.time() - t0)
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(f"wrote {out}: verdict {doc['verdict']}, {len(doc['findings'])} finding(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
