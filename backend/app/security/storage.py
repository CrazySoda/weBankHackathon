"""Read-only document storage: content-addressed on disk for the demo.

Files are stored once by SHA-256 and never modified; the API refuses writes to
an existing hash (immutability). Raw bytes never enter graph state.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


class DocumentStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def sha256(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def put(self, data: bytes) -> str:
        """Store bytes, return sha256. Idempotent (same content → same key)."""
        h = self.sha256(data)
        path = self._path(h)
        if path.exists():
            if path.read_bytes() != data:
                raise RuntimeError("sha256 collision on document store")
            return h
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.chmod(0o444)  # read-only
        tmp.replace(path)
        return h

    def get(self, sha256_hex: str) -> bytes:
        path = self._path(sha256_hex)
        if not path.exists():
            raise FileNotFoundError(sha256_hex)
        return path.read_bytes()

    def exists(self, sha256_hex: str) -> bool:
        return self._path(sha256_hex).exists()

    def _path(self, sha256_hex: str) -> Path:
        if len(sha256_hex) != 64 or not all(c in "0123456789abcdef" for c in sha256_hex):
            raise ValueError("invalid sha256 hex")
        return self.root / sha256_hex[:2] / sha256_hex
