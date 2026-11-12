# How we work on Tripwire

[PLAN.md](PLAN.md) is the source of truth: what we build, who owns what, the timeline and the cut order. These rules exist so four people can work in parallel without breaking each other's work or drifting off the plan.

## Branches

| Branch | Who pushes | How |
| --- | --- | --- |
| `main` | Nobody | **Locked.** It is only opened by the repo owner (@Adhithyan245) for the scheduled releases and the final submission. |
| `dev` | Everyone | Integration branch. Push or open a pull request here. No force pushes, no deleting it. |
| `role1/*`, `role2/*`, `role3/*`, `role4/*` | The role owner | Your working branches. Merge into `dev` through a pull request. |

Workflow:

```bash
git checkout dev && git pull
git checkout -b role2/verdict-engine
# ...work, commit...
git push -u origin role2/verdict-engine
gh pr create --base dev
```

Before a pull request into `dev`:

- `pytest` passes (Role 3 is the referee, per the plan).
- Anything that writes `findings.json` passes `python <challenge-repo>/format/validate.py`.
- No keys, tokens, private links or raw TCGA files (`gitleaks detect` before every merge on schedule).
- You touched only your role's area, or the owner of the other area agreed in the PR.

## Changing the plan

The plan was agreed by all four of us. It changes only by the same kind of agreement.

A **plan change** is anything that alters:

- the shared change contract ([docs/CONTRACT.md](docs/CONTRACT.md)),
- the `findings.json` structure, the verdict meanings, tolerances or minimum sample counts,
- a role's scope or ownership, the timeline, the cut order or the "never cut" list,
- the stack (new dependency, new service, new model),
- the demo script or the pitch line.

How to propose one:

1. Open an issue with the **Plan change proposal** template. Say what changes, why it makes Tripwire score better or run more reliably, what it costs in hours, and who it affects.
2. Every affected role owner replies **approve** or **object, because …**. The repo owner makes the final call.
3. Accepted: update `PLAN.md` (and `docs/CONTRACT.md` if needed) in the same PR as the code, and link the issue.
4. Rejected or no answer: the plan stands. Don't merge work that depends on it.

A change is accepted only if it clearly improves the project: a higher score on the rubric, more robustness on the unseen release, or less risk of a broken demo. A change that is only "nicer", or adds scope late, is rejected by default. After Friday night's feature freeze, only bug fixes are accepted.

Code-only changes inside your own role (refactors, bug fixes, tests) don't need a proposal. Just follow the pull-request rules above.

## Hard rules from the event (never broken, no proposal can change these)

- No diagnosis, treatment advice, patient risk score, or claim of clinical validity, regulatory compliance or production readiness.
- No re-identification and no linking records to outside sources about individuals.
- No API keys, tokens or private links in the repo.
- No raw TCGA files or generated releases committed.
- Every swap or duplicate is flagged for human review. Proposed repairs are never applied automatically.
- Nobody on the team opens `releases/practice-B/CHANGES.json` or the reference example `format/examples/control-tower-practice-B.json` to tune detection. Tests are built from the Mutation Lab and synthetic data, never from the answer key.
