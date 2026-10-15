from __future__ import annotations

from wgs_fmt_platform.contracts import KnowledgeClaim
from wgs_fmt_platform.knowledge.base import ClaimQuery, KnowledgeProvider


class UnifiedKnowledgeGateway:
    """Merge graph, gene, SQLite, and literature providers with degradation."""

    def __init__(self, providers: list[KnowledgeProvider]) -> None:
        if not providers:
            raise ValueError("at least one knowledge provider is required")
        self.providers = providers
        self.last_errors: list[str] = []
        self.last_versions: list[str] = []

    @staticmethod
    def _key(claim: KnowledgeClaim) -> tuple[str, str, str, str]:
        return (
            claim.subject.id,
            claim.predicate,
            claim.object.id,
            claim.evidence.source_id,
        )

    async def search_claims(self, query: ClaimQuery) -> list[KnowledgeClaim]:
        self.last_errors = []
        merged: dict[tuple[str, str, str, str], KnowledgeClaim] = {}
        for provider in self.providers:
            try:
                for claim in await provider.search_claims(query):
                    key = self._key(claim)
                    current = merged.get(key)
                    if current is None or (claim.parser_score or 0) > (current.parser_score or 0):
                        merged[key] = claim
            except Exception as exc:
                self.last_errors.append(f"{provider.__class__.__name__}: {exc}")

        claims = sorted(
            merged.values(),
            key=lambda item: (
                item.review_status == "human_verified",
                item.evidence.evidence_level in {"meta_analysis", "clinical_trial", "cohort"},
                item.parser_score or 0,
            ),
            reverse=True,
        )
        return claims[: query.limit]

    async def version(self) -> str:
        versions: list[str] = []
        for provider in self.providers:
            try:
                versions.append(await provider.version())
            except Exception as exc:
                self.last_errors.append(f"{provider.__class__.__name__}: {exc}")
        self.last_versions = versions
        return "+".join(versions) if versions else "unavailable"

