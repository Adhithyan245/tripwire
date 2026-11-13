# Role 3: Mutation Lab and QA

The Role 3 scaffold lives in the repo already. It can generate controlled release changes, run the team's detector, and compare the output with the planted changes. It does not need teammates to finish a new feature before its own tests can run.

## Where to work

| Purpose | Location |
| --- | --- |
| Controlled mutations and scoring | `tripwire/mutation_lab/core.py` |
| Generate and score from the command line | `tripwire/mutation_lab/__main__.py` |
| Additional dashboard scenarios | `tripwire/mutation_lab/extended.py` |
| Mutation Lab tests | `tests/test_mutation_lab.py` |
| Detector integration tests | `tests/test_detector_mutation_integration.py` |
| Full usage, truth format and limitations | `docs/MUTATION_LAB.md` |

## Start here

From the repository root, with Python 3.11+ and the dependencies installed:

```bash
python -m pip install -r requirements.txt
python -m tripwire.mutation_lab scenarios
python -m pytest -q tests/test_mutation_lab.py tests/test_mutation_extended.py tests/test_detector_mutation_integration.py
```

The integration tests use synthetic fixtures. They compare the currently checked-out detector with seeded changes and no-change controls; a stub detector is reported as skipped rather than passed. The rest of the project's tests can be run with `python -m pytest -q`. Some checks need the organizer challenge repository and fetched data; consult the main README.

## When a teammate's change is ready

1. Test the agreed branch or exact commit in a separate checkout. Keep other people's changes intact.
2. Run the focused tests above, then the full test suite and the applicable practice-envelope workflow from the main README.
3. For release testing, fetch the organizers' approved data and verify checksums. Follow `docs/MUTATION_LAB.md` to generate a **new copy** of the release and a separate local truth manifest, then run `score`.
4. Record the commit, scenarios, seeds, expected counts, misses, false positives, skipped checks and any errors. A result only covers the cases actually tested; matching a sample/type/file does not prove the biological interpretation or that its partner and affected fields are correct.
5. Keep raw patient-derived data, generated releases, truth manifests and secrets out of Git. Do not read the organizers' practice answer key to tune detection. Human review is required for proposed repairs; the lab does not apply them.

Checkpoint 2 with Ready-Set-Blocked still requires the paired team to share its repository and exact commit. A test of another team does not complete that exchange.
