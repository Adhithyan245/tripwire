"""Apply human-approved column mappings to produce a new DataFrame.

The original DataFrame is never mutated. No deduplication, imputation,
or clinical relabeling is performed. The output is a new in-memory
DataFrame with renamed columns only.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from .schema import ALLOWED_TARGETS


class TransformError(Exception):
    pass


def apply_mappings(
    df: pd.DataFrame,
    approved_mappings: list[dict],
    approval: bool = False,
    allowed_targets: Optional[frozenset[str]] = None,
) -> pd.DataFrame:
    """Apply approved column mappings to produce a new renamed DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        The original parsed upload. **Not mutated.**
    approved_mappings : list[dict]
        Each dict must have ``"source"`` and ``"target"`` keys.
        Only non-null targets are applied.
    approval : bool
        **Must be True.** The caller must confirm the human has
        explicitly approved these mappings.
    allowed_targets : frozenset[str], optional
        Valid target column names. Defaults to ALLOWED_TARGETS.

    Returns
    -------
    pd.DataFrame
        A new DataFrame with mapped columns renamed and unmapped columns
        preserved with their original names. All rows and values are
        preserved exactly.

    Raises
    ------
    TransformError
        If approval is not given, mappings are invalid, or source columns
        are not in the DataFrame.
    """
    if not approval:
        raise TransformError(
            "Explicit human approval is required before applying mappings."
        )

    if allowed_targets is None:
        allowed_targets = ALLOWED_TARGETS

    rename_map: dict[str, str] = {}
    seen_targets: set[str] = set()

    for m in approved_mappings:
        src = m.get("source")
        tgt = m.get("target")

        if tgt is None:
            continue

        if src not in df.columns:
            raise TransformError(
                f"Source column {src!r} is not in the uploaded data"
            )
        if tgt not in allowed_targets:
            raise TransformError(
                f"Target column {tgt!r} is not in the allowed target set"
            )
        if tgt in seen_targets:
            raise TransformError(
                f"Duplicate target {tgt!r} in approved mappings"
            )
        if src in rename_map:
            raise TransformError(
                f"Duplicate source {src!r} in approved mappings"
            )

        rename_map[src] = tgt
        seen_targets.add(tgt)

    result_names = [rename_map.get(col, col) for col in df.columns]
    if len(result_names) != len(set(result_names)):
        raise TransformError("Mappings produce duplicate output columns")
    result = df.copy()
    result = result.rename(columns=rename_map)
    return result
