"""python -m tripwire diff <release_A_dir> <release_B_dir> [--out out/findings.json] [--changes changes.json]"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import textwrap
import time

from .contract import load_changes
from .findings import build
from .release import Release
from .validate import validate


def main(argv=None):
    try:  # never crash on a console that can't print a character (Windows code pages)
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
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
    d.add_argument("--question", help="question-card id: makes the top-level question and verdict that card's "
                                      "(see `python -m tripwire questions`)")
    sub.add_parser("questions", help="list the supported question cards")
    doc_p = sub.add_parser("doctor", help="check the setup and print exactly what to do next")
    doc_p.add_argument("--challenge-dir", help="path to the challenge repo (default: next to this repo)")
    e = sub.add_parser("envelope", help="Saturday in one command: open a sealed envelope, compare it with release A, "
                                        "write findings.json")
    e.add_argument("envelope", help="envelope number (e.g. 07) or 'practice'")
    e.add_argument("words", nargs=4, help="the four-word code the judge gives you")
    e.add_argument("--challenge-dir", help="path to the challenge repo (default: next to this repo)")
    e.add_argument("--out", help="default: out/findings-<envelope>.json")
    e.add_argument("--question", help="question-card id, as for diff")
    args = p.parse_args(argv)

    if args.cmd == "report":
        from .report import write_report
        src = pathlib.Path(args.findings)
        dest = write_report(json.loads(src.read_text()), args.out or src.with_suffix(".html"))
        print(f"wrote {dest}")
        return 0


    if args.cmd == "doctor":
        from .doctor import run
        return run(args.challenge_dir)
    if args.cmd == "questions":
        from .questions import CARDS
        for c in CARDS:
            print(f"{c.id:<34} {c.intended_use:<15} {c.title}")
            print(f"{'':<34} inputs: {', '.join(c.files)}; checks: {', '.join(c.required_checks)}")
        return 0

    if args.cmd == "envelope":
        return envelope(args)

    t0 = time.time()
    a, b = Release(args.release_a, args.name_a), Release(args.release_b, args.name_b)
    if args.changes:
        changes = load_changes(args.changes)
    else:
        from .detect import detect_changes
        changes = detect_changes(a, b)
    doc = build(changes, a, b, args.hash_a, args.hash_b, verify_unaffected=not args.no_verify_unaffected,
                question=args.question)

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2))

    print(f"Tripwire: {a.name} -> {b.name}   overall verdict: {doc['verdict']}")
    for an in doc["analyses"]:
        print(f"  {an['id']:<3} {an['verdict']:<22} {an['why']}")
    print("  Questions:")
    for q in doc["questions"]:
        mark = "*" if q["id"] == args.question else " "
        print(f" {mark} {q['id']:<34} {q['verdict']:<22} {textwrap.shorten(q['why'], 120, placeholder=' ...')}")
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


def envelope(args) -> int:
    """Unseal with the organizers' script, then run the normal diff on the opened release."""
    import os
    import subprocess

    from .validate import challenge_dir
    root = challenge_dir(args.challenge_dir)
    if root is None:
        print("Challenge repo not found: clone it next to this repo or pass --challenge-dir.")
        return 2
    name = "practice" if args.envelope.lower() == "practice" else f"E{int(args.envelope):02d}"
    opened = root / "envelopes" / "opened" / name / "release"
    t0 = time.time()
    if not opened.is_dir():
        env = dict(os.environ, PYTHONUTF8="1")  # unseal.py prints check marks; Windows consoles crash without this
        # The organizers' script, unchanged, with pandas writing LF line endings (see tripwire/unseal_lf.py).
        r = subprocess.run([sys.executable, "-m", "tripwire.unseal_lf", args.envelope, *args.words], cwd=root,
                           env=dict(env, PYTHONPATH=str(pathlib.Path(__file__).resolve().parent.parent)))
        if r.returncode != 0 and not opened.is_dir():
            print("Unsealing failed; see the organizers' message above (check the number and the four words).")
            return r.returncode or 1
    else:
        print(f"Envelope {name} is already open at {opened}; comparing it.")
    print(f"Unsealed in {time.time() - t0:.1f}s")
    release_a = root / "data" / "tcga-brca" / "raw"
    out = args.out or f"out/findings-{name}.json"
    extra = ["--question", args.question] if args.question else []
    return main(["diff", str(release_a), str(opened), "--out", out, "--challenge-dir", str(root), *extra])


if __name__ == "__main__":
    sys.exit(main())
