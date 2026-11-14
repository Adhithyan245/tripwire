"""AI-assisted intake prototype for uploaded clinical data.

Public API:
    parse_upload        – validate and parse uploaded bytes into a DataFrame
    suggest_mappings    – call OpenAI to suggest column mappings (requires consent)
    validate_suggestions – validate AI suggestions against actual headers and allowed targets
    apply_mappings      – apply human-approved mappings to produce a new DataFrame
    match_question_card – find a matching question card ID from suggestions
    ALLOWED_TARGETS     – the set of valid target column names
"""

from .upload import parse_upload
from .ai_suggest import suggest_mappings, validate_suggestions, match_question_card
from .transform import apply_mappings
from .schema import ALLOWED_TARGETS

__all__ = [
    "parse_upload",
    "suggest_mappings",
    "validate_suggestions",
    "match_question_card",
    "apply_mappings",
    "ALLOWED_TARGETS",
]
