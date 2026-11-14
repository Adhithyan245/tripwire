"""Reproduce a planted sample swap, its research impact, and oracle recovery.

No historical incident is claimed to be reproduced. Raw data stays in temporary
directories; generated findings and the aggregate evidence go under ignored out/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tripwire.api import check
from tripwire.detect import detect_changes
from tripwire.mutation_lab.core import evaluate, generate
from tripwire.release import Release, content_sha256


def _commit(path: Path) -> str | None:
    result = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def replay(source: Path, output: Path, seed: int = 42) -> dict:
    source, output = source.resolve(), output.resolve()
    # Never allow evidence output to modify a source release.
    if output == source or source in output.parents or output in source.parents:
        raise ValueError("output must be outside the source release and its ancestors")
    if output.exists():
        raise FileExistsError("choose a new output folder; existing evidence is never overwritten")
    started = time.monotonic()
    a = Release(source, name="trusted")
    before = {name: content_sha256(source / name) for name in a.files}
    with tempfile.TemporaryDirectory(prefix="driftwire-incident-") as tmp:
        changed, recovered = Path(tmp) / "changed", Path(tmp) / "recovered"
        truth = generate(source, changed, "swap", seed)
        assert {c.file for c in truth} == {"protein_rppa.tsv.gz"}, "unexpected mutation target"
        b = Release(changed, name="planted-swap")
        observed = detect_changes(a, b)
        score = evaluate(truth, observed)
        baseline = check(source, source)
        incident = check(source, changed)
        # Oracle counterfactual: restore only the planted file from trusted data.
        # This uses known truth; it is not an autonomous repair or its evaluation.
        shutil.copytree(changed, recovered)
        shutil.copy2(source / "protein_rppa.tsv.gz", recovered / "protein_rppa.tsv.gz")
        recovery = check(source, recovered)
        docs = {"baseline": baseline, "incident": incident, "oracle-recovery": recovery}
        source_unchanged = before == {name: content_sha256(source / name) for name in a.files}
        if not source_unchanged:
            raise RuntimeError("source data changed during replay")
        errors = {name: result.validate() for name, result in docs.items()}
        if any(errors.values()):
            raise RuntimeError(f"organizer validation failed: {errors}")
        protein_counts = [len(a.protein.columns), len(b.protein.columns), len(Release(recovered).protein.columns)]
        root = Path(__file__).resolve().parents[2]
        status = subprocess.run(["git", "-C", str(root), "status", "--porcelain"], capture_output=True, text=True)
        summary = {
            "kind": "controlled simulation, not a historical incident reproduction",
            "provenance": {"engine_commit": _commit(root), "organizer_commit": _commit(source),
                           "python": sys.version.split()[0], "working_tree_dirty": bool(status.stdout.strip()),
                           "replay_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
            "seed": seed,
            "protein_sample_counts": protein_counts,
            "count_only_baseline": "no alarm" if protein_counts[0] == protein_counts[1] else "alarm",
            "detection": score,
            "no_change_detector_reports": len(detect_changes(a, a)),
            "oracle_recovery_detector_reports": len(detect_changes(a, Release(recovered))),
            "questions": {name: result.questions for name, result in docs.items()},
            "analyses": {name: result.doc["analyses"] for name, result in docs.items()},
            "input_fingerprints": before,
            "source_unchanged": source_unchanged,
            "all_outputs_validate": True,
            "seconds": round(time.monotonic() - started, 2),
            "limitations": [
                "One selected synthetic swap, not independent or clinical validation.",
                "Count-only baseline is deliberately simple; no competing tool was benchmarked.",
                "Oracle recovery uses known planted truth and a trusted prior file.",
                "Pre-existing label-concordance findings can remain after oracle recovery.",
                "Cross-release matching differs from cross-omics identity inference in COSMO/proMODMatcher.",
            ],
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".incident-evidence-", dir=output.parent) as stage:
            stage = Path(stage)
            for name, result in docs.items():
                result.save(stage / f"{name}.json")
            (stage / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
            stage.rename(output)
        return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release_a", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    result = replay(args.release_a, args.out, args.seed)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
