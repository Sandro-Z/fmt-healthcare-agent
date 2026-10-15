from __future__ import annotations

from pathlib import Path
from typing import Protocol

from wgs_fmt_platform.contracts import AnalysisResult, SampleManifest


class MetagenomeProvider(Protocol):
    async def initialize(self, reference: Path) -> str: ...

    async def update(self) -> str: ...

    async def run(self, sample: SampleManifest, *, database_version: str) -> AnalysisResult: ...

    async def export(self, output_dir: Path) -> Path: ...

    async def version(self) -> str: ...

