"""Command-line interface for controlled release mutations and scoring."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import warnings

from tripwire.contract import load_changes
from tripwire.mutation_lab.core import SCENARIOS, evaluate, generate
from tripwire.release import Release


def main(argv=None):
    parser = argparse.ArgumentParser(description="Research-only controlled mutation and detector evaluation")
    commands = parser.add_subparsers(dest="command", required=True)
    gen = commands.add_parser("generate", help="make a mutated copy and separate ground-truth manifest")
    gen.add_argument("source", type=Path)
    gen.add_argument("target", type=Path)
    gen.add_argument("--scenario", choices=SCENARIOS, required=True)
    gen.add_argument("--truth", type=Path, required=True, help="new JSON file outside both release directories")
    gen.add_argument("--seed", type=int, default=0)
    score = commands.add_parser("score", help="run the installed detector and compare to a manifest")
    score.add_argument("source", type=Path)
    score.add_argument("target", type=Path)
    score.add_argument("--truth", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.command == "generate":
        truth = args.truth.resolve()
        source, target = args.source.resolve(), args.target.resolve()
        if source == truth or source in truth.parents or target == truth or target in truth.parents:
            parser.error("truth file must be outside both release directories")
        if truth.exists():
            parser.error("truth file already exists")
        if not truth.parent.is_dir():
            parser.error("truth file parent does not exist")
        changes = generate(source, target, args.scenario, args.seed)
        try:
            # Exclusive create avoids accidentally overwriting an existing manifest.
            with truth.open("x", encoding="utf-8") as f:
                json.dump({"scenario": args.scenario, "seed": args.seed,
                           "changes": [c.to_dict() for c in changes]}, f, indent=2)
                f.write("\n")
        except Exception:
            import shutil
            shutil.rmtree(target)
            raise
        print(f"Generated {args.scenario}: {len(changes)} expected sample-level change(s).")
        print("Truth is local test data; never commit generated releases or patient-derived identifiers.")
        return 0

    from tripwire.detect import detect_changes
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        observed = detect_changes(Release(args.source), Release(args.target))
    result = evaluate(load_changes(args.truth), observed)
    result["detector_warnings"] = [str(w.message) for w in captured]
    result["limitations"] = [
        "Planted-data scores do not prove performance on unseen real changes.",
        "Matching does not verify related sample IDs, affected fields or biological identity.",
        "Precision and recall are undefined when their denominators are zero.",
    ]
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
