"""Tests for intake_prototype – upload, AI suggestions, validation, and transform.

All OpenAI calls are mocked: no real network or API key needed.
"""

from __future__ import annotations

import gzip
import json
import io
from unittest import mock

import pandas as pd
import pytest

from intake_prototype.upload import parse_upload, UploadError
from intake_prototype.ai_suggest import (
    suggest_mappings,
    validate_suggestions,
    match_question_card,
)
from intake_prototype.transform import apply_mappings, TransformError
from intake_prototype.schema import ALLOWED_TARGETS, MAX_UPLOAD_BYTES


# ── helpers ──────────────────────────────────────────────────────────

def _csv_bytes(headers: list[str], rows: list[list[str]]) -> bytes:
    lines = [",".join(headers)]
    for row in rows:
        lines.append(",".join(row))
    return "\n".join(lines).encode("utf-8")


def _tsv_bytes(headers: list[str], rows: list[list[str]]) -> bytes:
    lines = ["\t".join(headers)]
    for row in rows:
        lines.append("\t".join(row))
    return "\n".join(lines).encode("utf-8")


def _make_openai_response(content_dict: dict) -> bytes:
    return json.dumps({
        "choices": [{
            "message": {"content": json.dumps(content_dict)},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50},
    }).encode("utf-8")


SAMPLE_HEADERS = ["sample_id", "er_status", "subtype", "patient_age"]
SAMPLE_ROWS = [
    ["TCGA-A1-0001-01", "Positive", "LumA", "55"],
    ["TCGA-A1-0002-01", "Negative", "Basal", "42"],
]

GOOD_SUGGESTION = {
    "mappings": [
        {"source": "sample_id", "target": "sampleID", "confidence": "high"},
        {"source": "er_status", "target": "breast_carcinoma_estrogen_receptor_status", "confidence": "high"},
        {"source": "subtype", "target": "PAM50Call_RNAseq", "confidence": "medium"},
        {"source": "patient_age", "target": "age", "confidence": "medium"},
    ],
    "question_card_id": "er_protein_by_er_status",
    "clarification_questions": ["Does 'er_status' refer to IHC or mRNA-based ER classification?"],
}


# ── upload tests ──────────────────────────────────────────────────────

class TestParseUpload:
    def test_valid_csv(self):
        data = _csv_bytes(SAMPLE_HEADERS, SAMPLE_ROWS)
        df = parse_upload(data, "clinical.csv")
        assert list(df.columns) == SAMPLE_HEADERS
        assert len(df) == 2

    def test_valid_tsv(self):
        data = _tsv_bytes(SAMPLE_HEADERS, SAMPLE_ROWS)
        df = parse_upload(data, "data.tsv")
        assert list(df.columns) == SAMPLE_HEADERS
        assert len(df) == 2

    def test_valid_gzip_csv(self):
        raw = _csv_bytes(SAMPLE_HEADERS, SAMPLE_ROWS)
        compressed = gzip.compress(raw)
        df = parse_upload(compressed, "data.csv.gz")
        assert len(df) == 2

    def test_valid_gzip_tsv(self):
        raw = _tsv_bytes(SAMPLE_HEADERS, SAMPLE_ROWS)
        compressed = gzip.compress(raw)
        df = parse_upload(compressed, "data.tsv.gz")
        assert len(df) == 2

    def test_reject_unsupported_type(self):
        with pytest.raises(UploadError, match="Unsupported file type"):
            parse_upload(b"some data", "data.xlsx")

    def test_reject_unsupported_json(self):
        with pytest.raises(UploadError, match="Unsupported file type"):
            parse_upload(b'{"a": 1}', "data.json")

    def test_reject_empty(self):
        with pytest.raises(UploadError, match="empty"):
            parse_upload(b"", "data.csv")

    def test_reject_too_large(self):
        data = b"x" * (MAX_UPLOAD_BYTES + 1)
        with pytest.raises(UploadError, match="size limit"):
            parse_upload(data, "data.csv")

    def test_reject_not_bytes(self):
        with pytest.raises(UploadError, match="must be bytes"):
            parse_upload("string data", "data.csv")  # type: ignore[arg-type]

    def test_reject_no_filename(self):
        with pytest.raises(UploadError, match="Filename"):
            parse_upload(b"a,b\n1,2", "")

    def test_reject_duplicate_headers(self):
        data = "col_a,col_b,col_a\n1,2,3\n".encode("utf-8")
        with pytest.raises(UploadError, match="Duplicate column"):
            parse_upload(data, "data.csv")

    def test_reject_non_utf8(self):
        data = b"\xff\xfe" + "col_a,col_b\n1,2\n".encode("utf-8")
        with pytest.raises(UploadError, match="UTF-8"):
            parse_upload(data, "data.csv")

    def test_reject_header_only(self):
        data = b"col_a,col_b\n"
        with pytest.raises(UploadError, match="no data rows"):
            parse_upload(data, "data.csv")

    def test_content_type_fallback_csv(self):
        data = _csv_bytes(["a", "b"], [["1", "2"]])
        df = parse_upload(data, "upload.csv", content_type="text/csv")
        assert len(df) == 1

    def test_content_type_fallback_tsv(self):
        data = _tsv_bytes(["a", "b"], [["1", "2"]])
        df = parse_upload(data, "upload.tsv", content_type="text/tab-separated-values")
        assert len(df) == 1


# ── consent and API key tests ────────────────────────────────────────

class TestSuggestMappingsConsent:
    def test_no_consent_raises(self):
        with pytest.raises(ValueError, match="consent"):
            suggest_mappings(
                source_columns=SAMPLE_HEADERS,
                num_rows=2,
                consent=False,
            )

    def test_no_api_key_raises(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="OPENAI_API_KEY"):
                suggest_mappings(
                    source_columns=SAMPLE_HEADERS,
                    num_rows=2,
                    consent=True,
                )


# ── AI suggestion tests (mocked) ────────────────────────────────────

class TestSuggestMappingsMocked:
    def _mock_urlopen(self, response_dict):
        resp_bytes = _make_openai_response(response_dict)
        mock_resp = mock.MagicMock()
        mock_resp.read.return_value = resp_bytes
        mock_resp.__enter__ = mock.MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = mock.MagicMock(return_value=False)
        return mock.patch("urllib.request.urlopen", return_value=mock_resp)

    def test_good_suggestion(self):
        with mock.patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            with self._mock_urlopen(GOOD_SUGGESTION):
                result = suggest_mappings(
                    source_columns=SAMPLE_HEADERS,
                    num_rows=2,
                    consent=True,
                    research_question="Does ER protein differ by ER status?",
                    card_ids=["er_protein_by_er_status", "subtype_mix"],
                )
        assert result["mappings"] == GOOD_SUGGESTION["mappings"]
        assert result["question_card_id"] == "er_protein_by_er_status"

    def test_malformed_json_response(self):
        mock_resp = mock.MagicMock()
        bad_outer = json.dumps({
            "choices": [{
                "message": {"content": "NOT VALID JSON {{{"},
                "finish_reason": "stop",
            }]
        }).encode("utf-8")
        mock_resp.read.return_value = bad_outer
        mock_resp.__enter__ = mock.MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = mock.MagicMock(return_value=False)

        with mock.patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            with mock.patch("urllib.request.urlopen", return_value=mock_resp):
                with pytest.raises(RuntimeError, match="not valid JSON"):
                    suggest_mappings(
                        source_columns=SAMPLE_HEADERS,
                        num_rows=2,
                        consent=True,
                    )

    def test_no_raw_data_in_prompt(self):
        """The prompt must never contain raw data rows."""
        captured_req = {}

        def capture_urlopen(req, **kwargs):
            captured_req["body"] = json.loads(req.data)
            resp = mock.MagicMock()
            resp.read.return_value = _make_openai_response(GOOD_SUGGESTION)
            resp.__enter__ = mock.MagicMock(return_value=resp)
            resp.__exit__ = mock.MagicMock(return_value=False)
            return resp

        with mock.patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            with mock.patch("urllib.request.urlopen", side_effect=capture_urlopen):
                suggest_mappings(
                    source_columns=SAMPLE_HEADERS,
                    num_rows=2,
                    consent=True,
                )

        messages = captured_req["body"]["messages"]
        full_text = " ".join(m["content"] for m in messages)
        assert "TCGA-A1-0001" not in full_text
        assert "Positive" not in full_text or "Positive" in SAMPLE_HEADERS


# ── validation tests ─────────────────────────────────────────────────

class TestValidateSuggestions:
    def test_valid_suggestions(self):
        result = validate_suggestions(
            GOOD_SUGGESTION,
            source_columns=SAMPLE_HEADERS,
            card_ids=["er_protein_by_er_status", "subtype_mix"],
        )
        assert len(result["valid_mappings"]) == 4
        assert len(result["rejected_mappings"]) == 0
        assert result["question_card_id"] == "er_protein_by_er_status"
        assert len(result["errors"]) == 0

    def test_hallucinated_target(self):
        bad = {
            "mappings": [
                {"source": "sample_id", "target": "hallucinated_column", "confidence": "high"},
            ],
            "question_card_id": None,
            "clarification_questions": [],
        }
        result = validate_suggestions(bad, source_columns=SAMPLE_HEADERS)
        assert len(result["rejected_mappings"]) == 1
        assert "not in allowed target set" in result["rejected_mappings"][0]["rejection_reasons"][0]

    def test_hallucinated_source(self):
        bad = {
            "mappings": [
                {"source": "nonexistent_col", "target": "sampleID", "confidence": "high"},
            ],
            "question_card_id": None,
            "clarification_questions": [],
        }
        result = validate_suggestions(bad, source_columns=SAMPLE_HEADERS)
        assert len(result["rejected_mappings"]) == 1
        assert "not in uploaded file" in result["rejected_mappings"][0]["rejection_reasons"][0]

    def test_duplicate_target_rejected(self):
        bad = {
            "mappings": [
                {"source": "sample_id", "target": "sampleID", "confidence": "high"},
                {"source": "er_status", "target": "sampleID", "confidence": "high"},
            ],
            "question_card_id": None,
            "clarification_questions": [],
        }
        result = validate_suggestions(bad, source_columns=SAMPLE_HEADERS)
        assert len(result["rejected_mappings"]) == 1
        assert any("duplicate target" in r for r in result["rejected_mappings"][0]["rejection_reasons"])

    def test_duplicate_source_rejected(self):
        bad = {
            "mappings": [
                {"source": "sample_id", "target": "sampleID", "confidence": "high"},
                {"source": "sample_id", "target": "age", "confidence": "high"},
            ],
            "question_card_id": None,
            "clarification_questions": [],
        }
        result = validate_suggestions(bad, source_columns=SAMPLE_HEADERS)
        assert len(result["rejected_mappings"]) == 1
        assert any("duplicate source" in r for r in result["rejected_mappings"][0]["rejection_reasons"])

    def test_invalid_card_id(self):
        bad = {
            "mappings": [],
            "question_card_id": "totally_fake_card",
            "clarification_questions": [],
        }
        result = validate_suggestions(
            bad,
            source_columns=SAMPLE_HEADERS,
            card_ids=["er_protein_by_er_status"],
        )
        assert result["question_card_id"] is None
        assert any("not in supported cards" in e for e in result["errors"])

    def test_missing_mappings_key(self):
        bad = {"question_card_id": None, "clarification_questions": []}
        result = validate_suggestions(bad, source_columns=SAMPLE_HEADERS)
        assert any("'mappings' must be a list" in e for e in result["errors"])

    def test_non_dict_mapping_entry(self):
        bad = {
            "mappings": ["not a dict"],
            "question_card_id": None,
            "clarification_questions": [],
        }
        result = validate_suggestions(bad, source_columns=SAMPLE_HEADERS)
        assert any("not a dict" in e for e in result["errors"])

    def test_null_target_passes_validation(self):
        ok = {
            "mappings": [
                {"source": "sample_id", "target": None, "confidence": "low"},
            ],
            "question_card_id": None,
            "clarification_questions": ["What does sample_id map to?"],
        }
        result = validate_suggestions(ok, source_columns=SAMPLE_HEADERS)
        assert len(result["valid_mappings"]) == 1
        assert len(result["clarification_questions"]) == 1


# ── question card matching ───────────────────────────────────────────

class TestMatchQuestionCard:
    def test_valid_card(self):
        assert match_question_card(
            "er_protein_by_er_status",
            card_ids=["er_protein_by_er_status", "subtype_mix"],
        ) == "er_protein_by_er_status"

    def test_invalid_card(self):
        assert match_question_card(
            "fake_card",
            card_ids=["er_protein_by_er_status"],
        ) is None

    def test_none_card(self):
        assert match_question_card(None) is None


# ── transform tests ──────────────────────────────────────────────────

class TestApplyMappings:
    @pytest.fixture
    def sample_df(self):
        return pd.DataFrame({
            "sample_id": ["A", "B"],
            "er_status": ["Positive", "Negative"],
            "subtype": ["LumA", "Basal"],
            "patient_age": [55, 42],
        })

    def test_no_approval_raises(self, sample_df):
        with pytest.raises(TransformError, match="approval"):
            apply_mappings(
                sample_df,
                [{"source": "sample_id", "target": "sampleID"}],
                approval=False,
            )

    def test_valid_mapping(self, sample_df):
        mappings = [
            {"source": "sample_id", "target": "sampleID"},
            {"source": "er_status", "target": "breast_carcinoma_estrogen_receptor_status"},
        ]
        result = apply_mappings(sample_df, mappings, approval=True)
        assert "sampleID" in result.columns
        assert "breast_carcinoma_estrogen_receptor_status" in result.columns
        assert "subtype" in result.columns  # unmapped, preserved
        assert len(result) == 2
        # original not mutated
        assert "sample_id" in sample_df.columns

    def test_original_not_mutated(self, sample_df):
        original_cols = list(sample_df.columns)
        apply_mappings(
            sample_df,
            [{"source": "sample_id", "target": "sampleID"}],
            approval=True,
        )
        assert list(sample_df.columns) == original_cols

    def test_all_rows_preserved(self, sample_df):
        result = apply_mappings(
            sample_df,
            [{"source": "sample_id", "target": "sampleID"}],
            approval=True,
        )
        assert len(result) == len(sample_df)
        assert list(result["sampleID"]) == list(sample_df["sample_id"])

    def test_null_target_skipped(self, sample_df):
        mappings = [
            {"source": "sample_id", "target": None},
            {"source": "er_status", "target": "breast_carcinoma_estrogen_receptor_status"},
        ]
        result = apply_mappings(sample_df, mappings, approval=True)
        assert "sample_id" in result.columns  # unchanged
        assert "breast_carcinoma_estrogen_receptor_status" in result.columns

    def test_invalid_target_raises(self, sample_df):
        with pytest.raises(TransformError, match="not in the allowed target set"):
            apply_mappings(
                sample_df,
                [{"source": "sample_id", "target": "fake_target"}],
                approval=True,
            )

    def test_missing_source_raises(self, sample_df):
        with pytest.raises(TransformError, match="not in the uploaded data"):
            apply_mappings(
                sample_df,
                [{"source": "nonexistent", "target": "sampleID"}],
                approval=True,
            )

    def test_duplicate_target_raises(self, sample_df):
        with pytest.raises(TransformError, match="Duplicate target"):
            apply_mappings(
                sample_df,
                [
                    {"source": "sample_id", "target": "sampleID"},
                    {"source": "er_status", "target": "sampleID"},
                ],
                approval=True,
            )

    def test_duplicate_source_raises(self, sample_df):
        with pytest.raises(TransformError, match="Duplicate source"):
            apply_mappings(
                sample_df,
                [
                    {"source": "sample_id", "target": "sampleID"},
                    {"source": "sample_id", "target": "age"},
                ],
                approval=True,
            )

    def test_no_deduplication_or_imputation(self, sample_df):
        """Values must be preserved exactly, no cleanup."""
        df = pd.DataFrame({
            "sample_id": ["A", "A", "B"],  # duplicate row values are preserved
            "er_status": ["Positive", "Positive", ""],  # empty preserved
        })
        result = apply_mappings(
            df,
            [{"source": "sample_id", "target": "sampleID"}],
            approval=True,
        )
        assert list(result["sampleID"]) == ["A", "A", "B"]
        assert list(result["er_status"]) == ["Positive", "Positive", ""]


def test_preserves_identifiers_and_na_tokens():
    df = parse_upload(b'id,value\n001,NA\n002,\n', 'data.csv')
    assert df['id'].tolist() == ['001', '002']
    assert df['value'].tolist() == ['NA', '']


def test_rejects_rename_collision_with_unmapped_column():
    df = pd.DataFrame({'sample_id': ['001'], 'sampleID': ['002']})
    with pytest.raises(TransformError):
        apply_mappings(df, [{'source': 'sample_id', 'target': 'sampleID'}], approval=True)


def test_rejects_malformed_rows_and_quoted_duplicate_headers():
    with pytest.raises(UploadError):
        parse_upload(b'a,b\n1\n', 'data.csv')
    with pytest.raises(UploadError):
        parse_upload(b'"a",a\n1,2\n', 'data.csv')


def test_untrusted_mapping_types_are_rejected():
    result = validate_suggestions({'mappings': [{'source': [], 'target': {}}]}, ['x'])
    assert not result['valid_mappings']
    assert result['rejected_mappings']
