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
        return pd.read_csv(self.path / "clinical.tsv", sep="\t", low_memory=False)

    @cached_property
    def protein(self) -> pd.DataFrame:
        return pd.read_csv(self.path / "protein_rppa.tsv.gz", sep="\t", index_col=0)

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
            cache[name] = pd.read_csv(self.path / name, sep="\t", index_col=0)
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
