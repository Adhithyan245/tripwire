# Fresh-clone run (Saturday, November 14)

A brand-new folder and virtual environment, following only the README. Run on **Windows 11 (build 10.0.26300), Python 3.11.0**. Driftwire's branch was cloned from the local repository because it wasn't pushed yet. Everything else came from the internet as the README says: the organizers' repo, the packages and the release A download. Our QA has run the same steps on macOS with Python 3.13 (see `docs/QA_REPORT.md`).

| Step | Command | Exit | Time |
| --- | --- | --- | --- |
| 1 | `git clone https://github.com/disleveK/oncosys-hackathon-challenge oncosys-challenge` | 0 | not timed |
| 2 | `py -3.11 -m venv .venv` then `.venv\Scripts\activate` | 0 | not timed |
| 3 | `pip install -r requirements.txt` (exact pinned versions) | 0 | 162.9 s |
| 4 | `python ../oncosys-challenge/data/tcga-brca/fetch.py --no-rna` | 0 | 2.9 s |
| 5 | `python -m driftwire doctor` | 0 | 2.9 s |
| 6 | `python -m driftwire envelope practice orange meadow pilot lantern` | 0 | 14.0 s |
| 7 | `python -m driftwire verify out/findings-practice.json ../oncosys-challenge/data/tcga-brca/raw ../oncosys-challenge/envelopes/opened/practice/release` | 0 | 7.7 s |

Times are wall-clock times on one laptop, including Python start-up. The package install depends on your network and pip cache.

## doctor

```
Driftwire doctor
  OK Python 3.11
  OK required packages installed
  OK challenge repo: <your-folder>/oncosys-challenge
  OK release A fetched and matches the frozen checksums (5 files)
  ! practice envelope not opened yet (optional)
      fix: python -m driftwire envelope practice orange meadow pilot lantern

All set. Next:
  python -m driftwire envelope practice orange meadow pilot lantern   # one-command demo run
  streamlit run app/dashboard.py                                     # the dashboard (tour opens itself)
```

(With output redirected to a file, the console code page shows check marks as `OK`.)

## envelope

```
Opening envelope practice

  ? Release A matches the published fingerprints
  ? Envelope practice matches its published fingerprint
  ? Envelope practice opened
  ? All 5 release files match their fingerprints

  Done in 1.7 s. Everything is in:  envelopes\opened\practice/
  New release for your tool:   envelopes\opened\practice\release/
  Also inside:                 README.txt

Unsealed in 3.8s
Driftwire: raw -> practice   overall verdict: Conditional
  A1  Conditional            Inputs changed; the result moved within tolerance (difference 3.051 -> 3.019 (1.0% relative; tolerance 5%)).
  A2  Ready                  Nothing this analysis uses changed: the 844 samples it reads are identical in both releases; a check rerun confirms it (largest subtype share shift 0.0 pp (tolerance 1.0 pp)).
  Questions:
   er_protein_by_er_status            Conditional            Computed by A1: Inputs changed; the result moved within tolerance (difference 3.051 -> 3.019 (1.0% relative; ...
   subtype_mix                        Ready                  Computed by A2: Nothing this analysis uses changed: the 844 samples it reads are identical in both releases; a check ...
   os_by_subtype                      Ready                  Nothing this question reads changed between releases.
   predict_er_from_protein            Blocked                12 detected change(s) touch this question's inputs, including duplicate, swap. For model training that means wrong ...
   predict_subtype_from_copy_number   Conditional            site_confounding: label vs tissue source site: Cramer's V = 0.19 over 17 site groups (831 samples; sites under 10 ...
   predict_er_from_rna                Insufficient Evidence  This data can't answer the question: rna_hiseq.tsv.gz is not in release practice.
   predict_subtype_from_rna           Blocked                Circular question: the label PAM50Call_RNAseq was computed from rna_hiseq.tsv.gz, the same data this model would use ...
  5 finding(s), 5 proposed repair(s) (none applied)
  format/validate.py: valid
  wrote out\findings-practice.json in 6.6s
  report: out\findings-practice.html
```

(The organizers' `unseal.py` prints check marks; with output redirected to a file on Windows they show as `?`.)

## verify

```
Driftwire verify: identical
  - result sha256 e612c917c726c97c... reproduced
```

The result hash `e612c917c726c97c...` is the same one produced on the development machine, so the result reproduces in a fresh environment.

## What the README alone didn't cover, now fixed
- The Windows activation command was garbled (`.venv\Scripts` followed by a control character). It now reads `.venv\Scripts\activate`.
- The quickstart didn't mention `verify`. The judge quickstart at the top of the README now includes it.
- `doctor` now detects a macOS Python without root certificates *before* `fetch.py` fails, and prints the exact command: `open "/Applications/Python 3.X/Install Certificates.command"`.
