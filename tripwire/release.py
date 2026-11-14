"""Load a release folder and fingerprint its files."""
from __future__ import annotations

import gzip
import hashlib
import pathlib
from functools import cached_property

import pandas as pd

DATA_SUFFIXES = (".tsv", ".tsv.gz")


def file_sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def content_sha256(path) -> str:
    """Hash of the decompressed content with line endings normalised to LF.

    pandas writes CRLF on Windows, so a release rebuilt there (make_release.py, unseal.py) has different bytes
    but identical content. Normalising keeps our hashes equal to the organizers' on any OS."""
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rb") as f:
        return hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest()


def default_name(path: pathlib.Path) -> str:
    # envelopes/opened/E07/release -> E07
    return path.parent.name if path.name == "release" else path.name


def _no_duplicate_headers(path: pathlib.Path) -> None:
    """A clinical header that names the same column twice is ambiguous (pandas would silently rename one): refuse it.
    Not applied to the molecular files: there a repeated sample-ID column is a change the detector reports."""
    opener = gzip.open if path.name.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8", errors="replace", newline="") as f:
        cols = f.readline().rstrip(chr(13) + chr(10)).split(chr(9))
    dup = sorted({c for c in cols if cols.count(c) > 1 and c})
    if dup:
        raise ValueError(f"{path.name} names the same column more than once: {', '.join(dup[:5])}")


ROW_ID = {"survival.tsv": "sample"}  # sample-ID column of the row-oriented files


class Release:
    def __init__(self, path, name: str | None = None):
        self.path = pathlib.Path(path)
        if not self.path.is_dir():
            raise FileNotFoundError(f"release folder not found: {self.path}")
        self.name = name or default_name(self.path)

    @property
    def files(self) -> list[str]:
        return sorted(p.name for p in self.path.iterdir() if p.name.endswith(DATA_SUFFIXES))

    def has(self, name: str) -> bool:
        return (self.path / name).exists()

    @cached_property
    def clinical(self) -> pd.DataFrame:
        _no_duplicate_headers(self.path / "clinical.tsv")
        return pd.read_csv(self.path / "clinical.tsv", sep="\t", low_memory=False)

    @cached_property
    def protein(self) -> pd.DataFrame:
        return self._matrix("protein_rppa.tsv.gz")

    def _matrix(self, name: str) -> pd.DataFrame:
        """A molecular file with each feature row kept once. A repeated feature row (two ERALPHA rows, say) is
        ambiguous: it's remembered in repeated_features so the detector reports it, and only the first copy is used."""
        if name in ROW_ID:  # one row per sample: index by the named ID column wherever it sits in the header
            df = pd.read_csv(self.path / name, sep="\t")
            df = df.set_index(ROW_ID[name] if ROW_ID[name] in df.columns else df.columns[0])
        else:
            df = pd.read_csv(self.path / name, sep="\t", index_col=0)
        dup = df.index[df.index.duplicated()]
        if len(dup):
            self.__dict__.setdefault("repeated_features", {})[name] = sorted({str(x) for x in dup})
            df = df[~df.index.duplicated(keep="first")]
        return df

    def sample_ids(self, name: str) -> list[str]:
        """Sample IDs of a molecular file from its header line only (fast for large files). Cached."""
        cache = self.__dict__.setdefault("_ids", {})
        if name not in cache:
            if name == "protein_rppa.tsv.gz" or name in self.__dict__.get("_tables", {}):
                cache[name] = list(self.table(name).columns)
            else:
                cache[name] = list(pd.read_csv(self.path / name, sep="	", index_col=0, nrows=0).columns)
        return cache[name]

    def table(self, name: str) -> pd.DataFrame:
        """Any molecular file: features as rows, samples as columns. Cached."""
        if name == "clinical.tsv":
            return self.clinical
        if name == "protein_rppa.tsv.gz":
            return self.protein
        cache = self.__dict__.setdefault("_tables", {})
        if name not in cache:
            cache[name] = self._matrix(name)
        return cache[name]

    def fingerprints(self, hash_of: str = "file") -> list[dict]:
        fn = content_sha256 if hash_of == "content" else file_sha256
        out = []
        for name in self.files:
            entry = {"file": name, "sha256": fn(self.path / name)}
            if hash_of == "content":
                entry["hash_of"] = "content"
            out.append(entry)
        return out
