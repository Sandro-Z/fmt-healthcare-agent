from pathlib import Path

from wgs_fmt_platform.contracts import AnalysisResult, SampleManifest
from wgs_fmt_platform.metagenome.base import MetagenomeProvider


class MetagenomeService:
    def __init__(self, provider: MetagenomeProvider) -> None:
        self._provider = provider

    async def analyze(self, sample: SampleManifest, database_version: str) -> AnalysisResult:
        return await self._provider.run(sample, database_version=database_version)

    async def update_database(self) -> str:
        return await self._provider.update()

    async def export_database(self, output_dir: Path) -> Path:
        return await self._provider.export(output_dir)

