"""Safe parsing of uploaded CSV/TSV bytes."""

from __future__ import annotations

import csv
import gzip
import io
from typing import Optional

import pandas as pd

from .schema import (
    MAX_COLUMNS,
    MAX_GZIP_RATIO,
    MAX_ROWS,
    MAX_UPLOAD_BYTES,
    SUPPORTED_CONTENT_TYPES,
)


class UploadError(Exception):
    pass


def parse_upload(
    data: bytes,
    filename: str,
    content_type: Optional[str] = None,
) -> pd.DataFrame:
    """Parse uploaded bytes into a DataFrame.

    Parameters
    ----------
    data : bytes
        Raw upload payload. Must be UTF-8 CSV, TSV, or gzip-compressed
        versions of those.
    filename : str
        Original filename from the upload, used for type inference.
    content_type : str, optional
        MIME type hint. Overridden by filename extension when ambiguous.

    Returns
    -------
    pd.DataFrame

    Raises
    ------
    UploadError
        On unsupported type, size, malformed data, or duplicate headers.
    """
    if not isinstance(data, bytes):
        raise UploadError("Upload must be bytes")
    if not filename or not isinstance(filename, str):
        raise UploadError("Filename is required")
    if len(data) > MAX_UPLOAD_BYTES:
        raise UploadError(
            f"Upload exceeds size limit ({len(data)} bytes > {MAX_UPLOAD_BYTES})"
        )
    if len(data) == 0:
        raise UploadError("Upload is empty")

    raw_bytes, was_gzip = _maybe_decompress(data, filename)
    sep = _infer_separator(filename, content_type)

    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UploadError(f"Upload is not valid UTF-8: {exc}") from exc

    _check_headers(text, sep)
    df = _read_dataframe(text, sep)
    _check_dimensions(df)

    return df


def _maybe_decompress(data: bytes, filename: str) -> tuple[bytes, bool]:
    if not filename.endswith(".gz"):
        return data, False
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
            raw = stream.read(min(MAX_UPLOAD_BYTES, len(data) * MAX_GZIP_RATIO) + 1)
    except (gzip.BadGzipFile, OSError, EOFError) as exc:
        raise UploadError(f"Gzip decompression failed: {exc}") from exc
    if len(data) > 0 and len(raw) / len(data) > MAX_GZIP_RATIO:
        raise UploadError(
            f"Gzip decompression ratio ({len(raw) / len(data):.0f}x) "
            f"exceeds safety limit ({MAX_GZIP_RATIO}x)"
        )
    if len(raw) > MAX_UPLOAD_BYTES:
        raise UploadError(
            f"Decompressed size exceeds limit ({len(raw)} bytes > {MAX_UPLOAD_BYTES})"
        )
    return raw, True


def _infer_separator(filename: str, content_type: Optional[str]) -> str:
    lower = filename.lower().replace(".gz", "")
    if lower.endswith(".tsv"):
        return "\t"
    if lower.endswith(".csv"):
        return ","
    if content_type == "text/tab-separated-values":
        return "\t"
    if content_type == "text/csv":
        return ","
    raise UploadError(
        f"Unsupported file type: {filename!r}. "
        "Expected .csv, .tsv, .csv.gz, or .tsv.gz"
    )


def _check_headers(text: str, sep: str) -> None:
    try:
        rows = csv.reader(io.StringIO(text, newline=""), delimiter=sep, strict=True)
        headers = next(rows)
        if any(len(row) != len(headers) for row in rows):
            raise UploadError("Rows have inconsistent numbers of fields")
    except (csv.Error, StopIteration) as exc:
        raise UploadError("Malformed or empty tabular data") from exc
    if not headers or any(not h.strip() for h in headers):
        raise UploadError("Upload has no header row")
    seen: set[str] = set()
    dupes: list[str] = []
    for h in headers:
        h_stripped = h.strip()
        if h_stripped in seen:
            dupes.append(h_stripped)
        seen.add(h_stripped)
    if dupes:
        raise UploadError(f"Duplicate column headers: {', '.join(sorted(set(dupes)))}")


def _read_dataframe(text: str, sep: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(
            io.StringIO(text),
            sep=sep,
            low_memory=False,
            quoting=csv.QUOTE_MINIMAL,
            dtype=str,
            keep_default_na=False,
        )
    except Exception as exc:
        raise UploadError(f"Failed to parse tabular data: {exc}") from exc
    return df


def _check_dimensions(df: pd.DataFrame) -> None:
    if len(df.columns) > MAX_COLUMNS:
        raise UploadError(
            f"Too many columns ({len(df.columns)} > {MAX_COLUMNS})"
        )
    if len(df) > MAX_ROWS:
        raise UploadError(f"Too many rows ({len(df)} > {MAX_ROWS})")
    if len(df) == 0:
        raise UploadError("Upload has a header but no data rows")
