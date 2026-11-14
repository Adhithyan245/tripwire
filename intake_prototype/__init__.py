"""AI-assisted intake prototype for uploaded clinical data (experimental, research use only).

Original single-call helpers:
    parse_upload        – validate and parse uploaded bytes into a DataFrame
    suggest_mappings    – call OpenAI to suggest column mappings (requires consent)
    validate_suggestions – validate AI suggestions against actual headers and allowed targets
    apply_mappings      – apply human-approved mappings to produce a new DataFrame
    match_question_card – find a matching question card ID from suggestions
    ALLOWED_TARGETS     – the set of valid target column names

Two-agent workflow (see docs/AI_INTAKE_UI.md):
    IntakeWorkflow      – auditable state machine: upload -> mapping proposals (AI or manual) -> review and
                          clarifications -> data-owner approval -> prepared table -> question interpretation and
                          confirmation -> firewall run on a temporary candidate copy -> human review
    WorkflowError, AgentError, CLINICAL_TARGETS, STATES
"""

from .upload import parse_upload
from .ai_suggest import suggest_mappings, validate_suggestions, match_question_card
from .transform import apply_mappings
from .schema import ALLOWED_TARGETS
from .agents import AgentError, CLINICAL_TARGETS
from .workflow import IntakeWorkflow, WorkflowError, STATES

__all__ = [
    "parse_upload",
    "suggest_mappings",
    "validate_suggestions",
    "match_question_card",
    "apply_mappings",
    "ALLOWED_TARGETS",
    "IntakeWorkflow",
    "WorkflowError",
    "AgentError",
    "CLINICAL_TARGETS",
    "STATES",
]
