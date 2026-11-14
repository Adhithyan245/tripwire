"""CLI demo of the two-agent intake workflow on entirely synthetic data.

    python -m intake_prototype demo                         # scripted stand-in agents, no network, no key
    OPENAI_API_KEY=... python -m intake_prototype demo --ai openai --consent   # real calls, metadata only

The demo builds a synthetic trusted release A and candidate release B (B arrives without a clinical.tsv; its clinical
table comes as a separate CSV upload with non-standard column names and four relabelled subtypes), walks every step
of the workflow, runs the real Driftwire engine on a temporary candidate copy, leaves the result pending review, then
deletes all patient-shaped data (here: synthetic) and the synthetic inputs. In the demo the script stands in for the
human; every scripted human answer is labelled DEMO. Scripted agents are fixed JSON, not a model.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import secrets
import shutil
import sys

import numpy as np
import pandas as pd

from . import agents as ag
from .workflow import IntakeWorkflow, safe_session_root

ER, PAM50 = "breast_carcinoma_estrogen_receptor_status", "PAM50Call_RNAseq"
SUBTYPES = ["LumA", "LumB", "Basal", "Her2", "Normal"]
UPLOAD_HEADERS = {"sampleID": "Sample Barcode", ER: "ER status (IHC)", PAM50: "Subtype call", "age": "Age at dx"}
QUESTION_TEXT = "What is the PAM50 subtype mix of primary tumors in the new release?"


def make_synthetic_inputs(base: pathlib.Path, n: int = 120, seed: int = 7) -> dict:
    """Synthetic A, B (no clinical.tsv) and an upload CSV for B. No real data; barcodes use the fake site ZZ."""
    rng = np.random.default_rng(seed)
    ids = [f"TCGA-ZZ-{i:04d}-01" for i in range(n)] + [f"TCGA-ZZ-{i:04d}-11" for i in range(5)]
    clin = pd.DataFrame({"sampleID": ids, ER: ["Positive" if i % 3 else "Negative" for i in range(len(ids))],
                         PAM50: [SUBTYPES[i % 5] for i in range(len(ids))],
                         "age": rng.integers(30, 80, len(ids))})
    er_pos = clin[ER].eq("Positive").to_numpy()
    protein = pd.DataFrame([np.where(er_pos, 2.0, -1.0) + rng.normal(0, .3, len(ids)), rng.normal(0, 1, len(ids))],
                           index=["ERALPHA", "AKT"], columns=ids)
    protein.index.name = "sample"
    a, b = base / "release-A", base / "release-B"
    for d in (a, b):
        d.mkdir(parents=True)
        protein.to_csv(d / "protein_rppa.tsv.gz", sep="\t", compression={"method": "gzip", "mtime": 0})
    clin.to_csv(a / "clinical.tsv", sep="\t", index=False, lineterminator="\n")
    new = clin.copy()
    new.loc[[0, 5, 10, 15], PAM50] = "Basal"  # four relabelled subtypes the firewall should notice
    upload = base / "release-B-clinical-upload.csv"
    new.rename(columns=UPLOAD_HEADERS).to_csv(upload, index=False, lineterminator="\n")
    return {"trusted": a, "candidate": b, "upload": upload}


def scripted_transport(url: str, headers: dict, body: bytes, timeout: int) -> bytes:
    """Stand-in for both agents: fixed answers chosen from the metadata in the request. Not a model."""
    req = json.loads(body)
    system, user = req["messages"][0]["content"], json.loads(req["messages"][1]["content"])
    if system == ag.PREPARATION_SYSTEM:
        reverse = {v: k for k, v in UPLOAD_HEADERS.items()}
        out = {"mappings": [{"source": c, "target": reverse.get(c), "rationale": "name similarity (scripted)",
                             "confidence": "medium" if c == "ER status (IHC)" else "high"}
                            for c in user["source_columns"]],
               "clarification_questions": ["Is 'ER status (IHC)' defined the same way as the trusted release's "
                                           "ER status field?"]}
    else:
        q = user["question"].lower()
        out = {"card_id": "subtype_mix" if "subtype" in q and "mix" in q else None,
               "explanation": "The question asks for subtype shares (scripted).", "clarification_questions": []}
    return json.dumps({"choices": [{"message": {"content": json.dumps(out)}}]}).encode("utf-8")


def _say(msg: str) -> None:
    print(msg, flush=True)


def run_demo(args) -> int:
    root = safe_session_root(args.session_root)
    inputs_dir = root / f"demo-inputs-{secrets.token_hex(3)}"
    transport = scripted_transport if args.ai == "scripted" else None
    if args.ai == "openai" and not args.consent:
        _say("Refusing to call OpenAI without --consent (only column names, counts, the question and card "
             "descriptions of the SYNTHETIC demo data would be sent).")
        return 2
    wf = None
    try:
        paths = make_synthetic_inputs(inputs_dir)
        wf = IntakeWorkflow.create(root)
        _say(f"session: {wf.dir}\n[{wf.state}]")
        wf.upload(paths["upload"].read_bytes(), paths["upload"].name)
        _say(f"[{wf.state}] uploaded synthetic CSV ({wf.evidence()['upload']['n_rows']} rows)")

        prev = wf.preview_ai_payload(ag.PREPARATION)
        _say("preparation agent would receive (metadata only):\n" + json.dumps(prev["payload"]["source_columns"]))
        wf.grant_consent(ag.PREPARATION, granted_by="DEMO data owner", payload_sha256=prev["sha256"])
        view = wf.propose_mappings(transport=transport)
        _say(f"[{wf.state}] {len(view['proposals'])} proposals, {len(view['rejected'])} rejected, "
             f"{len(view['clarifications'])} clarifications ({'scripted' if transport else 'OpenAI'})")
        for p in view["proposals"]:
            if p["target"] is not None:
                wf.decide_mapping(p["source"], "accept", decided_by="DEMO data owner")
            else:
                wf.decide_mapping(p["source"], "reject", decided_by="DEMO data owner")
            _say(f"   {p['source']!r} -> {p['target']!r} ({p['confidence']}): decided")
        for c in view["clarifications"]:
            wf.answer_clarification(c["id"], "DEMO answer: synthetic column; same definition as the target field.",
                                    answered_by="DEMO data owner")
            _say(f"   answered {c['id']}: {c['text']}")
        wf.complete_mapping_review(reviewed_by="DEMO data owner")
        wf.approve(data_owner_confirmed=True, approved_by="DEMO data owner")
        prep = wf.prepare()
        _say(f"[{wf.state}] prepared clinical.tsv, columns {prep['columns']}, values preserved")

        wf.bind_releases(paths["trusted"], paths["candidate"], upload_belongs_to_candidate=True,
                         confirmed_by="DEMO data owner")
        wf.set_question(args.question)
        prev = wf.preview_ai_payload(ag.QUESTION)
        wf.grant_consent(ag.QUESTION, granted_by="DEMO researcher", payload_sha256=prev["sha256"])
        qv = wf.propose_question(transport=transport)
        proposed = qv["proposal"]["card_id"]
        _say(f"[{wf.state}] question agent proposes {proposed!r}: {qv['proposal']['explanation']}")
        for c in qv["clarifications"]:
            wf.answer_clarification(c["id"], "DEMO answer: primary tumors only.", answered_by="DEMO researcher")
        if proposed:
            wf.confirm_question(proposed, confirmed_by="DEMO researcher")
        else:
            _say("   no supported card proposed; the DEMO human chooses the baseline-only comparison")
            wf.confirm_question(None, confirmed_by="DEMO researcher", baseline_only=True)
        _say(f"[{wf.state}] confirmed {wf.evidence()['question_confirmation']['card_id']!r}")

        run = wf.run_firewall(link_mode=args.link_mode)
        if run["status"] != "complete":
            _say(f"[{wf.state}] no verdict: {run['error']}")
        else:
            _say(f"[{wf.state}] verdict {run['verdict']}; question verdict {run['question_verdict']}; "
                 f"{run['n_findings']} finding(s); originals unchanged: {run['originals_unchanged']}; "
                 f"review: {run['review']}")
            _say("   the verdict stays pending until a person calls record_review(); the demo leaves it pending")
        closed = wf.close(purge_findings=not args.keep_findings)
        _say(f"[{wf.state}] removed {closed['removed']}; evidence kept at {wf.dir / 'evidence.json'}")
        return 0 if run["status"] == "complete" else 1
    finally:
        if wf is not None and wf.state != "closed":  # a step failed: still delete the session's data folders
            wf.close(purge_findings=True)
        shutil.rmtree(inputs_dir, ignore_errors=True)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m intake_prototype", description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo", help="run the full workflow on synthetic data")
    d.add_argument("--session-root", help="where sessions go (default ~/.driftwire/intake-sessions; never /tmp)")
    d.add_argument("--ai", choices=["scripted", "openai"], default="scripted")
    d.add_argument("--consent", action="store_true", help="consent to send the synthetic metadata to OpenAI")
    d.add_argument("--question", default=QUESTION_TEXT)
    d.add_argument("--link-mode", choices=["copy", "symlink"], default="copy")
    d.add_argument("--keep-findings", action="store_true", help="keep findings.json after closing")
    args = p.parse_args(argv)
    return run_demo(args)


if __name__ == "__main__":
    sys.exit(main())
