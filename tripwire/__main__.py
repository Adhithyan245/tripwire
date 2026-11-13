"""python -m tripwire diff <release_A_dir> <release_B_dir> [--out out/findings.json] [--changes changes.json]"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

from .contract import load_changes
from .findings import build
from .release import Release
from .validate import validate


def main(argv=None):
    p = argparse.ArgumentParser(prog="tripwire", description="Diff two TCGA-BRCA releases. Research use only.")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("diff", help="compare release B against release A and write findings.json")
    d.add_argument("release_a")
    d.add_argument("release_b")
    d.add_argument("--out", default="out/findings.json")
    d.add_argument("--changes", help="use these changes (contract JSON list) instead of running the detector")
    d.add_argument("--name-a")
    d.add_argument("--name-b")
    d.add_argument("--hash-a", choices=["file", "content"], default="file")
    d.add_argument("--hash-b", choices=["file", "content"], default="content")
    d.add_argument("--no-verify-unaffected", action="store_true", help="don't rerun analyses the impact map says are unaffected")
    d.add_argument("--challenge-dir", help="path to the challenge repo (for the validator)")
    d.add_argument("--no-report", action="store_true", help="don't write the HTML report next to findings.json")
    r = sub.add_parser("report", help="write the human-readable HTML report for an existing findings.json")
    r.add_argument("findings")
    r.add_argument("--out", help="default: same name as the findings file, .html")
    args = p.parse_args(argv)

    if args.cmd == "report":
        from .report import write_report
        src = pathlib.Path(args.findings)
        dest = write_report(json.loads(src.read_text()), args.out or src.with_suffix(".html"))
        print(f"wrote {dest}")
        return 0

    t0 = time.time()
    a, b = Release(args.release_a, args.name_a), Release(args.release_b, args.name_b)
    if args.changes:
        changes = load_changes(args.changes)
    else:
        from .detect import detect_changes
        changes = detect_changes(a, b)
    doc = build(changes, a, b, args.hash_a, args.hash_b, verify_unaffected=not args.no_verify_unaffected)

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2))

    print(f"Tripwire: {a.name} -> {b.name}   overall verdict: {doc['verdict']}")
    for an in doc["analyses"]:
        print(f"  {an['id']:<3} {an['verdict']:<22} {an['why']}")
    print(f"  {len(doc['findings'])} finding(s), {len(doc['repairs'])} proposed repair(s) (none applied)")
    try:
        errs = validate(doc, args.challenge_dir)
        print(f"  format/validate.py: {'valid' if not errs else 'INVALID'}")
        for e in errs:
            print("   -", e)
    except FileNotFoundError as e:
        errs = []
        print(f"  validator skipped: {e}")
    print(f"  wrote {out} in {time.time() - t0:.1f}s")
    if not args.no_report:
        from .report import write_report
        print(f"  report: {write_report(doc, out.with_suffix('.html'))}")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
