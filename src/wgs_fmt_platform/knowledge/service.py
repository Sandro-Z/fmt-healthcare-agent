from wgs_fmt_platform.contracts import EvidenceBundle, AnalysisResult
from wgs_fmt_platform.knowledge.base import ClaimQuery, KnowledgeProvider


class KnowledgeService:
    def __init__(self, provider: KnowledgeProvider) -> None:
        self._provider = provider

    async def build_evidence(
        self,
        analysis: AnalysisResult,
        *,
        knowledge_version: str,
        population: dict[str, str | int | float] | None = None,
    ) -> EvidenceBundle:
        query = ClaimQuery(
            features=analysis.features,
            knowledge_version=knowledge_version,
            population=population or {},
        )
        claims = await self._provider.search_claims(query)
        return EvidenceBundle(
            analysis=analysis,
            claims=claims,
            knowledge_version=await self._provider.version(),
        )

