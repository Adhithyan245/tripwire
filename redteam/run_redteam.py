"""Blind red-team runner. Two jobs, no detector knowledge needed:

  python redteam/run_redteam.py copy               make an editable copy of the new release in redteam/work/release
  python redteam/run_redteam.py run                run Driftwire on that copy; results go to redteam/results/

Options: --trusted PATH (release A, default ../oncosys-challenge/data/tcga-brca/raw)
         --source PATH  (release to copy, default ../oncosys-challenge/envelopes/opened/practice/release)
         --release PATH (the edited copy to check, default redteam/work/release)
The edited copy and the planter's answer key stay out of git (see .gitignore). Research use only.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Blind red-team runner for Driftwire")
    p.add_argument("step", choices=["copy", "run"])
    p.add_argument("--trusted", default=str(ROOT.parent / "oncosys-challenge/data/tcga-brca/raw"))
    p.add_argument("--source", default=str(ROOT.parent / "oncosys-challenge/envelopes/opened/practice/release"))
    p.add_argument("--release", default=str(HERE / "work" / "release"))
    a = p.parse_args(argv)
    if a.step == "copy":
        dest = pathlib.Path(a.release)
        if dest.exists():
            print(f"{dest} already exists; delete it first if you want a fresh copy.")
            return 1
        shutil.copytree(a.source, dest)
        print(f"Copied the new release to {dest}. Edit the files there, then run:  python redteam/run_redteam.py run")
        return 0

    from tripwire.api import check
    from tripwire.report import write_report
    res = check(a.trusted, a.release, name_a="trusted", name_b="redteam")
    out = HERE / "results"
    out.mkdir(exist_ok=True)
    res.save(out / "findings.json")
    write_report(res.doc, out / "report.html")
    lines = [f"Driftwire verdict: {res.verdict}", f"Findings: {len(res.findings)}", ""]
    for f in res.findings:
        samples = [e["id"] for e in f.get("evidence", []) if e.get("kind") == "sample"]
        lines.append(f"{f['id']}  {f['kind']}  ({len(samples)} sample(s))")
        lines.append(f"    {f['summary']}")
        if samples:
            lines.append(f"    samples: {', '.join(samples)}")
    lines += ["", "Questions:"] + [f"  {k:<34} {v}" for k, v in res.questions.items()]
    (out / "summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nWrote {out / 'findings.json'}, {out / 'report.html'} and {out / 'summary.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
