# Mutation Lab (Role 3)

Generate a controlled, research-only release copy and compare the installed detector's changes with the known planted changes. Never commit real TCGA files, derived releases, or local truth manifests. Do not read the organizers' practice answer key or reference example to tune detection.

## Run

Fetch the organizer's pinned data and check its checksums first. Given a release folder containing `clinical.tsv` and `protein_rppa.tsv.gz`:

```bash
python -m tripwire.mutation_lab generate /path/to/release-A /path/to/new-release-B --scenario swap --seed 42 --truth /path/to/new-truth.json
python -m tripwire.mutation_lab score /path/to/release-A /path/to/new-release-B --truth /path/to/new-truth.json
```

The target directory and truth file must not already exist (a symlink at either path counts as existing); put the truth file outside both release directories. The generator never changes the source and rejects nested source/target paths, sources containing symlinks or special files, and repeated column headers or sample IDs. All validation and mutation happen in memory before the target is created; if writing the release or the truth manifest fails or is interrupted, both are removed so a half-written case is never scored. Bad inputs give a one-line CLI error, not a traceback. Clean up generated files safely when finished. Avoid publishing identifiers or truth manifests derived from real releases. `--help` lists all options.

Scenarios: `unchanged`, `reordered` (negative controls), `swap` (two sample-level records), `duplicate` (overwrite one profile with another; candidate for review), `disappeared` (remove one protein profile), `label_change` (flip an existing binary ER label), and `value_shift` (add 10 to one finite ERALPHA value whose shift is representable; `NA`, `inf` and values too large to change are skipped). Swap and duplicate pairs must differ numerically, so `1` versus `1.0` is not an observable swap. The seed makes the choice reproducible. Values are deliberately artificial; a no-change copy is not proof that a release is error-free.

Files the scenario does not touch are byte-for-byte copies. A file that is rewritten keeps every unplanted cell as its original text (blanks, `NA`, leading zeros and float formatting such as `1.50`), so the only differences from the source are the recorded changes. A rewritten file always uses LF line endings and a gzip header with `mtime` 0, so its bytes can differ from the source even when the content does not; `reordered` changes physical ordering only. A shifted value is written as Python's `repr` of the new float.

The truth manifest records the scenario, the seed, the expected changes and the SHA-256 of each data file in both releases. `score` refuses to run if either release no longer matches those hashes, which catches a wrong truth file or a release edited after generation. Older manifests without hashes are still scored, but with `truth_hashes_verified: false` and an added limitation.

## Reading a score

Scoring calls `tripwire.detect.detect_changes` and matches `Change` objects by exact change type, filename, and sample ID. Each change type reports expected and reported sample-level counts, true/false positives, false negatives, precision and recall. Duplicate detector reports count as false positives. A control with no expected changes reports its number of false positives; precision or recall with a zero denominator is `null`, not a perfect score. Warnings, including a stub-detector warning, are included in the result. `score` exits 0 whenever it produces a report, including for the current stub detector, so read the counts and warnings rather than the exit code.

The partner is scored separately and does not affect precision or recall: `expected_with_partner` counts expected changes that name a swap partner or duplicate source, and `partner_matches` counts how many of those the detector reported with the same `related_sample_id`. A detector that finds both swapped samples but pairs them with the wrong samples gets full recall and fewer partner matches. The score does **not** check affected fields, and it does not prove sample identity, biological interpretation, or impact on an analysis. A full swap is two expected sample records under this metric, not one pair; a detector emitting only one member has at most 50% sample-level recall. A matched change is not automatically a clinically meaningful problem. Exact matching may be stricter than the organizer's checker. Real duplicates may be legitimate replicates, and a release diff cannot see an error shared by both releases.

One seeded replay is a demo, not a general detection estimate. Run multiple seeds and fault types, preserve held-out cases, inspect false positives and negatives, and report denominators. State what is untested. The [historical MODMatcher TCGA-BRCA case](https://doi.org/10.1371/journal.pcbi.1003790) motivates an analogous synthetic swap; this harness does not reproduce that study's cross-modal method or historical results. No automatic repairs or clinical decisions are made.
