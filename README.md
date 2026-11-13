# Tripwire

**Same sample count, different data. Tripwire tells you what changed, what it breaks, and what it can't see.**

OncoSys AI Healthcare Hackathon, Nov 2026 · Team **Skill issue** · Track 1, Cohort Firewall · Product: Cohort Control Tower

**User:** a research engineer who owns a dataset that gets new releases.
**Workflow:** point Tripwire at release A and release B. It finds swaps, duplicates and lost coverage, reruns only the analyses those changes touch, gives each one a verdict (Ready, Conditional, Blocked, Insufficient Evidence) and writes `findings.json` in the shared v0.2 format.

Research use only. Tripwire makes no diagnosis, treatment advice, risk score or clinical claim.

## Setup

Needs Python 3.11+ and the [challenge repo](https://github.com/disleveK/oncosys-hackathon-challenge) cloned next to this one:

```bash
git clone https://github.com/disleveK/oncosys-hackathon-challenge ../oncosys-challenge
pip install -r requirements.txt
python ../oncosys-challenge/data/tcga-brca/fetch.py --no-rna
```

## Run

```bash
python -m tripwire diff ../oncosys-challenge/data/tcga-brca/raw <release-B-folder> --out out/findings.json
python ../oncosys-challenge/format/validate.py out/findings.json
```

### Saturday: the sealed envelope, in one command

The judge gives an envelope number and a four-word code. One command opens it with the organizers' `unseal.py`, compares the release with release A, and writes `out/findings-<envelope>.json`, which is validated:

```bash
python -m tripwire envelope 07 amber falcon river quartz
```

Rehearse with the public practice envelope:

```bash
python -m tripwire envelope practice orange meadow pilot lantern
```

The command runs `unseal.py` unchanged, on any OS. On Windows it also sets `PYTHONUTF8=1`, because the script's ✓ marks crash a Windows console otherwise (still true after the organizers' Nov 12 update). The organizers have since fixed the CRLF line-ending mismatch in `unseal.py` and `make_release.py` (challenge repo `d0fbebd`). Our LF shim (`tripwire/unseal_lf.py`) is now redundant there, but it keeps older copies of the challenge repo working. An envelope that's already open is compared without unsealing again.

### Human-readable report

Every `diff` also writes `findings.html` next to `findings.json`: the verdicts, each analysis with before and after values, each finding with its evidence, severity reason and limitation, proposed repairs (none applied), research questions when present, tolerances, and file fingerprints. It's a single self-contained page (no scripts), so it opens anywhere and prints cleanly. Use `--no-report` to skip it, or `python -m tripwire report out/findings.json` to rebuild it.

### Dashboard

```bash
streamlit run app/dashboard.py
```

The page opens at http://localhost:8501. From the sidebar you pick release B, or open a sealed envelope with its number and four words, choose a research question, and compare. The page shows:

- **Verdicts first:** the overall verdict, each research question with its rule and checks not run, and each analysis with before and after values and its sample-by-sample input changes.
- **Findings and evidence:** every finding with its severity reason, limitation and evidence table, plus a "trace one sample" view.
- **Review:** a reviewer records approve, reject or request more evidence, with a reason and their role, for every proposed repair. Decisions go into `findings.json` (`decisions`, with `original_preserved: true`). Nothing is ever applied.
- **What Tripwire can't see:** the blind spots, plus this run's unbuilt checks.
- **Data and export:** a validator check, a download of `findings.json` with the decisions, and the HTML report.

## How the pieces plug together

| Role | Plug-in point |
| --- | --- |
| 1 · Detection | Implement `tripwire.detect.detect_changes(release_a, release_b) -> list[Change]` (currently a stub). `Change` is in `tripwire/contract.py`, documented in `docs/CONTRACT.md`. |
| 2 · Impact, verdicts, format | `tripwire/analyses.py` (A1, A2 and what each reads), `impact.py`, `verdicts.py`, `findings.py` |
| 3 · Mutation Lab | Feed your answer key straight in: `python -m tripwire diff A B --changes my_changes.json`, or call `tripwire.findings.build(changes, Release(a), Release(b))` |
| 4 · Interface | Read `findings.json`: `verdict`, `analyses[].verdict`, `.why` (verdict reason), `.impact` (why touched or left alone), `.before`/`.after`, `findings[]`, `repairs[]`, `settings` (stated tolerances). For the Question Gate, use `tripwire.verdicts.CheckResult` + `question_verdict`. |

Even without a detector, Tripwire reruns the analyses the impact map calls unaffected. If one moved anyway, it is **Blocked** and reported as an unexplained change. So a detector miss can't turn into a false "Ready".

```bash
python -m pytest -q
```

### Question cards

```bash
python -m tripwire questions                       # list the supported research questions
python -m tripwire diff <A> <B> --question predict_er_from_protein
```

Every run assesses every supported card and writes them under `questions` in `findings.json`, each with its `verdict`, `why`, `release_part`, `checks`, `coverage` and `relevant_findings`. `--question` makes one card the top-level question and verdict. A card whose inputs aren't in the release says the data can't answer it. A required check that hasn't been built shows as `unavailable` and is never counted as a pass.

## Team

See [PLAN.md](PLAN.md) for roles and [CONTRIBUTING.md](CONTRIBUTING.md) for how we work. `main` is locked; all work goes to `dev`.

## Data and licenses

TCGA-BRCA open-access data via the UCSC Xena TCGA hub, fetched by the challenge repo's `fetch.py` and checked against its pinned checksums. It is never committed here. Credit: TCGA Research Network; UCSC Xena; survival from the TCGA Pan-Cancer Clinical Data Resource (Liu et al., *Cell* 2018). See the challenge repo's `DATA_LICENSES.md`.
