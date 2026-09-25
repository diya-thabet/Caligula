"""Content-addressed, write-once blob storage on the local filesystem.

A later "corrected" file can never overwrite bytes we already hold; it can only
be added next to them under its own hash.
"""

from __future__ import annotations

from pathlib import Path

from caligula.domain.services.text import sha256_bytes


class FileBlobStorage:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, digest: str) -> Path:
        return self.root / digest[:2] / digest

    def put(self, data: bytes) -> str:
        digest = sha256_bytes(data)
        path = self._path(digest)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return digest

    def get(self, digest: str) -> bytes:
        return self._path(digest).read_bytes()

    def verify(self, digest: str) -> bool:
        path = self._path(digest)
        return path.exists() and sha256_bytes(path.read_bytes()) == digest
