"""Detection engine: Role 1 owns this package.

Interface stub only, so Role 2's pipeline runs end to end today. Replace the body of detect_changes with the real
detector; keep the signature. Until then Tripwire still catches that an analysis moved (verification rerun) and
reports it as an unexplained change.
"""
from __future__ import annotations

import warnings

from ..contract import Change
from ..release import Release


def detect_changes(release_a: Release, release_b: Release) -> list[Change]:
    warnings.warn("tripwire.detect is a stub (Role 1 not merged yet): no changes detected", stacklevel=2)
    return []
