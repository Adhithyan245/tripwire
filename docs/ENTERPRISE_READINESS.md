# Enterprise readiness: honest self-assessment

Each dimension is scored from 0 (absent) to 5 (proven in production), with the evidence file or test and what is still unverified. Scored by the team on 2026-11-14.

| # | Dimension | Score | Evidence | Unverified |
| --- | --- | --- | --- | --- |
| 1 | Workflow integration | 3 | CI gate `--fail-on` with exit 4 ([docs/ci/driftwire-gate.yml](ci/driftwire-gate.yml)); `envelope`, `diff`, `inspect` and `verify` commands; dashboard "Run on your data" (`tests/test_dashboard_same_result.py`) | The gate has never run in a real data team's pipeline |
| 2 | Architecture | 3 | One pipeline shared by the CLI and the dashboard: the dashboard calls the CLI's `main` (same result SHA-256, tested); [docs/CONTRACT.md](CONTRACT.md) | Single process; no service or API deployment |
| 3 | Reliability | 3 | Malformed-input and fail-closed tests (`tests/test_malformed_inputs.py`, `tests/test_unfamiliar_layouts.py`); 296+ tests passing locally | The empty-cohort case can still return **Ready** for A2 ([performance.md](performance.md)); the CI matrix hasn't run on GitHub yet |
| 4 | Security and access control | 1 | [security.md](security.md): secrets policy, `pip-audit` results | No access control or authentication at all; cryptography 49.0.0 has an advisory that is off our code path but not yet bumped |
| 5 | Privacy and governance | 2 | Open-access, de-identified data only; local processing; AI intake sends column names only ([security.md](security.md)) | No PHI handling; no data-governance review |
| 6 | Output quality evaluation | 3 | Mutation Lab scorecard ([MUTATION_LAB.md](MUTATION_LAB.md)); blind AI red-team: 2 caught, 5 generic, 0 missed, 0 false alarms ([blind_redteam.md](blind_redteam.md)) | One dataset; an AI tester, not an independent person; the red-team found a masking effect |
| 7 | Observability and audit | 3 | Reproducibility receipt and `verify` ([clean_clone_run.md](clean_clone_run.md)); review decisions saved in findings.json | No logging or metrics service |
| 8 | Scalability | 2 | 10x synthetic test: 12,470 samples, 11.1 s, 213 MB ([performance.md](performance.md)) | Copy number and mutation not scaled; one run |
| 9 | Deployment and integration | 2 | Pinned `requirements.txt`; fresh-clone record; CI workflow (`.github/workflows/tests.yml`) | CI not yet run; no package release |
| 10 | Cost and support | 1 | Runs locally with no paid services | No support process, SLA or owner rota |
| 11 | Human oversight and recovery | 4 | Repairs are proposals only, never applied; per-repair review with a reason; `verify` re-checks any past result | Not tested with real curators |
| 12 | Compliance | 1 | Research-use-only labelling on every output | No regulatory assessment; not for clinical use |

## Level claimed: Level 1, Level 2 in progress

C1 (fail-safe inputs) passed: every malformed input gives a one-line error and exit 2, or a non-Ready result, and an internal error fails closed. That alone isn't enough to claim Level 2. Remaining items:

1. An empty analysis cohort must give Insufficient Evidence, not Ready. This is a verdict-logic change, found in [performance.md](performance.md).
2. A green run of the CI matrix on GitHub, with skip markers for any test that needs the challenge repo.
3. Bump cryptography to 50.0.0 and rerun the tests.
4. A first supervised pilot run under [PILOT_PLAN.md](PILOT_PLAN.md).

## Blockers to Level 3

- No access control, so anyone who can run it sees all of the data it's pointed at.
- Tested on one dataset only (TCGA-BRCA).
- No real customer pilot yet.
