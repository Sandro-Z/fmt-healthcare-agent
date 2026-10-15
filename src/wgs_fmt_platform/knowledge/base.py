from typing import Protocol

from pydantic import BaseModel, Field

from wgs_fmt_platform.contracts import FeatureObservation, KnowledgeClaim


class ClaimQuery(BaseModel):
    features: list[FeatureObservation]
    task: str = "health_report"
    population: dict[str, str | int | float] = Field(default_factory=dict)
    knowledge_version: str = "current"
    limit: int = Field(default=50, ge=1, le=500)


class KnowledgeProvider(Protocol):
    async def search_claims(self, query: ClaimQuery) -> list[KnowledgeClaim]: ...

    async def version(self) -> str: ...

