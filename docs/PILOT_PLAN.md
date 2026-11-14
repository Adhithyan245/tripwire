# Pilot plan: supervised real-world evaluation

A protocol for a first supervised evaluation. It has not been run, and nothing below is a result.

**Who runs it.** A data curator, who reviews every finding against the source data, and a researcher, who uses the releases for one of the supported questions. A Driftwire team member supports them, but doesn't score.

**On what.** Consecutive real public release pairs of the same dataset, for example successive GDC data releases of TCGA-BRCA in the same file layout. Plan for at least 10 pairs, including at least 3 that the curator expects to show no meaningful change.

**Mode: shadow.**
- Driftwire runs as a CI gate in report-only mode: `diff` writes findings.json and the report, and never blocks a release (no `--fail-on`).
- Every finding is reviewed by the curator, who records each decision and its reason in the dashboard's Review tab. Nothing is repaired automatically.
- The researcher records their own verdict for their question before seeing Driftwire's.

**Metrics.**
- **Precision:** the share of Driftwire findings that the curator confirms as real changes.
- **Recall:** of the changes the curator finds by independent review of each pair (sampled where full review is too large), the share Driftwire reported.
- **False-alarm rate on no-change pairs:** findings per pair the curator judged unchanged.
- **Time to review:** curator minutes per pair, with and without the report.
- **Verdict agreement:** Driftwire's question verdict against the researcher's own verdict, per pair.

**Go / no-go for a blocking gate.** Move the gate from report-only to blocking (`--fail-on Blocked`) only if all of these hold over the pilot:
- precision of at least 0.9 on high-severity findings;
- no missed change the curator rates high severity;
- no more than 1 false alarm across the no-change pairs;
- verdict agreement on at least 80% of pairs, with every disagreement explained.

Otherwise, stay in report-only mode, fix, and repeat on new pairs.

**Rollback.** The gate is a single CI step. To roll back, remove `--fail-on`, or revert the workflow file, and the release pipeline is back to report-only in one commit. Because Driftwire never edits the data, no data rollback is ever needed. Keep every findings.json and its receipt, so that any past decision can be re-checked with `python -m driftwire verify`.
