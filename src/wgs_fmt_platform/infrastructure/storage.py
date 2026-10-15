from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from pydantic import BaseModel


class StoredArtifact(BaseModel):
    uri: str
    sha256: str
    size: int


class FileArtifactStore:
    """Filesystem implementation; replaceable by S3/MinIO behind this boundary."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    @staticmethod
    def _safe_component(value: str) -> str:
        if not value.replace("-", "").replace("_", "").replace(".", "").isalnum():
            raise ValueError(f"unsafe artifact component: {value}")
        return value

    def put(self, source: Path, namespace: str, version: str) -> StoredArtifact:
        source = source.resolve(strict=True)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        destination = (
            self.root
            / self._safe_component(namespace)
            / self._safe_component(version)
            / digest
            / source.name
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copy2(source, destination)
        return StoredArtifact(
            uri=destination.as_uri(),
            sha256=digest,
            size=destination.stat().st_size,
        )

