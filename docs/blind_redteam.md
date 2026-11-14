# Blind red-team: an isolated AI tester edits the practice release

## Answer key locked

- File: `../redteam_work/answer_key/answer_key.md` (outside the repo), written by the tester.
- SHA-256: `86a6c2513d701480859cd17e6a6b68ef129b30e49626b0de817337924b12668b`
- Locked at: 2026-11-14T18:14:11Z, before Driftwire was run on the edited release and before anyone on the team read the key. The hash was computed without opening the file.
- Verified after the run: the hash of the file read for scoring matched the locked hash above.

## Method

1. The practice envelope's opened release was copied to `../redteam_work/release_B_modified/`, outside the repo.
2. An isolated AI subagent was told to work only in `../redteam_work/`, and not to open the Driftwire repo (code, tests, docs, Mutation Lab or `redteam/`). It was asked to plant 5 to 8 realistic release errors, at least 2 of them subtle, plus 1 or 2 benign edits, and to write an answer key. It replied only "DONE".
3. The answer key's SHA-256 was recorded and committed before Driftwire ran.
4. Driftwire ran with `python redteam/run_redteam.py run --release ../redteam_work/release_B_modified` (release A: `../oncosys-challenge/data/tcga-brca/raw`). Outputs are in `redteam/results/`: overall verdict **Conditional**, 11 findings.
5. Only then was the answer key read and each edit scored. The scoring rule:
   - **caught:** the right type and the right samples;
   - **generic:** flagged with the right file and samples, but as a value change, removed rows or membership change, not as the real cause;
   - **missed:** not flagged.

## Results

| Edit | What the tester planted | Driftwire | Score |
| --- | --- | --- | --- |
| H1 | Mutation gene symbols auto-converted to dates (SEP15 → 15-Sep, MARCH1 → 1-Mar and 4 more) | F3: rows DEC1, MARCH1, MARCH5, SEP15, SEPT2 (+1 more) removed from mutation_gene_level.tsv.gz | generic: right rows, but reported as removed rows, not as a rename to dates |
| H2 (subtle) | ER status flipped Negative → Positive for 5 samples in clinical.tsv | F1: the same 5 samples changed `breast_carcinoma_estrogen_receptor_status` | caught |
| H3 | OS.time and DSS.time converted from days to months for the 111 site-E2 samples | F9: 114 samples changed OS.time and DSS.time (111 from H3 plus 3 from H6) | generic: right samples and fields, but no unit change named |
| H4 (subtle) | Copy-number columns of TCGA-A2-A04T-01 and TCGA-A2-A04W-01 swapped | F2: those two profiles exchanged in copy_number_gistic.tsv.gz | caught |
| H5 (subtle) | Protein row AKT changed from log2 to linear scale (2^x) for all samples | F6: 742 samples in protein_rppa.tsv.gz changed values without a swap or copy | generic: right file, but the single affected row (AKT) isn't named |
| H6 (subtle) | OS and OS.time copied from the row above for 3 samples | F9: all 3 are in the survival value-change finding | generic: merged with H3 |
| H7 | 3 mutation barcodes reformatted (hyphens → dots) | F4 and F5: those 3 IDs lost, and the 3 dotted IDs appeared, in mutation_gene_level.tsv.gz | generic: exact samples, but not named as ID reformatting |
| B1 (benign) | clinical.tsv rows reordered | no finding | correctly silent |
| B2 (benign) | protein rows reordered | no finding of its own | correctly silent |

**Totals:** of 7 harmful edits, 2 caught, 5 generic and 0 missed. Of 2 benign edits, 2 were correctly silent, with 0 false alarms.

**A masking effect the tester didn't plant:** the practice release already contains a protein swap (TCGA-A8-A09K-01 and TCGA-B6-A0WX-01) and 5 copied protein profiles. On the plain practice release Driftwire names both. With H5 rescaling one protein row in every sample, neither is named any more. The swapped pair is folded into F6's generic value change, and the 5 copies show up as 5 newly appeared samples (F7). So one rescaled feature can hide sample-level swaps and copies in the same file. This is a detector limitation, documented here and not fixed: detection is Role 1. A concrete fix to consider is to run swap and copy matching after excluding feature rows that shifted for almost every sample.

Other findings (F8, F10, F11) are changes and label conflicts that were already in the practice release, reported as on the plain practice run.

## Limitations

- The isolation was enforced by instructions, not by the system: the tester could technically have read the repo, and we rely on it having followed the instruction.
- The tester is an AI model, not an independent person, and it may share blind spots with the tool's authors.
- This is one run on one dataset (TCGA-BRCA), with 9 edits.
- The scoring was done by the team, using the rule above.
