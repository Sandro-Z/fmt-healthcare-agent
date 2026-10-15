from typing import Protocol

from wgs_fmt_platform.contracts import EvidenceBundle, ModelPrediction


class ModelProvider(Protocol):
    async def predict(self, evidence: EvidenceBundle) -> list[ModelPrediction]: ...

    async def version(self) -> str: ...

