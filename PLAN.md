# Tripwire — Idea Brief and Team Plan

> **Proposed update — not yet accepted.** The plan below remains the team's agreed plan until [plan-change proposal #2](https://github.com/Adhithyan245/tripwire/issues/2) is accepted by affected role owners and the repo owner. This section is a reviewable proposal, not authorization to merge dependent code. Update the relevant sections below as part of the accepted implementation PR, in accordance with CONTRIBUTING.md.

## Proposal: question-aware decision rehearsal

**Pitch:** Tripwire shows how a change in a data release affects a particular research question, what evidence supports the result, and what a reviewer would need to reconsider it.

Keep Cohort Control Tower's release comparison, A1/A2 impact mapping and shared-format output. Add one connected workflow:

1. **Question card:** The reviewer selects or supplies a structured card with intended use, cohort, outcome, required inputs and acceptable limitations. Start with a small, explicitly supported set of questions. Validate the card and show unsupported or missing fields; do not silently guess.
2. **Evidence and impact:** Compare releases; show each supported finding with its source files, fields, counts or affected records, calculation, limitations and relevance to the selected question. Explain why other analyses are unaffected. Distinguish observed changes from suspected causes.
3. **Decision rehearsal:** Preview one or two supported proposed actions, such as excluding a suspect record from a descriptive analysis or requiring a patient-grouped split. Recompute only what the available data and code support. A preview is not a source-data change, a repair, or evidence that a reviewer has approved the dataset.
4. **Human review:** Record a reviewer decision (approve, reject, or request more evidence), the reasons and limitations, and the evidence needed to reconsider. Flag swaps and duplicates for curator review. Do not auto-apply repairs.
5. **Check coverage:** List checks run, passed, failed, skipped or unavailable, with the reason. A missing required check or missing evidence must not be interpreted as a pass. The tool cannot claim leakage from duplicated patients alone: it should distinguish a potential risk from leakage demonstrated by an actual supplied split.

A single release may produce different findings or verdicts for different questions **only when the data and documented rules support the difference**. Thresholds and minimums are prototype policy choices, not clinical standards; show their values and rationale. Do not claim clinical validity or use the tool for patient-level decisions.

### Published Track 1 rubric

The [event page](https://the-open-accelerator.com/hackathon/upcoming/OncoSysHack/) publishes the following weights. This replaces the need to rely on the fallback score lower in this document; no score is predicted for unbuilt or untested functionality.

| Criterion | Points |
| --- | ---: |
| Finding supported data problems | 20 |
| Reasoning for the research question | 20 |
| Evidence and sources | 15 |
| Safety and uncertainty | 15 |
| Working tool and clear setup | 15 |
| Useful next steps | 10 |
| Communication | 5 |

### Proposed MVP and cut order

**First end-to-end slice:** detect at least one real change from supplied releases → connect it to a supported question and affected analysis → show checks and evidence → record a human review → export `findings.json` that passes the organizer validator. Then add additional detection coverage and a single computable decision preview. Do not treat a stub detector, a skipped check, or an untested setup as a completed slice.

The question card, relevant checks, evidence, review, valid output, and unseen-input workflow are core. Cut in this order if behind: AI-written summary and free-text question translation; Mutation Lab interface (keep the smallest useful synthetic test harness); additional preview actions; visual polish; the preview itself. Never cut human review, required evidence, question-specific reasoning, or format validation to preserve a stretch feature. Site-confounding and other checks must state their assumptions and limitations; cut unsupported checks instead of implying they passed.

**Estimate:** 6–12 team-hours beyond a working detection-to-findings pipeline for a minimal card, one preview, review record and coverage display. This is an unvalidated estimate; revisit after integration. The detector, format compatibility, and clean setup remain the critical path.

### Proposed four-person allocation

| Role | Scope |
| --- | --- |
| 1 · Detection | Detect changes in the supplied releases with source evidence and conservative handling of duplicates and low-information profiles. |
| 2 · Impact, verdicts and format | Structured question card, dependencies, explicit verdict/check-coverage rules, analysis reruns and shared-format output. |
| 3 · QA and integration | Synthetic mutations and false-positive cases, validator, blind practice run, practice-envelope timing and fresh-clone test. Report measured misses and denominators. |
| 4 · Review experience and story | Evidence drill-down, supported action preview, reviewer record, setup documentation, video and demo. |

Integrate the first slice before expanding coverage. Role assignments remain unfilled until the team agrees; this proposal does not change the shared change contract by itself.

### Proposed demo and unseen-input rehearsal

In three minutes: show equal release counts and an actual detected change; trace it to evidence and an affected analysis; change between two supported question cards and explain the difference; preview one supported action and its remaining limitations; record a human decision and show export. Never promise a verdict flip before seeing the data. Use a recorded backup. For Q&A, rehearse the organizer's [practice envelope](https://github.com/disleveK/oncosys-hackathon-challenge/blob/main/envelopes/README.md), run the actual tool on the unsealed input, and time the complete workflow; the event page recommends finishing within about a minute after unsealing.

### Historical case: TCGA breast-cancer sample misalignment

The motivation is a real case, not a claim about the contents of the event's frozen release. In [Yoo et al., MODMatcher (2014)](https://doi.org/10.1371/journal.pcbi.1003790), researchers examined 317 TCGA breast-cancer tumor samples with gene-expression and methylation profiles and reported eight misaligned tumor profile pairs. Two profiles were cross-aligned, suggesting a sample swap; comparison with miRNA data suggested the mRNA profiles were involved. After the authors' proposed realignment, the number of statistically identified methylation–expression associations rose from 9,195 to 9,252 under their study's thresholds. The 57-association difference belongs to that paper; it is not a Tripwire result or a clinical outcome.

**Honest scope:** MODMatcher compared different modalities within a dataset. Tripwire's release comparison can catch an analogous change only when a suitable correct earlier baseline exists and the changed data type is covered. If the same error is already present in both releases, the release diff may miss it. Do not imply the historical error is in the current event data, that Tripwire would certainly have found it, or that Tripwire reproduces the authors' cross-modal method. Do not infer sensitive attributes, attempt re-identification, or link records to external information about individuals.

### Proposed incident-inspired replay and evaluation

Using only the event-approved frozen release, with original files unchanged:

1. Verify Release A using the organizer's documented checksums. Make a local test copy B; never commit raw data or generated releases.
2. Plant a two-profile swap in a data type the detector supports, preserving sample IDs and counts. Maintain a separate local test manifest with the known changes. This recreates a **failure pattern**, not the historical patient records. Use additional planted swaps, duplicates, omissions and other supported changes only after the first slice works.
3. Freeze the analysis question and calculation before inspecting results. Compare A and B, record findings and their evidence, run the chosen analysis, and show the measured difference with denominators and limitations. A changed result is possible, not guaranteed; report the observed outcome.
4. Preview a supported exclusion or restoration on an overlay without changing the source release. Show the recalculated result, the evidence needed to confirm the proposed action, and the remaining uncertainty. Record a human decision; do not auto-apply a repair.
5. Test a byte-identical copy and an equivalent reordered copy as no-change controls. Where possible keep some seeded cases hidden from detector development. Report true positives, false positives and false negatives, with precision and recall by fault type and denominators. Account for missing or inapplicable cases instead of reporting one inflated aggregate. Exact profile equality is evidence to investigate, not proof of a mistaken identity; distinguish legitimate replicates from suspected errors.
6. Rehearse the organizer's practice envelope and validate the exported `findings.json`. Separately document that replay performance on planted changes does not establish accuracy on the historical incident or all unseen releases.

**Illustration, not a Tripwire benchmark:** An eight-record toy calculation exchanged two scalar values while retaining eight records. The difference between two group means moved from 8.0 to 2.5 and returned to 8.0 after the known original values were restored. This example uses invented values and a known reference, not patient data; it is not an observed effect in the challenge data. Replace it in a live demo with actual results from the approved-data replay, or label it clearly as a toy.

**Suggested demo framing:** “Researchers documented a breast-cancer data alignment problem. We simulated an analogous swap in the event data: the count stayed the same, the detector reported [measured finding], and the preselected analysis moved [measured before/after]. A reviewer can inspect the evidence and test a proposed action. Our release comparison cannot detect an error shared by both releases.” Do not fill in bracketed results until actually measured.

### Mock judge feedback — not official scores

Three independent model reviewers assessed the concept without executing Tripwire. Claude and Grok judged the limited described current evidence at 40/100 and 25/100 respectively; an OpenAI reviewer estimated 74/100 **conditional on the proposed workflow working**. The inputs and assumptions differ, so these numbers are not directly comparable and are not a prediction of the event outcome. The [official rubric](https://the-open-accelerator.com/hackathon/upcoming/OncoSysHack/) and actual organizer judges control.

Common improvements: replace the stub detector; test on unseen changes and no-change controls; show how a specified research question changes the analysis and decision; trace conclusions to the actual calculations and source fields; show checks not run and release-diff blind spots; make review and reproducible setup observable. Demonstrated results matter more than the mock scores.

### Why this direction

The organizer's [Cohort Control Tower brief](https://github.com/disleveK/oncosys-hackathon-challenge/blob/main/products/cohort-control-tower.md) requires release comparison, affected-analysis reruns and shared-format output. The rehearsal adds a clear, question-specific next step to that core. Previous TOA winners offer useful precedent, not evidence of this event's judges: [Retrieval Crew](https://the-open-accelerator.com/hackathon/past/RAGtheCityHack/Retrieval-Crew-Track-A-review.html) emphasized traceable answers and measured limitations; [Atlas Weave](https://the-open-accelerator.com/hackathon/past/Chart-the-Common-Wealth/) paired evidence with human approval. The current event's published rubric and rules control this project.

---


Nov 11, 2026 · @Adhithyan Aravind

## Summary

We are building **Tripwire**, the Track 1 (Cohort Firewall) entry, based on the featured **Cohort Control Tower** product. Tripwire answers two questions about the frozen TCGA-BRCA data and gives every answer a verdict: **Ready, Conditional, Blocked or Insufficient Evidence**.

1. **What silently changed in this new data release, and which analyses does it break?** Tripwire diffs two releases, finds swaps, duplicates and lost coverage, reruns only the affected analyses, and writes `findings.json` in the shared format.
2. **Is this dataset ready for this AI question?** A researcher types a proposed AI question in plain English. Tripwire turns it into a checked analysis spec and tests it for patient leakage, site confounding and sample size.

The differentiator is the **Mutation Lab**: Tripwire injects many kinds of change into a release, measures what it catches, and shows its own blind spots on screen.

**Pitch line:** "Same sample count, different data. Tripwire tells you what changed, what it breaks, and what it can't see."

## The hackathon: what shapes the build

Judges run our tool live on a data release we have never seen, and a checker compares our `findings.json` with an answer key. Everything below follows from that.

| Item | Detail |
| --- | --- |
| Event | OncoSys AI Healthcare Hackathon (The Open Accelerator, OncoSys AI, Northeastern, Red Hat), Nov 11–14, 2026 |
| Track | Track 1, Cohort Firewall: decide whether data is ready for an AI question |
| Data | Frozen TCGA-BRCA release only, fetched with `data/tcga-brca/fetch.py` and checked against `sources.csv` |
| Team form | Due Thu Nov 12, 1:30 PM ET |
| Checkpoint 1 | Thu: post one working result in Discord |
| Checkpoint 2 | Fri: swap repos with our paired team; each runs the other's from the README alone |
| Code freeze | Sat Nov 14, 2:15 PM ET: demo video and Git repo due |
| Presentation | 3 minutes plus 2 minutes of questions, Cabral Center, Northeastern |
| Rubric | 7 criteria, 100 points, per track; released at kickoff (not yet in this doc) |

**The bar every project must clear:** a judge can use the workflow without us narrating, sees one result they can verify, and one limitation they can inspect inside the product.

**Judging notes from the rules:** a finished workflow beats an ambitious one that doesn't run. "This data can't answer the question, and here's why" is a valid, winning result.

**Finale:** a Cohort Control Tower catches a silent change in a release, and another team's Repair Review Desk imports our findings and makes the review decision live. We should volunteer for it.

Sources: [event page](https://the-open-accelerator.com/hackathon/upcoming/OncoSysHack/), [challenge repo](https://github.com/disleveK/oncosys-hackathon-challenge), [RULES.md](https://github.com/disleveK/oncosys-hackathon-challenge/blob/main/RULES.md), [SUBMISSION\_CHECKLIST.md](https://github.com/disleveK/oncosys-hackathon-challenge/blob/main/SUBMISSION_CHECKLIST.md), [Cohort Control Tower brief](https://github.com/disleveK/oncosys-hackathon-challenge/blob/main/products/cohort-control-tower.md).

## The problem and why Tripwire wins

A new data release can keep the same sample count while swapping, duplicating or dropping samples underneath. Any analysis or model built on it silently changes, and a count check won't notice.

The user is a **research engineer** who owns a dataset that gets new releases. Today they compare row counts or rerun everything. Neither tells them which result moved, or why.

Why this idea wins at this event:

- **Objective scoring.** Featured products get the answer-key checker. The most robust detector earns points nobody can argue with.
- **It answers the track's headline question.** Per-analysis verdicts plus the Question Gate answer "is this dataset ready for this AI question?" directly.
- **It survives the unseen input.** The Mutation Lab is our test suite, so we never tune to the practice release.
- **It shows its limits.** The on-screen blind-spot report is the inspectable limitation the rules require.
- **It fits our past work.** It uses the same deterministic-verifier pattern as OpsPilot.

**Honest weak spot:** several teams will build a Control Tower, and a plain dataframe diff may catch the practice changes. Our edge is impact mapping, verdicts, readiness checks and the Mutation Lab. Without them, we are just another diff.

## The product

Tripwire has two modes that share one verdict engine, plus a Mutation Lab that tests both.

### Mode 1: Release diff (the scored core)

1. Load release A and release B.
2. Fingerprint every sample in every data type: protein, RNA, copy number, mutations.
3. Detect changes: swaps, duplicate profiles under new IDs, samples that appeared or disappeared, clinical label changes, sample-type code changes, and coverage lost by subgroup.
4. Map each change to the analyses that use those files, fields and samples.
5. Rerun only the affected analyses. Show before and after. Say why the rest were left alone.
6. Give each analysis a verdict and write `findings.json`, with proposed repairs that are never auto-applied.

**Practice target:** with practice release B, Tripwire must catch that membership changed even though the count didn't, flag A1 (ER-alpha protein by ER status) as affected, and leave A2 (RNA subtype mix) alone. It must reach that from logic, not hardcoding.

### Mode 2: Question readiness (the Question Gate)

1. A researcher types a proposed AI question, for example "predict ER status from RNA."
2. An LLM translates it into a structured spec: input files, columns, label, sample filter.
3. Code validates the spec: columns exist, label present, filter returns samples.
4. The researcher confirms the spec before anything runs.
5. Three readiness checks run on the confirmed spec:
   1. **Patient leakage:** patients with several samples that could fall into both train and test sets.
   2. **Site confounding:** the label unevenly spread across tissue source sites (from the TCGA barcode), so a model could learn the hospital, not the biology.
   3. **Sample size per class:** too few labeled samples per class after filtering.
6. A verdict comes back with the evidence behind it.

### The verdicts

| Verdict | Release diff meaning | Question readiness meaning |
| --- | --- | --- |
| Ready | Nothing this analysis uses changed | All checks pass |
| Conditional | Inputs changed, result moved less than our stated tolerance | A fixable issue, e.g. split by patient |
| Blocked | Result moved beyond tolerance or the conclusion flipped | A check fails that can't be fixed in this data |
| Insufficient Evidence | Too few samples left after the change | Too few labeled samples per class |

### The Mutation Lab

A generator injects change types into release A: swaps, duplicates, drops, label flips, sample-type code changes, ID case and whitespace changes, unit shifts in one data type, and missing data concentrated in one subgroup. Tripwire runs on each one. The interface shows detection rate per change type, including the ones we miss and why. During the demo, a judge picks a change type from a dropdown and watches Tripwire catch it.

## Technical design and stack

Everything that gets scored is deterministic Python. The LLM only translates questions and writes summaries, and code checks both.

**Pipeline:** load releases → fingerprint → detect changes → map impact → rerun affected analyses → verdicts → `findings.json` → Streamlit interface. The Question Gate feeds a confirmed spec into the same impact and verdict steps.

| Component | How it works |
| --- | --- |
| Fingerprints | Per sample and data type, a hash of the rounded value vector, plus nearest-neighbour correlation to catch near-duplicates (e.g. above 0.999 on RNA) |
| Swap detection | Sample ID X in B carries the fingerprint that belonged to ID Y in A |
| ID handling | Sample and patient IDs kept separate. Parse TCGA barcodes for patient, sample-type code (01 primary tumor, 11 normal, 06 metastatic) and tissue source site |
| Coverage loss | Missing-data rate by subgroup (subtype, ER status) compared between releases |
| Impact map | Each analysis declares its files, columns and sample filter. Affected = changed samples and fields that intersect what it uses |
| Verdict engine | Shared by both modes; tolerance and minimum sample count stated in config and shown in the interface |
| Output | `findings.json`, shared format v0.2, must pass `python format/validate.py` |
| Interface | Streamlit: verdicts first, then evidence trace, limitations panel, human-review flags, research-only label |

**Stack:** Python, pandas or DuckDB, Streamlit, pytest. AI through Ollama locally or a key the user pastes in. Gitleaks before submission. Nothing else.

**Read first, before writing code:** `format/README.md`, `format/validate.py`, `data/tcga-brca/reference_analyses.py`, and `make_release.py --help`. Do **not** open `releases/practice-B/CHANGES.json` until our tool has run on practice B.

## AI use, safeguards and hard rules

The AI never decides a verdict. It translates and explains, and code checks everything it produces.

| AI job | Safeguard |
| --- | --- |
| Question Gate: plain English to analysis spec | Code checks columns, label and filter; the researcher confirms the spec before it runs |
| Summary of what broke | Every sample ID and number in the summary must exist in `findings.json`; anything else is rejected |
| No key or model available | Fall back to a template summary and a manual spec form; the demo still works |

The AI must run real queries or read real files, show its sources, and say clearly when the data can't answer.

**Rules we must never break:**

- No diagnosis, treatment advice, patient risk score, or claim of clinical validity, regulatory compliance or production readiness. The interface carries a research-only label.
- No re-identification and no linking records to outside sources about individuals.
- No API keys, tokens or private links in the repo. Users supply their own key.
- No raw TCGA files committed. They are fetched and checked against the pinned checksums.
- Third-party code and licenses listed; data credited as in `DATA_LICENSES.md`.
- **Human review:** every swap or duplicate is flagged for curator review, and proposed repairs are never applied automatically.

## Demo script (3 minutes)

The demo puts the judge in control twice: once to break the data, once to ask a question.

| Time | What happens | What it proves |
| --- | --- | --- |
| 0:00–0:20 | "Same sample count, different data." Show two releases with identical counts | The problem is real and invisible |
| 0:20–1:00 | Drop in the new release. Verdicts appear: A1 Blocked or Conditional, A2 Ready, with the swapped samples listed | Detection plus impact mapping |
| 1:00–1:30 | Click one changed sample and trace it to the files, fields and calculation. Show how far A1's result moved | One result the judge can verify |
| 1:30–2:05 | Judge picks a change type from the Mutation Lab dropdown; Tripwire catches it live | Robustness on input we didn't prepare |
| 2:05–2:40 | Judge types an AI question. Tripwire shows the spec, the judge confirms, a verdict comes back with leakage or sample-size evidence | The track's headline question, answered |
| 2:40–3:00 | Show the blind-spot panel: "We catch X of Y change types; here's what we miss" | One limitation the judge can inspect |

**Backup:** a recorded video of the full run, in case anything fails live. Rehearse it at least twice on Saturday morning.

## Projected score and risks

Projected score is about **86/100** on a fallback rubric, if executed well. The official Track 1 rubric isn't in this doc yet, so these are not the real weights. The last points to 90 come only from Saturday's evidence: a high Mutation Lab catch rate and the Question Gate handling a question a judge invents.

| Risk | Severity | Mitigation |
| --- | --- | --- |
| Tool only works on the practice release | Critical | Never hardcode practice changes; the Mutation Lab is our test suite from Thursday |
| Unseen release has change types we didn't anticipate | High | Detect generally (fingerprints, distributions), then report what we miss |
| Shared format v0.2 is harder than expected | High | First output passes the validator by Thursday noon, even if nearly empty |
| Other teams build the same product | High | Compete on impact mapping, verdicts, readiness checks and the Mutation Lab |
| Scope grew with the Question Gate | Medium | Start it only after the core passes on practice B; cut it if behind |
| Official rubric weights things differently | Medium | Re-score against it the moment we have it |
| LLM or API fails during the demo | Medium | Template fallback and a manual spec form; AI isn't on the scored path |
| Accidental clinical claim | Low | Research-only label; never output anything about a patient |

## Team plan

Four people work in parallel from hour one by building against one shared data contract. Fill in names in the Owner column.

### The shared contract (agree Thursday morning, 30 minutes, all four)

One detected change looks like this. The detector writes these, the Mutation Lab uses them as its answer key, and `findings.json` is built from them.

```json
{
  "sample_id": "TCGA-XX-XXXX-01A",
  "change_type": "swap",
  "file": "protein",
  "fields": ["ER-alpha"],
  "evidence": "fingerprint matches TCGA-YY-YYYY-01A in release A",
  "before": "...",
  "after": "..."
}
```

### Roles

| Role | Owner | Owns | Done when |
| --- | --- | --- | --- |
| 1. Detection engine |  | Fingerprints, swaps, duplicates, appeared and disappeared samples, label and sample-type changes, subgroup coverage loss; Friday: the three readiness checks | Catches practice B's changes without reading `CHANGES.json` |
| 2. Impact, verdicts and format |  | Dependency map for A1 and A2, reruns, before and after, verdict engine for both modes, `findings.json`, validator | Output validates; A1 flagged and A2 left alone from logic |
| 3. Mutation Lab and QA |  | Change generator, detection-rate report, pytest suite, questions with known answers, clean-clone run, Gitleaks, Checkpoint 2 | Reports "catches X of Y"; a fresh clone runs from the README alone |
| 4. Interface, Question Gate and story |  | Streamlit app, Question Gate (LLM call plus spec form), README, demo video, 3-minute pitch, optional AI summary | A judge reaches a verdict without anyone explaining |

**Who fits which role:** Role 1 is the strongest pandas person. Role 2 is the most careful engineer, since it's the critical path and must not also present. Role 3 likes breaking things. Role 4 is the best communicator and builds against a hand-written mock `findings.json` from the start.

### Timeline

| When | Role 1 | Role 2 | Role 3 | Role 4 |
| --- | --- | --- | --- | --- |
| Thu morning | Agree contract; read format spec with Role 2 | Agree contract; read format spec | Agree contract; read `make_release.py` | Agree contract; write mock `findings.json` |
| Thu by noon | Fingerprinting | Near-empty `findings.json` passes validator | First 2–3 mutation types | Streamlit skeleton on the mock |
| Thu evening | Detection works on practice B | Impact map for A1 and A2 | 4–5 mutation types | Verdict and evidence views |
| Thu night | First integration; post Checkpoint 1 |  |  |  |
| Fri midday | Readiness checks: leakage, sample size | Reruns, verdicts, spec input for Question Gate | Runs every mutation type; files misses to Role 1 | Question Gate LLM call and spec form |
| Fri evening | Site confounding; fix misses | Integration lead | Checkpoint 2 repo swap | Swap mock for real output |
| Fri night | Feature freeze |  |  |  |
| Sat to 2:15 PM | Bug fixes only | Bug fixes; technical Q&A prep | Final clean-clone check | Video, README, rehearse pitch twice |

### Rules that keep us from colliding

- **Merge on schedule.** Pull requests into `main` at Thursday night, Friday midday and Friday night, with Role 3's tests passing first.
- **Role 3 is the referee.** Mutation Lab misses go straight to Role 1 as bugs.
- **Presenter stays off the critical path.** Role 4 presents; Role 2 answers technical questions.
- **Gate on the core.** No Question Gate or readiness work until detection plus a valid `findings.json` passes on practice B.

### Cut order if we fall behind

1. AI summary
2. Site-confounding check
3. Question Gate
4. Interface polish

Never cut: validator-passing `findings.json`, impact mapping, the limitations panel, or the human-review flags.

## Submission checklist and open questions

Tick these off before the Saturday 2:15 PM ET code freeze.

- [ ] Team form submitted with Track 1 and Cohort Control Tower (Thu 1:30 PM ET)
- [ ] Checkpoint 1 posted in Discord (Thu)
- [ ] Checkpoint 2: paired team ran our repo from the README; we fixed what broke (Fri)
- [ ] README names product, track, user, the one workflow, team members, exact setup and run steps
- [ ] Clean clone: fresh folder, `fetch.py`, tool runs from the README alone
- [ ] Judged results use the frozen TCGA-BRCA release; checksums match `sources.csv`
- [ ] `findings.json` passes `python format/validate.py`
- [ ] One result a judge can trace to samples, files and a calculation
- [ ] One limitation visible in the product, not only the README
- [ ] Human-review flags shown in the interface
- [ ] No diagnosis, treatment advice, risk score or clinical claim
- [ ] Gitleaks run; no keys, tokens or private links
- [ ] AI runs with a local model or user-supplied key, shows sources, says when data can't answer
- [ ] Third-party code and licenses listed; data credited
- [ ] Demo video link in the README
- [ ] Pitch rehearsed twice

**Open questions:**

- What does the official Track 1 rubric weight? Re-score this plan against it.
- Who owns each role? Fill in the Owner column above.
- Which team are we paired with for Checkpoint 2, and will they build a Repair Review Desk for the finale handoff?
