"""Experimental two-agent intake workflow with an auditable state machine.

    created -> uploaded -> mapping_proposed (AI or manual) -> mapping_reviewed -> approved -> prepared
            -> question_proposed (AI, optional) -> question_confirmed -> [firewall run]
            -> review_pending (or firewall_failed) -> reviewed -> closed

Every step is an explicit call; nothing advances on its own. Changing an earlier input (a new upload, a mapping
decision, a clarification answer, the question text, the releases) invalidates every later step, which then has to be
redone. Model output is a proposal; a person decides. The data owner must confirm the mapping, the uploaded table
must be confirmed as belonging to the candidate release, and a person must confirm the question card. The firewall
verdict is put up for review and never accepted automatically.

What is stored, where: one session folder per workflow (never under /tmp). `upload/` holds the original upload bytes,
`prepared/` the renamed clinical table, `work/` the temporary candidate copy (deleted right after each run, also on
failure), `results/` findings.json. `evidence.json` holds the structured record (metadata, decisions, human answers,
hashes); `audit.jsonl` is a hash-chained event log that holds no cell values, no human free text (only its hash) and
no secrets. `close()` deletes the patient-derived folders. Original files are never modified: their hashes are checked
before and after each run.

Research prototype. A renamed table is not a validated release, and model confidence is not evidence of meaning.
"""
from __future__ import annotations

import copy
import datetime as _dt
import hashlib
import json
import logging
import os
import pathlib
import secrets
import shutil
import tempfile
from typing import Any, Optional

import pandas as pd

from . import agents as ag
from .transform import TransformError, apply_mappings
from .upload import parse_upload

log = logging.getLogger(__name__)

STATES = ("created", "uploaded", "mapping_proposed", "mapping_reviewed", "approved", "prepared",
          "question_proposed", "question_confirmed", "firewall_failed", "review_pending", "reviewed", "closed")
_ORDER = {s: i for i, s in enumerate(STATES)}

MAPPING_DECISIONS = ("accept", "reject", "edit")
REVIEW_DECISIONS = ("accept_result", "reject_result", "request_more_evidence")
LINK_MODES = ("copy", "symlink")
MARKER = ".driftwire-intake-session"
EXCLUDED_FROM_CANDIDATE = {"CHANGES.json"}  # organizer answer keys are never opened, hashed or copied
MAX_QUESTION = 2000
MAX_ANSWER = 4000

APPROVAL_STATEMENT = ("I am the data owner, or act for them. I approve exactly the listed column renames, applied to a "
                      "copy. No values are changed. This does not make the table a validated release.")
BELONGS_STATEMENT = ("The uploaded table is the clinical table of the candidate release given here (the same samples "
                     "and the same field definitions as that release).")
LIMITATIONS = [
    "Research prototype; not a validated release, not clinical, not production.",
    "AI suggestions are proposals. Model confidence is the model's self-report, not proof that two fields mean the "
    "same thing; only the data owner can confirm meaning.",
    "Only metadata (column names, counts, the question text, card descriptions, release file names) is sent to the "
    "model, and only after explicit consent bound to the exact payload. Column names and the question can still be "
    "sensitive.",
    "Only renames are applied. No values, rows, deduplication, imputation or relabelling are changed.",
    "Only the clinical table of the candidate release is replaced; every other candidate file is used as is.",
    "The fixed supported schema covers sampleID, ER status, PAM50 subtype and age. Survival fields are not edited.",
    "A verdict is only produced when both releases, the prepared table and a confirmed question card (or an explicit "
    "baseline-only choice) are present and valid. The verdict needs human review.",
]


class WorkflowError(Exception):
    """A step was called out of order or its preconditions failed. The message names what is missing."""


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _sha_file(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha_text(s: str) -> str:
    return _sha_bytes(s.encode("utf-8"))


def _write_private(path: pathlib.Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(path.name + f".{secrets.token_hex(4)}.part")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _forbidden_roots(allow_system_temp: bool) -> list[pathlib.Path]:
    if allow_system_temp:  # tests only: pytest's tmp_path lives in the system temp folder (/tmp on Linux)
        return []
    roots = {pathlib.Path("/tmp").resolve(), pathlib.Path("/private/tmp"), pathlib.Path("/var/tmp").resolve(),
             pathlib.Path(tempfile.gettempdir()).resolve()}
    return sorted(roots)


def _inside(child: pathlib.Path, parent: pathlib.Path) -> bool:
    return child == parent or parent in child.parents


def safe_session_root(root: Optional[str | os.PathLike] = None, allow_system_temp: bool = False) -> pathlib.Path:
    """Resolve the session root. Default: $DRIFTWIRE_INTAKE_ROOT or ~/.driftwire/intake-sessions (outside the repo,
    so nothing patient-derived can be committed). /tmp and the system temp folder are refused because macOS deletes
    them mid-task; tests may pass allow_system_temp=True to use pytest's tmp_path."""
    raw = root or os.environ.get("DRIFTWIRE_INTAKE_ROOT") or (pathlib.Path.home() / ".driftwire" / "intake-sessions")
    r = pathlib.Path(raw).expanduser().resolve()
    for bad in _forbidden_roots(allow_system_temp):
        if _inside(r, bad):
            raise WorkflowError(f"refusing session root under {bad}: temporary folders can be deleted mid-task")
    return r


def _fingerprint(d: pathlib.Path) -> dict[str, str]:
    """sha256 of every regular file under d (relative path -> hash), skipping organizer answer keys."""
    out = {}
    for p in sorted(d.rglob("*")):
        if p.name in EXCLUDED_FROM_CANDIDATE or not p.is_file():
            continue
        out[p.relative_to(d).as_posix()] = _sha_file(p)
    return out


def _format(filename: str, content_type: Optional[str]) -> str:
    low = filename.lower()
    gz = low.endswith(".gz")
    base = low[:-3] if gz else low
    if base.endswith(".tsv"):
        kind = "tsv"
    elif base.endswith(".csv"):
        kind = "csv"
    else:
        kind = "tsv" if content_type == "text/tab-separated-values" else "csv"
    return kind + (".gz" if gz else "")


class IntakeWorkflow:
    """One intake session. Create with `IntakeWorkflow.create()`, reopen with `IntakeWorkflow.load()`."""

    def __init__(self, session_dir: pathlib.Path, state: dict):
        self.dir = session_dir
        self._s = state
        self._df: Optional[pd.DataFrame] = None
        self.last_result = None  # tripwire.api.Result of the latest successful run (not persisted)

    # ------------------------------------------------------------ lifecycle

    @classmethod
    def create(cls, session_root=None, *, allow_system_temp: bool = False) -> "IntakeWorkflow":
        root = safe_session_root(session_root, allow_system_temp)
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        sid = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(4)
        d = root / sid
        d.mkdir(mode=0o700)
        (d / MARKER).write_text(sid + "\n", encoding="utf-8")
        state = {"session_id": sid, "schema": "driftwire-intake-evidence/0.1", "created_at": _now(), "state": "created",
                 "history": [], "upload": None, "consents": {}, "ai_calls": [], "mapping": None,
                 "clarifications": [], "next_clarification": 1, "mapping_review": None, "approval": None,
                 "prepared": None, "question": None, "question_proposal": None, "question_confirmation": None,
                 "releases": None, "run": None, "runs": [], "review": None, "reviews": [], "closed": None,
                 "audit_head": "0" * 64, "limitations": LIMITATIONS}
        wf = cls(d, state)
        wf._audit("session_created", {"session_id": sid})
        wf._save()
        return wf

    @classmethod
    def load(cls, session_dir, *, allow_system_temp: bool = False) -> "IntakeWorkflow":
        d = pathlib.Path(session_dir).expanduser().resolve()
        safe_session_root(d.parent, allow_system_temp)
        if not (d / MARKER).is_file() or not (d / "evidence.json").is_file():
            raise WorkflowError("not an intake session folder")
        wf = cls(d, json.loads((d / "evidence.json").read_text(encoding="utf-8")))
        shutil.rmtree(d / "work", ignore_errors=True)  # leftovers of an interrupted run
        return wf

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if self._s["state"] != "closed":
            self.close()
        return False

    def close(self, *, purge_findings: bool = False) -> dict:
        """Delete patient-derived data (original upload copy, prepared table, candidate copies; findings too when
        purge_findings). evidence.json and audit.jsonl stay. Irreversible for this session."""
        removed = []
        for sub in ["upload", "prepared", "work"] + (["results"] if purge_findings else []):
            p = self.dir / sub
            if p.exists():
                shutil.rmtree(p)
                removed.append(sub)
        self._df = None
        self._s["closed"] = {"at": _now(), "removed": removed, "findings_kept": not purge_findings}
        self._set_state("closed", "close", {"removed": removed})
        return self._s["closed"]

    def discard(self) -> None:
        """Delete the whole session folder, evidence included."""
        if not (self.dir / MARKER).is_file():
            raise WorkflowError("not an intake session folder; nothing deleted")
        shutil.rmtree(self.dir)

    # ------------------------------------------------------------ state, audit, persistence

    @property
    def state(self) -> str:
        return self._s["state"]

    def evidence(self) -> dict:
        """The structured record: metadata, proposals, decisions, human answers, hashes, run outcomes, reviews."""
        return copy.deepcopy(self._s)

    def status(self) -> dict:
        s = self._s
        return {"state": s["state"], "next": NEXT_ACTIONS.get(s["state"], []),
                "open_clarifications": [c["id"] for c in s["clarifications"] if c["answer"] is None],
                "undecided_proposals": self._undecided(),
                "consents": {k: v["payload_sha256"] for k, v in s["consents"].items()},
                "releases_bound": s["releases"] is not None,
                "verdict": (s["run"] or {}).get("verdict"), "review": s["review"]}

    def _require(self, *states: str) -> None:
        if self._s["state"] == "closed":
            raise WorkflowError("session is closed")
        if self._s["state"] not in states:
            raise WorkflowError(f"not allowed in state {self._s['state']!r}; expected one of {list(states)}")

    def _require_at_least(self, state: str) -> None:
        if self._s["state"] == "closed":
            raise WorkflowError("session is closed")
        if _ORDER[self._s["state"]] < _ORDER[state]:
            raise WorkflowError(f"not allowed in state {self._s['state']!r}; reach {state!r} first")

    def _audit(self, event: str, details: dict) -> None:
        entry = {"seq": len(self._s["history"]) + 1, "at": _now(), "event": event, "state": self._s["state"],
                 "details": details, "prev": self._s["audit_head"]}
        line = json.dumps(entry, sort_keys=True, ensure_ascii=False)
        entry_hash = _sha_text(line)
        with open(self.dir / "audit.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({**entry, "hash": entry_hash}, sort_keys=True, ensure_ascii=False) + "\n")
        os.chmod(self.dir / "audit.jsonl", 0o600)
        self._s["audit_head"] = entry_hash
        self._s["history"].append({"seq": entry["seq"], "at": entry["at"], "event": event, "state": entry["state"]})
        log.info("intake %s: %s", self._s["session_id"], event)  # event names only, never data

    def _save(self) -> None:
        _write_private(self.dir / "evidence.json", json.dumps(self._s, indent=2, ensure_ascii=False).encode("utf-8"))

    def _set_state(self, new: str, event: str, details: Optional[dict] = None) -> None:
        old = self._s["state"]
        self._s["state"] = new
        self._audit(event, {"from": old, "to": new, **(details or {})})
        self._save()

    def _reset_after(self, state: str, reason: str) -> None:
        """Invalidate every step after `state` (no-op when the workflow hasn't gone past it)."""
        s, cur = self._s, self._s["state"]
        if _ORDER[cur] <= _ORDER[state]:
            return
        i = _ORDER[state]
        if i < _ORDER["mapping_proposed"]:
            s["mapping"] = None
            s["clarifications"] = [c for c in s["clarifications"] if c["stage"] != "mapping"]
        if i < _ORDER["mapping_reviewed"]:
            s["mapping_review"] = None
        if i < _ORDER["approved"]:
            s["approval"] = None
        if i < _ORDER["prepared"]:
            s["prepared"] = None
            shutil.rmtree(self.dir / "prepared", ignore_errors=True)
        if i < _ORDER["question_proposed"]:
            s["question_proposal"] = None
            s["clarifications"] = [c for c in s["clarifications"] if c["stage"] != "question"]
        if i < _ORDER["question_confirmed"]:
            s["question_confirmation"] = None
        if i < _ORDER["firewall_failed"]:
            s["run"], s["review"] = None, None
            self.last_result = None
        s["state"] = state
        self._audit("invalidated", {"from": cur, "to": state, "reason": reason})

    def _add_clarification(self, stage: str, origin: str, text: str, about: Optional[str] = None) -> str:
        cid = f"C{self._s['next_clarification']}"
        self._s["next_clarification"] += 1
        self._s["clarifications"].append({"id": cid, "stage": stage, "origin": origin, "text": text, "about": about,
                                          "answer": None, "answered_by": None, "answered_at": None})
        return cid

    # ------------------------------------------------------------ 1. upload

    def upload(self, data: bytes, filename: str, content_type: Optional[str] = None) -> dict:
        """Validate and store the original upload (CSV/TSV, optionally gzip). Re-uploading restarts the workflow."""
        if self._s["state"] == "closed":
            raise WorkflowError("session is closed")
        df = parse_upload(data, filename, content_type)  # raises UploadError
        fmt = _format(filename, content_type)
        if self._s["state"] != "created":
            self._reset_after("uploaded", "new upload")
            shutil.rmtree(self.dir / "upload", ignore_errors=True)
            if self._s["releases"] is not None:  # the "belongs to candidate" confirmation was for the old file
                self._s["releases"] = None
                self._audit("releases_unbound", {"reason": "new upload"})
        _write_private(self.dir / "upload" / f"original.{fmt}", data)
        self._df = df
        self._s["upload"] = {"stored_as": f"upload/original.{fmt}", "format": fmt, "sha256": _sha_bytes(data),
                             "size_bytes": len(data), "filename_sha256": _sha_text(filename),
                             "n_rows": int(len(df)), "n_columns": int(len(df.columns)),
                             "columns": [str(c) for c in df.columns], "at": _now()}
        self._set_state("uploaded", "uploaded", {"format": fmt, "sha256": self._s["upload"]["sha256"],
                                                 "n_rows": len(df), "n_columns": len(df.columns)})
        return copy.deepcopy(self._s["upload"])

    def _frame(self) -> pd.DataFrame:
        if self._df is None:
            u = self._s["upload"]
            p = self.dir / u["stored_as"]
            data = p.read_bytes()
            if _sha_bytes(data) != u["sha256"]:
                raise WorkflowError("stored upload no longer matches its recorded hash")
            self._df = parse_upload(data, p.name)
        return self._df

    def _columns(self) -> list[str]:
        return list(self._s["upload"]["columns"])

    # ------------------------------------------------------------ consent (per agent, bound to the exact payload)

    def preview_ai_payload(self, agent: str) -> dict:
        """What the agent would receive, and its hash. Show this to the user before asking for consent."""
        if agent == ag.PREPARATION:
            self._require_at_least("uploaded")
            u = self._s["upload"]
            payload = ag.preparation_request(u["columns"], u["n_rows"], u["format"])
        elif agent == ag.QUESTION:
            self._require_at_least("prepared")
            if not self._s["question"]:
                raise WorkflowError("enter the research question first (set_question)")
            files = sorted(self._s["releases"]["candidate_files"]) if self._s["releases"] else []
            payload = ag.question_request(self._s["question"]["text"], self._s["prepared"]["columns"], files)
        else:
            raise WorkflowError(f"unknown agent {agent!r}; expected one of {ag.AGENTS}")
        return {"agent": agent, "payload": payload, "sha256": ag.payload_sha256(payload)}

    def grant_consent(self, agent: str, *, granted_by: str, payload_sha256: str) -> dict:
        """Explicit consent for one agent in this workflow, bound to the payload the user was shown."""
        preview = self.preview_ai_payload(agent)
        if not (granted_by or "").strip():
            raise WorkflowError("consent needs the name or role of the person granting it")
        if payload_sha256 != preview["sha256"]:
            raise WorkflowError("the payload changed since it was shown; show it again before consenting")
        self._s["consents"][agent] = {"granted_by": granted_by.strip(), "payload_sha256": payload_sha256, "at": _now()}
        self._audit("consent_granted", {"agent": agent, "payload_sha256": payload_sha256})
        self._save()
        return copy.deepcopy(self._s["consents"][agent])

    def revoke_consent(self, agent: str) -> None:
        if self._s["consents"].pop(agent, None) is not None:
            self._audit("consent_revoked", {"agent": agent})
            self._save()

    def _check_consent(self, agent: str, sha: str) -> None:
        c = self._s["consents"].get(agent)
        if c is None:
            raise ag.AgentError(f"no consent for the {agent} agent in this workflow; nothing was sent")
        if c["payload_sha256"] != sha:
            raise ag.AgentError(f"the {agent} payload changed since consent was given; nothing was sent")

    def _record_call(self, call: ag.AgentCall) -> None:
        self._s["ai_calls"].append({"agent": call.agent, "model": call.model, "payload_sha256": call.payload_sha256,
                                    "sent_fields": sorted(call.request_metadata), "at": _now()})
        self._audit("ai_call", {"agent": call.agent, "model": call.model, "payload_sha256": call.payload_sha256})

    # ------------------------------------------------------------ 2. mapping proposals

    def propose_mappings(self, *, transport=None, model: Optional[str] = None,
                         timeout: int = ag.DEFAULT_TIMEOUT) -> dict:
        """Ask the preparation agent (metadata only, consent required). On any AI failure the workflow is unchanged;
        use start_manual_mapping() instead."""
        self._require_at_least("uploaded")
        preview = self.preview_ai_payload(ag.PREPARATION)
        self._check_consent(ag.PREPARATION, preview["sha256"])
        try:
            raw, call = ag.call_preparation_agent(preview["payload"], consent=True, model=model, timeout=timeout,
                                                  transport=transport)
        except ag.AgentError as exc:
            self._audit("ai_call_failed", {"agent": ag.PREPARATION, "error": str(exc)})
            self._save()
            raise
        v = ag.validate_preparation_output(raw, self._columns())
        self._reset_after("uploaded", "new mapping proposal")
        self._record_call(call)
        self._s["mapping"] = {"origin": "preparation_agent", "proposals": v["proposals"], "rejected": v["rejected"],
                              "agent_errors": v["errors"], "decisions": {}}
        for q in v["clarifications"]:
            self._add_clarification("mapping", "preparation_agent", q)
        for p in v["proposals"]:
            if p["target"] is not None and p["confidence"] != "high":
                self._add_clarification(
                    "mapping", "system",
                    f"The assistant rated '{p['source']}' -> '{p['target']}' as {p['confidence']} confidence. "
                    "What does this column contain, and does it match the definition of the target field?",
                    about=p["source"])
        self._set_state("mapping_proposed", "mapping_proposed",
                        {"origin": "preparation_agent", "n_proposals": len(v["proposals"]),
                         "n_rejected": len(v["rejected"]), "n_clarifications": len(v["clarifications"])})
        return self.mapping_view()

    def start_manual_mapping(self) -> dict:
        """Skip AI: no proposals; the data owner sets each rename with decide_mapping(..., 'edit', target)."""
        self._require_at_least("uploaded")
        self._reset_after("uploaded", "manual mapping")
        self._s["mapping"] = {"origin": "manual", "proposals": [], "rejected": [], "agent_errors": [], "decisions": {}}
        self._set_state("mapping_proposed", "mapping_proposed", {"origin": "manual"})
        return self.mapping_view()

    def mapping_view(self) -> dict:
        m = self._s["mapping"]
        if m is None:
            raise WorkflowError("no mapping proposal yet")
        return {"origin": m["origin"], "source_columns": self._columns(),
                "targets": [{"name": k, "description": v, "required": k in ag.REQUIRED_TARGETS}
                            for k, v in ag.CLINICAL_TARGETS.items()],
                "proposals": copy.deepcopy(m["proposals"]), "rejected": copy.deepcopy(m["rejected"]),
                "agent_errors": list(m["agent_errors"]), "decisions": copy.deepcopy(m["decisions"]),
                "undecided": self._undecided(),
                "clarifications": [copy.deepcopy(c) for c in self._s["clarifications"] if c["stage"] == "mapping"],
                "note": "Confidence is the model's self-report, not evidence of meaning."}

    def _undecided(self) -> list[str]:
        m = self._s["mapping"]
        if not m:
            return []
        return [p["source"] for p in m["proposals"] if p["source"] not in m["decisions"]]

    # ------------------------------------------------------------ 3. review: decisions and clarification answers

    def decide_mapping(self, source: str, decision: str, target: Optional[str] = None, *,
                       decided_by: str, note: str = "") -> dict:
        """accept: take the proposal as is (may be 'no target'); reject: keep the column unmapped;
        edit: map to `target` (the manual path)."""
        self._require_at_least("mapping_proposed")
        if source not in self._columns():
            raise WorkflowError("source is not a column of the upload")
        if decision not in MAPPING_DECISIONS:
            raise WorkflowError(f"decision must be one of {MAPPING_DECISIONS}")
        if not (decided_by or "").strip():
            raise WorkflowError("a decision needs the name or role of the person making it")
        prop = next((p for p in self._s["mapping"]["proposals"] if p["source"] == source), None)
        if decision == "accept":
            if prop is None:
                raise WorkflowError("there is no proposal to accept for this column; use 'edit'")
            tgt = prop["target"]
        elif decision == "edit":
            if target not in ag.CLINICAL_TARGETS:
                raise WorkflowError("target is not in the fixed supported schema")
            tgt = target
        else:
            tgt = None
        self._reset_after("mapping_proposed", "mapping decision changed")
        note = (note or "").strip()[:MAX_ANSWER]
        self._s["mapping"]["decisions"][source] = {"decision": decision, "target": tgt, "note": note,
                                                    "decided_by": decided_by.strip(), "at": _now(),
                                                    "proposed_target": prop["target"] if prop else None}
        self._audit("mapping_decided", {"source": source, "decision": decision, "target": tgt,
                                        "note_sha256": _sha_text(note) if note else None})
        self._save()
        return copy.deepcopy(self._s["mapping"]["decisions"][source])

    def clarifications(self, stage: Optional[str] = None) -> list[dict]:
        return [copy.deepcopy(c) for c in self._s["clarifications"] if stage in (None, c["stage"])]

    def answer_clarification(self, clarification_id: str, answer: str, *, answered_by: str) -> dict:
        c = next((c for c in self._s["clarifications"] if c["id"] == clarification_id), None)
        if c is None:
            raise WorkflowError("unknown clarification")
        if self._s["state"] == "closed":
            raise WorkflowError("session is closed")
        text = (answer or "").strip()
        if not text:
            raise WorkflowError("an answer cannot be empty; unresolved questions are never approved silently")
        if not (answered_by or "").strip():
            raise WorkflowError("an answer needs the name or role of the person giving it")
        self._reset_after("mapping_proposed" if c["stage"] == "mapping" else "question_proposed",
                          "clarification answered")
        c.update(answer=text[:MAX_ANSWER], answered_by=answered_by.strip(), answered_at=_now())
        self._audit("clarification_answered", {"id": c["id"], "stage": c["stage"], "answer_sha256": _sha_text(text)})
        self._save()
        return copy.deepcopy(c)

    def _renames(self) -> list[dict]:
        d = self._s["mapping"]["decisions"]
        return [{"source": s, "target": v["target"]} for s, v in d.items()
                if v["target"] is not None and v["target"] != s]

    def complete_mapping_review(self, *, reviewed_by: str) -> dict:
        """Close the review. Fails (and changes nothing) while any proposal is undecided, any mapping clarification
        is unanswered, the renames collide, or sampleID would be missing."""
        self._require("mapping_proposed")
        if not (reviewed_by or "").strip():
            raise WorkflowError("the review needs the name or role of the reviewer")
        problems = []
        und = self._undecided()
        if und:
            problems.append(f"undecided proposals: {', '.join(und)}")
        open_c = [c["id"] for c in self._s["clarifications"] if c["stage"] == "mapping" and c["answer"] is None]
        if open_c:
            problems.append(f"unanswered clarifications: {', '.join(open_c)}")
        renames = self._renames()
        out_cols: list[str] = []
        try:
            out_cols = list(apply_mappings(self._frame().iloc[:0], renames, approval=True,
                                           allowed_targets=frozenset(ag.CLINICAL_TARGETS)).columns)
        except TransformError as exc:
            problems.append(str(exc))
        if out_cols:
            for t in ag.REQUIRED_TARGETS:
                if t not in out_cols:
                    problems.append(f"required field {t} is not mapped")
        if problems:
            self._audit("mapping_review_blocked", {"n_problems": len(problems)})
            self._save()
            raise WorkflowError("mapping review is not complete: " + "; ".join(problems))
        renamed = {r["source"] for r in renames}
        self._s["mapping_review"] = {"reviewed_by": reviewed_by.strip(), "at": _now(), "renames": renames,
                                     "renames_sha256": ag.payload_sha256(renames), "output_columns": out_cols,
                                     "unmapped_columns": [c for c in self._columns() if c not in renamed]}
        self._set_state("mapping_reviewed", "mapping_reviewed", {"n_renames": len(renames)})
        return copy.deepcopy(self._s["mapping_review"])

    # ------------------------------------------------------------ 4. approval (data owner) and 5. prepared data

    def approve(self, *, data_owner_confirmed: bool, approved_by: str) -> dict:
        self._require("mapping_reviewed")
        if data_owner_confirmed is not True:
            raise WorkflowError("data owner confirmation is mandatory: " + APPROVAL_STATEMENT)
        if not (approved_by or "").strip():
            raise WorkflowError("approval needs the data owner's name or role")
        r = self._s["mapping_review"]
        self._s["approval"] = {"data_owner_confirmed": True, "approved_by": approved_by.strip(), "at": _now(),
                               "statement": APPROVAL_STATEMENT, "renames": copy.deepcopy(r["renames"]),
                               "renames_sha256": r["renames_sha256"]}
        self._set_state("approved", "approved", {"renames_sha256": r["renames_sha256"]})
        return copy.deepcopy(self._s["approval"])

    def prepare(self) -> dict:
        """Apply exactly the approved renames to a copy and write prepared/clinical.tsv. Values are checked to be
        unchanged, including after writing and reading the file back."""
        self._require("approved")
        a = self._s["approval"]
        if ag.payload_sha256(a["renames"]) != a["renames_sha256"]:
            raise WorkflowError("approved renames do not match their recorded hash")
        df = self._frame()
        out = apply_mappings(df, a["renames"], approval=True, allowed_targets=frozenset(ag.CLINICAL_TARGETS))
        if out.shape != df.shape or not out.set_axis(list(df.columns), axis=1).equals(df):
            raise WorkflowError("renaming changed values; nothing was written")
        path = self.dir / "prepared" / "clinical.tsv"
        _write_private(path, out.to_csv(sep="\t", index=False, lineterminator="\n").encode("utf-8"))
        back = pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False)
        if list(back.columns) != list(out.columns) or not back.equals(out):
            shutil.rmtree(path.parent, ignore_errors=True)
            raise WorkflowError("prepared file did not round-trip exactly; nothing kept")
        ids = out["sampleID"]
        self._s["prepared"] = {"path": "prepared/clinical.tsv", "sha256": _sha_file(path), "n_rows": int(len(out)),
                               "columns": list(out.columns), "renames": copy.deepcopy(a["renames"]),
                               "values_preserved": True, "n_unique_sample_ids": int(ids.nunique()),
                               "n_blank_sample_ids": int((ids.str.strip() == "").sum()), "at": _now()}
        self._set_state("prepared", "prepared", {"sha256": self._s["prepared"]["sha256"]})
        return copy.deepcopy(self._s["prepared"])

    # ------------------------------------------------------------ 6. research question

    def set_question(self, text: str) -> dict:
        """Enter or change the research question. A change invalidates any interpretation and confirmation."""
        self._require_at_least("uploaded")
        t = (text or "").strip()
        if not t:
            raise WorkflowError("the question cannot be empty")
        if len(t) > MAX_QUESTION:
            raise WorkflowError(f"the question is longer than {MAX_QUESTION} characters")
        if self._s["question"] and self._s["question"]["text"] == t:
            return copy.deepcopy(self._s["question"])
        self._reset_after("prepared", "question changed")
        self._s["question"] = {"text": t, "sha256": _sha_text(t), "at": _now()}
        self._audit("question_set", {"question_sha256": self._s["question"]["sha256"]})
        self._save()
        return copy.deepcopy(self._s["question"])

    def propose_question(self, *, transport=None, model: Optional[str] = None,
                         timeout: int = ag.DEFAULT_TIMEOUT) -> dict:
        """Ask the question agent (separate call and consent). Unknown card IDs become None."""
        self._require_at_least("prepared")
        preview = self.preview_ai_payload(ag.QUESTION)
        self._check_consent(ag.QUESTION, preview["sha256"])
        try:
            raw, call = ag.call_question_agent(preview["payload"], consent=True, model=model, timeout=timeout, transport=transport)
        except ag.AgentError as exc:
            self._audit("ai_call_failed", {"agent": ag.QUESTION, "error": str(exc)})
            self._save()
            raise
        from tripwire.questions import BY_ID
        v = ag.validate_question_output(raw, list(BY_ID))
        self._reset_after("prepared", "new question proposal")
        self._record_call(call)
        self._s["question_proposal"] = {"card_id": v["card_id"], "explanation": v["explanation"],
                                        "agent_errors": v["errors"], "question_sha256": self._s["question"]["sha256"],
                                        "at": _now()}
        for q in v["clarifications"]:
            self._add_clarification("question", "question_agent", q)
        self._set_state("question_proposed", "question_proposed", {"card_id": v["card_id"],
                                                                   "n_errors": len(v["errors"])})
        return self.question_view()

    def question_view(self) -> dict:
        from tripwire.questions import BY_ID
        p = self._s["question_proposal"]
        card = BY_ID.get(p["card_id"]) if p and p["card_id"] else None
        return {"question": copy.deepcopy(self._s["question"]), "proposal": copy.deepcopy(p),
                "proposed_card": next((c for c in ag.card_catalogue() if card and c["id"] == card.id), None),
                "supported_cards": ag.card_catalogue(),
                "clarifications": [copy.deepcopy(c) for c in self._s["clarifications"] if c["stage"] == "question"],
                "confirmation": copy.deepcopy(self._s["question_confirmation"])}

    def confirm_question(self, card_id: Optional[str], *, confirmed_by: str, baseline_only: bool = False) -> dict:
        """A person confirms the supported card (it may differ from the proposal), or chooses baseline_only=True
        with card_id=None to compare the reference analyses without a question card."""
        from tripwire.questions import BY_ID
        self._require_at_least("prepared")
        if not (confirmed_by or "").strip():
            raise WorkflowError("confirmation needs the name or role of the person confirming")
        if baseline_only:
            if card_id is not None:
                raise WorkflowError("baseline-only means no question card; pass card_id=None")
        else:
            if card_id is None:
                raise WorkflowError("choose a supported card, or baseline_only=True; no card is never assumed")
            if not isinstance(card_id, str) or card_id not in BY_ID:
                raise WorkflowError("not a supported question card")
            if not self._s["question"]:
                raise WorkflowError("enter the research question first (set_question)")
        open_c = [c["id"] for c in self._s["clarifications"] if c["stage"] == "question" and c["answer"] is None]
        if open_c:
            raise WorkflowError(f"unanswered question clarifications: {', '.join(open_c)}")
        p = self._s["question_proposal"]
        q = self._s["question"]
        if p and q and p["question_sha256"] != q["sha256"]:
            raise WorkflowError("the proposal is for an older question; ask again or confirm manually")
        self._reset_after("question_proposed" if p else "prepared", "question re-confirmed")
        self._s["question_confirmation"] = {
            "card_id": card_id, "baseline_only": bool(baseline_only), "confirmed_by": confirmed_by.strip(),
            "question_sha256": q["sha256"] if q else None, "at": _now(),
            "proposed_card_id": p["card_id"] if p else None,
            "matches_proposal": (p["card_id"] == card_id) if p else None}
        self._set_state("question_confirmed", "question_confirmed",
                        {"card_id": card_id, "baseline_only": bool(baseline_only),
                         "matches_proposal": self._s["question_confirmation"]["matches_proposal"]})
        return copy.deepcopy(self._s["question_confirmation"])

    # ------------------------------------------------------------ 7. releases and the firewall run

    def bind_releases(self, trusted_dir, candidate_dir, *, upload_belongs_to_candidate: bool,
                      confirmed_by: str) -> dict:
        """Name trusted release A and candidate release B. The person must confirm the upload is B's clinical
        table. Both folders are fingerprinted; they must be unchanged at run time and after it."""
        self._require_at_least("uploaded")
        if upload_belongs_to_candidate is not True:
            raise WorkflowError("confirm that the uploaded table belongs to the candidate release: " + BELONGS_STATEMENT)
        if not (confirmed_by or "").strip():
            raise WorkflowError("confirmation needs the name or role of the person confirming")
        a, b = pathlib.Path(trusted_dir).expanduser().resolve(), pathlib.Path(candidate_dir).expanduser().resolve()
        for p, what in ((a, "trusted release"), (b, "candidate release")):
            if not p.is_dir():
                raise WorkflowError(f"{what} folder not found")
            if _inside(p, self.dir) or _inside(self.dir, p):
                raise WorkflowError(f"{what} folder overlaps the session folder")
        if _inside(a, b) or _inside(b, a):
            raise WorkflowError("trusted and candidate releases must be separate folders")
        if not (a / "clinical.tsv").is_file():
            raise WorkflowError("trusted release has no clinical.tsv")
        from tripwire.release import default_name
        fa, fb = _fingerprint(a), _fingerprint(b)
        self._reset_after("question_confirmed", "releases changed")
        self._s["releases"] = {"trusted": str(a), "candidate": str(b), "trusted_name": default_name(a),
                               "candidate_name": default_name(b), "trusted_fingerprint": fa,
                               "candidate_fingerprint": fb, "candidate_files": sorted(fb),
                               "candidate_had_clinical": "clinical.tsv" in fb, "confirmed_by": confirmed_by.strip(),
                               "belongs_statement": BELONGS_STATEMENT, "at": _now()}
        self._audit("releases_bound", {"n_trusted_files": len(fa), "n_candidate_files": len(fb)})
        self._save()
        return copy.deepcopy(self._s["releases"])

    def run_firewall(self, *, link_mode: str = "copy", validate: bool = False,
                     challenge_dir: Optional[str] = None) -> dict:
        """Build a temporary candidate copy (B's files, with clinical.tsv replaced by the prepared table), run
        tripwire.api.check with the confirmed card, delete the copy, and put the result up for review.

        Raises WorkflowError (no verdict, state unchanged) when inputs are missing or invalid. An engine failure is
        recorded as state 'firewall_failed' with no verdict. link_mode='symlink' links B's unchanged files instead
        of copying them (less disk); the engine only reads them either way."""
        self._require("question_confirmed", "firewall_failed")
        if link_mode not in LINK_MODES:
            raise WorkflowError(f"link_mode must be one of {LINK_MODES}")
        s = self._s
        missing = []
        if not s["releases"]:
            missing.append("releases not bound (bind_releases)")
        if not s["question_confirmation"]:
            missing.append("question card not confirmed")
        prepared = self.dir / "prepared" / "clinical.tsv"
        if not s["prepared"] or not prepared.is_file() or _sha_file(prepared) != s["prepared"]["sha256"]:
            missing.append("prepared table missing or changed")
        if missing:
            raise WorkflowError("cannot run the firewall: " + "; ".join(missing))
        rel, qc = s["releases"], s["question_confirmation"]
        run_id = f"R{len(s['runs']) + 1}"
        record = {"run_id": run_id, "at": _now(), "status": "failed", "verdict": None, "question_verdict": None,
                  "card_id": qc["card_id"], "baseline_only": qc["baseline_only"], "link_mode": link_mode,
                  "error": None, "warnings": [], "review": "pending"}
        a, b = pathlib.Path(rel["trusted"]), pathlib.Path(rel["candidate"])
        try:
            if _fingerprint(a) != rel["trusted_fingerprint"] or _fingerprint(b) != rel["candidate_fingerprint"]:
                record["error"] = "release files changed since they were bound; bind them again"
        except OSError:
            record["error"] = "release folders could not be read"
        work = self.dir / "work" / run_id
        result = None
        if record["error"] is None:
            try:
                cand = work / "candidate"
                record["candidate_build"] = _build_candidate(b, cand, prepared, link_mode)
                record["warnings"] += _overlap_warnings(b, prepared, record)
                from tripwire.api import check
                result = check(a, cand, question=qc["card_id"], name_a=rel["trusted_name"],
                               name_b=rel["candidate_name"])
            except Exception as exc:  # engine or build failure: no verdict; message withheld (may quote data)
                record["error"] = f"firewall run failed ({type(exc).__name__})"
                result = None
            finally:
                shutil.rmtree(work, ignore_errors=True)
                if work.exists():
                    record["warnings"].append("temporary candidate copy could not be fully deleted")
                    result = None
                    record["error"] = record["error"] or "cleanup of the candidate copy failed"
        try:
            unchanged = (_fingerprint(a) == rel["trusted_fingerprint"] and
                         _fingerprint(b) == rel["candidate_fingerprint"] and
                         _sha_file(self.dir / s["upload"]["stored_as"]) == s["upload"]["sha256"])
        except OSError:
            unchanged = False
        record["originals_unchanged"] = unchanged
        if not unchanged:
            result = None
            record["error"] = record["error"] or "original files changed during the run; no verdict"
        if result is not None:
            from tripwire.review import review_status
            rdir = self.dir / "results" / run_id
            body = json.dumps(result.doc, indent=2).encode("utf-8")
            _write_private(rdir / "findings.json", body)
            rs = review_status(result.doc)
            record.update(status="complete", verdict=result.verdict, seconds=round(result.seconds, 2),
                          question_verdict=result.questions.get(qc["card_id"]) if qc["card_id"] else None,
                          n_findings=len(result.findings), flagged_for_review=rs["flagged"],
                          findings_path=f"results/{run_id}/findings.json", findings_sha256=_sha_bytes(body))
            if validate:
                try:
                    record["validation_errors"] = result.validate(challenge_dir)
                except Exception as exc:
                    record["validation_errors"] = [f"validator could not run ({type(exc).__name__})"]
            self.last_result = result
        s["run"] = record
        s["runs"].append({k: record[k] for k in ("run_id", "at", "status", "verdict", "error")})
        s["review"] = None
        if result is not None:
            self._set_state("review_pending", "firewall_complete", {"run_id": run_id, "verdict": record["verdict"]})
        else:
            self._set_state("firewall_failed", "firewall_failed", {"run_id": run_id, "error": record["error"]})
        return copy.deepcopy(record)

    def findings(self) -> dict:
        """The latest findings.json document (findings stay local; they are never sent to a model)."""
        r = self._s["run"]
        if not r or r["status"] != "complete":
            raise WorkflowError("no completed run")
        return json.loads((self.dir / r["findings_path"]).read_text(encoding="utf-8"))

    # ------------------------------------------------------------ 8. human review (separate, never automatic)

    def record_review(self, decision: str, *, reason: str, reviewer_role: str) -> dict:
        self._require("review_pending")
        if decision not in REVIEW_DECISIONS:
            raise WorkflowError(f"decision must be one of {REVIEW_DECISIONS}")
        reason, role = (reason or "").strip(), (reviewer_role or "").strip()
        if not reason or not role:
            raise WorkflowError("a review needs a reason and the reviewer's role")
        rev = {"run_id": self._s["run"]["run_id"], "decision": decision, "reason": reason[:MAX_ANSWER],
               "reviewer_role": role, "at": _now(), "verdict_reviewed": self._s["run"]["verdict"],
               "repairs_applied": False}
        self._s["reviews"].append(rev)
        self._s["review"] = rev
        self._s["run"]["review"] = decision
        details = {"run_id": rev["run_id"], "decision": decision, "reason_sha256": _sha_text(reason)}
        if decision == "request_more_evidence":
            self._audit("review_recorded", details)
            self._save()
        else:
            self._set_state("reviewed", "review_recorded", details)
        return copy.deepcopy(rev)


NEXT_ACTIONS = {
    "created": ["upload"],
    "uploaded": ["preview_ai_payload('preparation') + grant_consent + propose_mappings", "start_manual_mapping",
                 "bind_releases", "set_question"],
    "mapping_proposed": ["decide_mapping", "answer_clarification", "complete_mapping_review"],
    "mapping_reviewed": ["approve", "decide_mapping (reopens review)"],
    "approved": ["prepare"],
    "prepared": ["set_question", "preview_ai_payload('question') + grant_consent + propose_question",
                 "confirm_question", "bind_releases"],
    "question_proposed": ["answer_clarification", "confirm_question", "set_question"],
    "question_confirmed": ["bind_releases", "run_firewall"],
    "firewall_failed": ["run_firewall", "bind_releases"],
    "review_pending": ["record_review"],
    "reviewed": ["close"],
}


def _build_candidate(src: pathlib.Path, dst: pathlib.Path, prepared: pathlib.Path, link_mode: str) -> dict:
    dst.mkdir(parents=True, mode=0o700)
    kept = []
    for entry in sorted(src.iterdir()):
        if entry.name == "clinical.tsv" or entry.name in EXCLUDED_FROM_CANDIDATE:
            continue
        target = dst / entry.name
        if link_mode == "symlink":
            target.symlink_to(entry.resolve(), target_is_directory=entry.is_dir())
        elif entry.is_dir():
            shutil.copytree(entry, target, ignore=shutil.ignore_patterns(*EXCLUDED_FROM_CANDIDATE))
        else:
            shutil.copy2(entry, target)
        kept.append(entry.name)
    shutil.copyfile(prepared, dst / "clinical.tsv")
    os.chmod(dst / "clinical.tsv", 0o600)
    return {"replaced": "clinical.tsv", "candidate_had_clinical": (src / "clinical.tsv").is_file(),
            "kept_from_candidate": kept, "excluded": sorted(EXCLUDED_FROM_CANDIDATE)}


def _overlap_warnings(b: pathlib.Path, prepared: pathlib.Path, record: dict) -> list[str]:
    """Local, counts-only check that the upload looks like B's clinical table. Never sent anywhere."""
    if not (b / "clinical.tsv").is_file():
        return []
    try:
        old = set(pd.read_csv(b / "clinical.tsv", sep="\t", dtype=str, usecols=["sampleID"])["sampleID"].dropna())
        new = set(pd.read_csv(prepared, sep="\t", dtype=str, keep_default_na=False, usecols=["sampleID"])["sampleID"])
    except (ValueError, OSError, pd.errors.ParserError):
        return ["could not compare sample IDs with the candidate's own clinical.tsv"]
    record["sample_overlap"] = {"n_uploaded": len(new), "n_candidate_clinical": len(old), "n_shared": len(new & old)}
    if not new & old:
        return ["no uploaded sample ID appears in the candidate release's own clinical.tsv; check that the upload "
                "really belongs to this release"]
    return []
