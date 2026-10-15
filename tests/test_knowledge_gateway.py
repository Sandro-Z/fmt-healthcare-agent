import pytest

from wgs_fmt_platform.contracts import (
    FeatureObservation,
    KnowledgeClaim,
    Provenance,
)
from wgs_fmt_platform.contracts.models import ClaimEntity, ClaimEvidence
from wgs_fmt_platform.knowledge import ClaimQuery, UnifiedKnowledgeGateway


def _claim(score: float) -> KnowledgeClaim:
    return KnowledgeClaim(
        claim_id=f"claim-{score}",
        subject=ClaimEntity(id="NCBITaxon:1", name="Microbe A", type="Microbe"),
        predicate="ASSOCIATED_WITH",
        object=ClaimEntity(id="ICD11:1", name="Disease A", type="Disease"),
        evidence=ClaimEvidence(source_type="pubmed", source_id="PMID:1"),
        parser_score=score,
        provenance=Provenance(source="test", source_version="v1"),
    )


class Provider:
    def __init__(self, score: float, version: str) -> None:
        self.claim = _claim(score)
        self._version = version

    async def search_claims(self, query):
        return [self.claim]

    async def version(self):
        return self._version


@pytest.mark.asyncio
async def test_gateway_deduplicates_and_keeps_higher_confidence() -> None:
    gateway = UnifiedKnowledgeGateway([Provider(0.6, "graph-v1"), Provider(0.9, "gene-v2")])
    feature = FeatureObservation(
        feature_id="NCBITaxon:1",
        feature_name="Microbe A",
        feature_type="microbe",
        value=1.0,
        unit="percent",
        provenance=Provenance(source="test", source_version="v1"),
    )
    claims = await gateway.search_claims(ClaimQuery(features=[feature]))
    assert len(claims) == 1
    assert claims[0].parser_score == 0.9
    assert await gateway.version() == "graph-v1+gene-v2"
