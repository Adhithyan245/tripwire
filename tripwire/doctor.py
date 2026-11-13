"""python -m tripwire doctor: check the setup and say exactly what to do next.

Checks Python, the packages, the challenge repo, release A and its checksums, and the practice envelope. Every
problem comes with the one command that fixes it. Nothing is changed or downloaded.
"""
from __future__ import annotations

import csv
import importlib.util
import pathlib
import sys

from .release import file_sha256
from .validate import challenge_dir

REQUIRED = ["pandas", "numpy", "jsonschema", "cryptography"]
OPTIONAL = {"streamlit": "the dashboard", "pytest": "the tests"}


def _marks() -> tuple[str, str, str]:
    """Check marks where the console can show them; plain text on consoles that can't (old Windows code pages)."""
    try:
        "✓✗".encode(sys.stdout.encoding or "ascii")
        return "✓", "✗", "!"
    except (UnicodeEncodeError, LookupError):
        return "OK", "X", "!"


def run(explicit_challenge: str | None = None) -> int:
    OK, NO, WARN = _marks()
    ok = True
    lines: list[str] = []

    def good(msg):
        lines.append(f"  {OK} {msg}")

    def bad(msg, fix):
        nonlocal ok
        ok = False
        lines.append(f"  {NO} {msg}\n      fix: {fix}")

    def warn(msg, fix):
        lines.append(f"  {WARN} {msg}\n      fix: {fix}")

    v = sys.version_info
    (good if v >= (3, 11) else lambda m: bad(m, "install Python 3.11 or newer"))(f"Python {v.major}.{v.minor}")
    missing = [p for p in REQUIRED if importlib.util.find_spec(p) is None]
    if missing:
        bad(f"missing packages: {', '.join(missing)}", "pip install -r requirements.txt")
    else:
        good("required packages installed")
    for pkg, why in OPTIONAL.items():
        if importlib.util.find_spec(pkg) is None:
            warn(f"{pkg} not installed (needed for {why})", "pip install -r requirements.txt")

    root = challenge_dir(explicit_challenge)
    if root is None:
        bad("challenge repo not found next to this repo",
            "git clone https://github.com/disleveK/oncosys-hackathon-challenge ../oncosys-challenge")
    else:
        good(f"challenge repo: {root}")
        raw = root / "data" / "tcga-brca" / "raw"
        sources = root / "data" / "tcga-brca" / "sources.csv"
        expected = {r["file"]: r["sha256"] for r in csv.DictReader(open(sources))} if sources.exists() else {}
        needed = [f for f in expected if f != "rna_hiseq.tsv.gz"]
        absent = [f for f in needed if not (raw / f).exists()]
        if absent:
            bad(f"release A not fetched ({len(absent)} file(s) missing)",
                f"python {root / 'data' / 'tcga-brca' / 'fetch.py'} --no-rna")
        else:
            wrong = [f for f in needed if file_sha256(raw / f) != expected[f]]
            if wrong:
                bad(f"release A checksum mismatch: {', '.join(wrong)}",
                    f"python {root / 'data' / 'tcga-brca' / 'fetch.py'} --no-rna   (re-fetch; tell organizers if it persists)")
            else:
                good(f"release A fetched and matches the frozen checksums ({len(needed)} files)")
        opened = root / "envelopes" / "opened" / "practice" / "release"
        if opened.is_dir():
            good("practice envelope already open")
        else:
            warn("practice envelope not opened yet (optional)",
                 "python -m tripwire envelope practice orange meadow pilot lantern")

    print("Tripwire doctor\n" + "\n".join(lines))
    if ok:
        print("\nAll set. Next:\n"
              "  python -m tripwire envelope practice orange meadow pilot lantern   # one-command demo run\n"
              "  streamlit run app/dashboard.py                                     # the dashboard (tour opens itself)")
    else:
        print(f"\nFix the {NO} items above, then run `python -m tripwire doctor` again.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run())
