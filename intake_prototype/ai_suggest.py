"""AI-assisted column mapping suggestions via OpenAI Chat Completions.

All network access is gated on an explicit ``consent=True`` argument.
Only column names and aggregate dimensions are sent; never raw data rows.
"""

from __future__ import annotations

import json
import logging
import os
import ssl
import urllib.request
import urllib.error
from typing import Any, Optional

from .schema import ALLOWED_TARGETS

logger = logging.getLogger(__name__)

OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4.1-mini"
DEFAULT_TIMEOUT = 30

_SYSTEM_PROMPT = (
    "You are a data-mapping assistant for a biomedical research project. "
    "The user will provide column names from an uploaded dataset and a list of "
    "expected target column names. Suggest the most likely mapping from each "
    "source column to one target column (or null if no match). Also suggest "
    "which question card ID (from a provided list) best fits this data, or null. "
    "Return ONLY valid JSON with this exact schema:\n"
    '{"mappings": [{"source": "<col>", "target": "<target_or_null>", '
    '"confidence": "<high|medium|low>"}], '
    '"question_card_id": "<id_or_null>", '
    '"clarification_questions": ["<question>", ...]}\n'
    "Rules:\n"
    "- Each source column maps to at most one target.\n"
    "- Each target can be mapped to by at most one source.\n"
    "- Only use target names from the provided allowed set.\n"
    "- Only use question card IDs from the provided list.\n"
    "- If unsure, set confidence to 'low' and add a clarification question.\n"
    "- Never invent target names or card IDs not in the lists.\n"
    "- These are suggestions only, not decisions."
)


def suggest_mappings(
    source_columns: list[str],
    num_rows: int,
    allowed_targets: Optional[frozenset[str]] = None,
    card_ids: Optional[list[str]] = None,
    consent: bool = False,
    model: str = DEFAULT_MODEL,
    timeout: int = DEFAULT_TIMEOUT,
    filename: Optional[str] = None,
    research_question: str = "",
) -> dict[str, Any]:
    """Call OpenAI to suggest column mappings.

    Parameters
    ----------
    source_columns : list[str]
        Column names from the uploaded file.
    num_rows : int
        Number of data rows (aggregate dimension only).
    allowed_targets : frozenset[str], optional
        Valid target column names. Defaults to ALLOWED_TARGETS.
    card_ids : list[str], optional
        Valid question card IDs. Defaults to tripwire.questions.BY_ID keys.
    consent : bool
        **Must be True**. Caller must explicitly consent to sending metadata
        to OpenAI. If False, raises ValueError with no network activity.
    model : str
        OpenAI model to use.
    timeout : int
        Request timeout in seconds.
    filename : str, optional
        Original filename (included in prompt for context).

    Returns
    -------
    dict
        Raw (unvalidated) parsed JSON from the model.

    Raises
    ------
    ValueError
        If consent is False or inputs are invalid.
    RuntimeError
        On network or API errors.
    """
    if not consent:
        raise ValueError(
            "Explicit consent is required to send metadata to OpenAI. "
            "Set consent=True after the user has opted in."
        )

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY environment variable is not set. "
            "AI suggestions require an API key."
        )

    if allowed_targets is None:
        allowed_targets = ALLOWED_TARGETS
    if card_ids is None:
        card_ids = _get_card_ids()

    user_msg = _build_user_message(
        source_columns, num_rows, allowed_targets, card_ids, filename, research_question
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.0,
        "max_tokens": 2048,
    }

    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    req = urllib.request.Request(
        OPENAI_ENDPOINT, data=body, headers=headers, method="POST"
    )
    try:
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            resp_body = resp.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"OpenAI API returned HTTP {exc.code}"
        ) from exc
    except (urllib.error.URLError, OSError) as exc:
        raise RuntimeError(
            f"Failed to reach OpenAI API: {exc}"
        ) from exc

    try:
        resp_json = json.loads(resp_body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"OpenAI returned invalid JSON response: {exc}"
        ) from exc

    content = (
        resp_json.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )

    try:
        result = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Model output is not valid JSON: {exc}"
        ) from exc

    if not isinstance(result, dict):
        raise RuntimeError("Model output must be a JSON object")
    if not research_question.strip():
        result["question_card_id"] = None
    return result


def validate_suggestions(
    suggestions: dict[str, Any],
    source_columns: list[str],
    allowed_targets: Optional[frozenset[str]] = None,
    card_ids: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Validate AI suggestions against actual source headers and allowed targets.

    Returns a dict with:
        valid_mappings: list of validated mapping dicts
        rejected_mappings: list of rejected mappings with reasons
        question_card_id: validated card ID or None
        clarification_questions: list of strings
        errors: list of validation error strings
    """
    if allowed_targets is None:
        allowed_targets = ALLOWED_TARGETS
    if card_ids is None:
        card_ids = _get_card_ids()

    if not isinstance(suggestions, dict):
        raise ValueError("Suggestions must be a JSON object")
    errors: list[str] = []
    valid: list[dict] = []
    rejected: list[dict] = []

    source_set = set(source_columns)
    seen_sources: set[str] = set()
    seen_targets: set[str] = set()

    mappings = suggestions.get("mappings")
    if not isinstance(mappings, list):
        errors.append("'mappings' must be a list")
        mappings = []

    for item in mappings:
        if not isinstance(item, dict):
            errors.append(f"Mapping entry is not a dict: {item!r}")
            continue
        src = item.get("source")
        tgt = item.get("target")
        conf = item.get("confidence", "low")

        if not isinstance(src, str) or (tgt is not None and not isinstance(tgt, str)) or not isinstance(conf, str):
            rejected.append({**item, "rejection_reasons": ["Invalid mapping value types"]})
            continue

        reasons: list[str] = []

        if src not in source_set:
            reasons.append(f"source column {src!r} not in uploaded file")
        if src in seen_sources:
            reasons.append(f"duplicate source column {src!r}")

        if tgt is not None:
            if tgt not in allowed_targets:
                reasons.append(
                    f"target {tgt!r} not in allowed target set"
                )
            if tgt in seen_targets:
                reasons.append(f"duplicate target {tgt!r}")

        if conf not in ("high", "medium", "low"):
            reasons.append(f"invalid confidence {conf!r}")

        if reasons:
            rejected.append({**item, "rejection_reasons": reasons})
        else:
            valid.append(item)
            seen_sources.add(src)
            if tgt is not None:
                seen_targets.add(tgt)

    raw_card_id = suggestions.get("question_card_id")
    validated_card_id = None
    if raw_card_id is not None:
        if isinstance(raw_card_id, str) and raw_card_id in card_ids:
            validated_card_id = raw_card_id
        else:
            errors.append(
                f"question_card_id {raw_card_id!r} not in supported cards"
            )

    clarifications = suggestions.get("clarification_questions", [])
    if not isinstance(clarifications, list):
        errors.append("'clarification_questions' must be a list")
        clarifications = []
    clarifications = [q for q in clarifications if isinstance(q, str)]

    return {
        "valid_mappings": valid,
        "rejected_mappings": rejected,
        "question_card_id": validated_card_id,
        "clarification_questions": clarifications,
        "errors": errors,
    }


def match_question_card(
    card_id: Optional[str],
    card_ids: Optional[list[str]] = None,
) -> Optional[str]:
    """Validate a question card ID against the supported set.

    Returns the card ID if valid, None otherwise.
    """
    if card_id is None:
        return None
    if card_ids is None:
        card_ids = _get_card_ids()
    return card_id if card_id in card_ids else None


def _get_card_ids() -> list[str]:
    try:
        from tripwire.questions import BY_ID
        return list(BY_ID.keys())
    except ImportError:
        return []


def _build_user_message(
    source_columns: list[str],
    num_rows: int,
    allowed_targets: frozenset[str],
    card_ids: list[str],
    filename: Optional[str],
    research_question: str,
) -> str:
    parts = []
    parts.append(f"Research question: {json.dumps(research_question)}")
    if filename:
        parts.append(f"Filename: {filename}")
    parts.append(f"Number of rows: {num_rows}")
    parts.append(f"Source columns: {json.dumps(source_columns)}")
    parts.append(f"Allowed target columns: {json.dumps(sorted(allowed_targets))}")
    parts.append(f"Supported question card IDs: {json.dumps(card_ids)}")
    parts.append(
        "Suggest the best mapping from source to target columns, "
        "and which question card (if any) fits this dataset."
    )
    return "\n".join(parts)
