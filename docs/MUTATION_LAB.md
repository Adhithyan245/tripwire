# Mutation Lab (Role 3)

Generate a controlled, research-only release copy and compare the installed detector's changes with the known planted changes. Never commit real TCGA files, derived releases, or local truth manifests. Do not read the organizers' practice answer key or reference example to tune detection.

## Run

Fetch the organizer's pinned data and check its checksums first. Given a release folder containing `clinical.tsv` and `protein_rppa.tsv.gz`:

```bash
python -m tripwire.mutation_lab generate /path/to/release-A /path/to/new-release-B --scenario swap --seed 42 --truth /path/to/new-truth.json
python -m tripwire.mutation_lab score /path/to/release-A /path/to/new-release-B --truth /path/to/new-truth.json
```

The target directory and truth file must not already exist; put the truth file outside both release directories. The generator never changes the source and rejects nested source/target paths. Clean up generated files safely when finished. Avoid publishing identifiers or truth manifests derived from real releases. `--help` lists all options.

Scenarios: `unchanged`, `reordered` (negative controls), `swap` (two sample-level records), `duplicate` (overwrite one profile with another; candidate for review), `disappeared` (remove one protein profile), `label_change` (flip an existing binary ER label), and `value_shift` (add 10 to one non-null ERALPHA value). The seed makes the choice reproducible. Values are deliberately artificial; a no-change copy is not proof that a release is error-free. The source files' original format is retained; reorder changes physical ordering only.

## Reading a score

Scoring calls `tripwire.detect.detect_changes` and matches `Change` objects by exact change type, filename, and sample ID. Each change type reports expected and reported sample-level counts, true/false positives, false negatives, precision and recall. Duplicate detector reports count as false positives. A control with no expected changes reports its number of false positives; precision or recall with a zero denominator is `null`, not a perfect score. Warnings, including a stub-detector warning, are included in the result.

The score does **not** check affected fields or a swap/duplicate partner; it does not prove sample identity, biological interpretation, or impact on an analysis. A full swap is two expected sample records under this metric, not one pair; a detector emitting only one member has at most 50% sample-level recall. A matched change is not automatically a clinically meaningful problem. Exact matching may be stricter than the organizer's checker. Real duplicates may be legitimate replicates, and a release diff cannot see an error shared by both releases.

One seeded replay is a demo, not a general detection estimate. Run multiple seeds and fault types, preserve held-out cases, inspect false positives and negatives, and report denominators. State what is untested. The [historical MODMatcher TCGA-BRCA case](https://doi.org/10.1371/journal.pcbi.1003790) motivates an analogous synthetic swap; this harness does not reproduce that study's cross-modal method or historical results. No automatic repairs or clinical decisions are made.
