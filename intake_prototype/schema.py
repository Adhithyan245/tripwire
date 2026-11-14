"""Constants and schema definitions for the intake prototype."""

from __future__ import annotations

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MiB
MAX_COLUMNS = 2000
MAX_ROWS = 500_000
MAX_GZIP_RATIO = 20  # reject gzip bombs exceeding this decompression ratio

ALLOWED_TARGETS: frozenset[str] = frozenset({
    "sampleID",
    "breast_carcinoma_estrogen_receptor_status",
    "PAM50Call_RNAseq",
    "age",
    "OS",
    "OS.time",
    "Redaction",
})

SUPPORTED_CONTENT_TYPES = frozenset({"text/csv", "text/tab-separated-values"})
