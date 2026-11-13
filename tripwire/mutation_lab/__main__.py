"""Command-line interface for controlled release mutations and scoring."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
import warnings

from tripwire.contract import load_changes
from tripwire.mutation_lab.core import SCENARIOS, evaluate, generate
from tripwire.release import Release


def _fingerprints(path: Path) -> dict[str, str]:
    """Byte hashes of a release's data files, used to tie a truth manifest to its releases."""
    return {e["file"]: e["sha256"] for e in Release(path).fingerprints()}


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
        if args.truth.is_symlink():
            parser.error("truth file already exists")
        truth = args.truth.resolve()
        source, target = args.source.resolve(), args.target.resolve()
        if source == truth or source in truth.parents or target == truth or target in truth.parents:
            parser.error("truth file must be outside both release directories")
        if truth.exists():
            parser.error("truth file already exists")
        if not truth.parent.is_dir():
            parser.error("truth file parent does not exist")
        try:
            changes = generate(source, args.target, args.scenario, args.seed)
        except (ValueError, FileNotFoundError, FileExistsError) as e:
            parser.error(str(e))
        created_truth = False
        try:
            manifest = {"scenario": args.scenario, "seed": args.seed,
                        "source_files": _fingerprints(source), "target_files": _fingerprints(target),
                        "changes": [c.to_dict() for c in changes]}
            # Exclusive create avoids accidentally overwriting an existing manifest.
            with truth.open("x", encoding="utf-8") as f:
                created_truth = True
                json.dump(manifest, f, indent=2)
                f.write("\n")
        except BaseException:
            # Roll back both outputs so a half-written manifest is never scored later.
            if created_truth:
                truth.unlink(missing_ok=True)
            shutil.rmtree(target)
            raise
        print(f"Generated {args.scenario}: {len(changes)} expected sample-level change(s).")
        print("Truth is local test data; never commit generated releases or patient-derived identifiers.")
        return 0

    try:
        manifest = json.loads(args.truth.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or not isinstance(manifest.get("changes"), list):
            raise ValueError("truth manifest must contain a changes list")
        if ("source_files" in manifest) != ("target_files" in manifest):
            raise ValueError("truth manifest must contain both release hashes or neither")
        expected = load_changes(args.truth)
        source_files, target_files = _fingerprints(args.source), _fingerprints(args.target)
    except (OSError, ValueError, TypeError) as e:
        parser.error(f"cannot read releases or truth manifest: {e}")
    checked = isinstance(manifest, dict) and "source_files" in manifest and "target_files" in manifest
    if checked and (manifest["source_files"] != source_files or manifest["target_files"] != target_files):
        parser.error("releases do not match the truth manifest's file hashes; "
                     "wrong truth file, or a release changed after generation")

    from tripwire.detect import detect_changes
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        observed = detect_changes(Release(args.source), Release(args.target))
    result = evaluate(expected, observed)
    result["truth_hashes_verified"] = checked
    result["detector_warnings"] = [str(w.message) for w in captured]
    result["limitations"] = [
        "Planted-data scores do not prove performance on unseen real changes.",
        "Matching does not verify affected fields or biological identity; partners are reported separately.",
        "Precision and recall are undefined when their denominators are zero.",
    ]
    if not checked:
        result["limitations"].append("Truth manifest has no release hashes, so it may not belong to these releases.")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
