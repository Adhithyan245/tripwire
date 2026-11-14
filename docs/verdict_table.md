# One release, seven verdicts

The organizers' practice envelope, compared with the trusted release A. Every row is Driftwire's real output from:

```bash
python -m driftwire verdicts ../oncosys-challenge/data/tcga-brca/raw ../oncosys-challenge/envelopes/opened/practice/release
```

| Question | Use | Verdict | Driftwire's reason |
| --- | --- | --- | --- |
| Does ER-alpha protein differ between ER-positive and ER-negative tumors? | describe the data | **Conditional** | Computed by A1: Inputs changed; the result moved within tolerance (difference 3.051 -> 3.019 (1.0% relative; tolerance 5%)). |
| What is the PAM50 subtype mix of primary tumors? | describe the data | **Ready** | Computed by A2: Nothing this analysis uses changed: the 844 samples it reads are identical in both releases; a check rerun confirms it (largest subtype share shift 0.0 pp (tolerance 1.0 pp)). |
| Does overall survival differ between PAM50 subtypes? | describe the data | **Ready** | Nothing this question reads changed between releases. |
| Train a research model to predict ER status from protein (RPPA). | train a model | **Blocked** | 12 detected change(s) touch this question's inputs, including duplicate, swap. |
| Train a research model to predict PAM50 subtype from copy number. | train a model | **Conditional** | site_confounding: label vs tissue source site: Cramer's V = 0.19 over 17 site groups (831 samples; sites under 10 pooled). |
| Train a research model to predict ER status from RNA expression. | train a model | **Insufficient Evidence** | This data can't answer the question: rna_hiseq.tsv.gz is not in release practice. |
| Train a research model to predict PAM50 subtype from RNA expression. | train a model | **Blocked (circular)** | Circular question: the label PAM50Call_RNAseq was computed from rna_hiseq.tsv.gz, the same data this model would use as input, so it would mostly re-learn the labelling algorithm. |

Run on November 14, Driftwire branch `role2/judge-evidence`, organizer data at commit `6e15a39`. Each reason is the first sentence of the `why` field Driftwire writes into `findings.json` for that question.
