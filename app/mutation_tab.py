"""Mutation Lab tab: plant a known change in a copy of release A, let Tripwire find it blind, and score the result.

Generated releases go to a temporary folder and are deleted after each run. Synthetic test data only.
"""
from __future__ import annotations

import pathlib
import shutil
import tempfile
import time
from collections import defaultdict

import pandas as pd

from tripwire.detect import detect_changes
from tripwire.findings import build
from tripwire.mutation_lab.core import SCENARIOS, evaluate, generate
from tripwire.mutation_lab.extended import DESCRIPTIONS as EXT_DESC, EXTENDED, generate_extended
from tripwire.release import Release

CORE_DESC = {
    "unchanged": "no-change control: an exact copy",
    "reordered": "no-change control: same data, rows and columns shuffled",
    "swap": "two samples' protein profiles exchanged",
    "duplicate": "one sample's profile overwritten with another's",
    "disappeared": "one sample's protein profile removed",
    "label_change": "one sample's ER status flipped in clinical.tsv",
    "value_shift": "one ER-alpha value shifted",
}
ALL = {**{s: CORE_DESC.get(s, s) for s in SCENARIOS}, **EXT_DESC}
SCENARIO_NAMES = list(ALL)


def run_one(release_a: str, scenario: str, seed: int, verdicts: bool = True) -> dict:
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="tripwire-lab-"))
    try:
        target = tmp / "release"
        gen = generate_extended if scenario in EXTENDED else generate
        t0 = time.time()
        truth = gen(pathlib.Path(release_a), target, scenario, seed)
        a, b = Release(release_a, name="A"), Release(target, name=f"lab-{scenario}-{seed}")
        observed = detect_changes(a, b)
        secs = time.time() - t0
        doc = build(observed, a, b) if verdicts else None  # the scorecard doesn't show verdicts; skip the cost
        score = evaluate(truth, observed)
        return {"scenario": scenario, "seed": seed, "truth": truth, "observed": observed, "score": score,
                "verdict": doc["verdict"] if doc else None,
                "analyses": {x["id"]: x["verdict"] for x in doc["analyses"]} if doc else {}, "secs": secs}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)  # our own temp folder only


def totals(score: dict) -> tuple[int, int, int]:
    bt = score["by_change_type"]
    return (sum(x["true_positives"] for x in bt), sum(x["false_positives"] for x in bt),
            sum(x["false_negatives"] for x in bt))


def render(st, release_a: str) -> None:
    st.subheader("Mutation Lab")
    st.write("Plant a known change in a copy of release A. Tripwire isn't told what was planted; it has to find it, "
             "and the lab scores what it found against what was planted. Nothing is ever written to release A.")
    if not release_a or not pathlib.Path(release_a, "clinical.tsv").exists():
        st.warning("Set release A in the sidebar first (it needs clinical.tsv and protein_rppa.tsv.gz).")
        return

    c1, c2, c3 = st.columns([3, 1, 1])
    scenario = c1.selectbox("Change to plant", list(ALL), format_func=lambda s: f"{s}: {ALL[s]}", key="lab_scn")
    seed = c2.number_input("Seed", 0, 999, 1, key="lab_seed", help="Same seed, same planted samples.")
    if c3.button("Plant and detect", type="primary", use_container_width=True):
        with st.spinner("Copying release A, planting the change, running Tripwire blind…"):
            try:
                st.session_state["lab_one"] = run_one(release_a, scenario, int(seed))
            except Exception as e:
                st.error(f"Couldn't run this scenario: {e}")
    r = st.session_state.get("lab_one")
    if r:
        tp, fp, fn = totals(r["score"])
        planted = len(r["truth"])
        ok = fp == 0 and fn == 0
        headline = (f"Caught all {planted} planted change(s), no false alarms" if ok and planted else
                    "No change planted, and none reported" if ok else
                    f"Found {tp} of {planted}; {fn} missed, {fp} extra")
        (st.success if ok else st.error)(f"**{r['scenario']}** (seed {r['seed']}): {headline} · {r['secs']:.1f} s")
        st.caption(f"Verdicts for this release: overall **{r['verdict']}** · " +
                   " · ".join(f"{k} {v}" for k, v in r["analyses"].items()))
        found = {(c.change_type, c.file, c.sample_id) for c in r["observed"]}
        want = {(c.change_type, c.file, c.sample_id) for c in r["truth"]}
        rows = [{"planted": f"{c.change_type} · {c.sample_id}", "file": c.file,
                 "found by Tripwire": "✓" if (c.change_type, c.file, c.sample_id) in found else "✗ missed"}
                for c in r["truth"][:50]]
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        extra = [{"reported": f"{c.change_type} · {c.sample_id}", "file": c.file, "evidence": c.evidence}
                 for c in r["observed"] if (c.change_type, c.file, c.sample_id) not in want]
        if extra:
            st.caption("Reported but not planted (false alarms):")
            st.dataframe(pd.DataFrame(extra[:50]), hide_index=True, use_container_width=True)

    st.divider()
    st.subheader("Scorecard: every scenario")
    st.write("Runs every scenario over several seeds and reports, per change type, how many planted changes Tripwire "
             "caught, missed, and how many it reported that weren't planted.")
    seeds = st.slider("Seeds per scenario", 1, 5, 1, key="lab_nseeds",
                      help=f"About {len(SCENARIO_NAMES) * 3} seconds per seed on a laptop.")
    if st.button("Run the full scorecard", key="lab_all"):
        runs, bar = [], st.progress(0.0)
        names = list(ALL)
        for i, s in enumerate(names):
            for k in range(seeds):
                try:
                    runs.append(run_one(release_a, s, k + 1, verdicts=False))
                except Exception as e:  # report, don't hide
                    runs.append({"scenario": s, "seed": k + 1, "error": str(e)})
                bar.progress((i * seeds + k + 1) / (len(names) * seeds))
        st.session_state["lab_all_runs"] = runs
    runs = st.session_state.get("lab_all_runs")
    if runs:
        per = defaultdict(lambda: [0, 0, 0, 0])
        controls_fp, errors = 0, [r for r in runs if "error" in r]
        for r in runs:
            if "error" in r:
                continue
            if not r["truth"]:
                controls_fp += totals(r["score"])[1]
            for x in r["score"]["by_change_type"]:
                p = per[x["change_type"]]
                p[0] += x["expected"]; p[1] += x["true_positives"]; p[2] += x["false_negatives"]; p[3] += x["false_positives"]
        tbl = [{"change type": k, "planted": v[0], "caught": v[1], "missed": v[2], "false alarms": v[3],
                "recall": f"{v[1] / v[0]:.0%}" if v[0] else "n/a",
                "precision": f"{v[1] / (v[1] + v[3]):.0%}" if v[1] + v[3] else "n/a"} for k, v in sorted(per.items())]
        alarms = sum(v[3] for v in per.values())
        ok = [r for r in runs if "error" not in r]
        exact = [r for r in ok if totals(r["score"])[1:] == (0, 0)]
        st.metric("Runs exactly right", f"{len(exact)} of {len(runs)}",
                  help="Every planted change found and nothing extra reported, matched on change type, file and "
                       "sample.")
        st.caption(f"{len(SCENARIO_NAMES)} scenarios × {len(runs) // max(1, len(SCENARIO_NAMES))} seed(s) · "
                   f"{alarms} false alarm(s) in total · {controls_fp} on no-change controls · slowest "
                   f"{max((r['secs'] for r in ok), default=0):.1f} s. Per change type below; a vanished file counts "
                   "every sample in it.")
        st.dataframe(pd.DataFrame(tbl), hide_index=True, use_container_width=True)
        for r in errors:
            st.warning(f"{r['scenario']} seed {r['seed']}: {r['error']}")
        st.caption("Limits: planted changes are synthetic and seeded. A perfect score here does not prove accuracy on "
                   "an unseen release, and a release comparison can't see an error shared by both releases.")
