import httpx
import pytest

from wgs_fmt_platform.contracts import FeatureObservation, Provenance
from wgs_fmt_platform.knowledge import ClaimQuery
from wgs_fmt_platform.knowledge.adapters import ClaimApiAdapter


@pytest.mark.asyncio
async def test_openapi_discovery_and_claim_normalization() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/openapi.json":
            return httpx.Response(
                200,
                json={
                    "openapi": "3.1.0",
                    "info": {"title": "Literature Claim API", "version": "kg-2026.07"},
                    "paths": {
                        "/api/claims/query": {
                            "post": {
                                "operationId": "search_claims",
                                "summary": "Search literature claims",
                                "tags": ["claims"],
                            }
                        }
                    },
                },
            )
        if request.url.path == "/api/claims/query":
            payload = __import__("json").loads(request.content)
            assert payload["feature_ids"] == ["NCBITaxon:853"]
            return httpx.Response(
                200,
                json={
                    "version": "kg-2026.07",
                    "results": [
                        {
                            "id": "claim-001",
                            "source": {
                                "id": "NCBITaxon:853",
                                "label": "Faecalibacterium prausnitzii",
                                "type": "Microbe",
                            },
                            "relation": "NEGATIVELY_ASSOCIATED_WITH",
                            "target": {
                                "id": "ICD11:DD71",
                                "label": "Inflammatory bowel disease",
                                "type": "Disease",
                            },
                            "pmid": "PMID:12345678",
                            "evidence_text": "Reported association in a cohort.",
                            "confidence": 0.91,
                        }
                    ],
                },
            )
        return httpx.Response(404)

    adapter = ClaimApiAdapter(
        "http://10.181.8.92:8080",
        transport=httpx.MockTransport(handler),
    )
    feature = FeatureObservation(
        feature_id="NCBITaxon:853",
        feature_name="Faecalibacterium prausnitzii",
        feature_type="microbe",
        value=0.42,
        unit="percent",
        status="low",
        provenance=Provenance(source="test", source_version="v1"),
    )
    claims = await adapter.search_claims(ClaimQuery(features=[feature]))
    assert adapter.search_path == "/api/claims/query"
    assert adapter.search_method == "POST"
    assert len(claims) == 1
    assert claims[0].claim_id == "claim-001"
    assert claims[0].subject.id == "NCBITaxon:853"
    assert claims[0].object.id == "ICD11:DD71"
    assert claims[0].evidence.source_id == "PMID:12345678"
    assert await adapter.version() == "kg-2026.07"


def test_claim_response_requires_supported_shape() -> None:
    with pytest.raises(Exception, match="contains none"):
        ClaimApiAdapter._items({"unexpected": []})


@pytest.mark.asyncio
async def test_litkg_knowledge_base_claim_contract() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/openapi.json":
            return httpx.Response(
                200,
                json={
                    "openapi": "3.1.0",
                    "info": {"title": "LitKG API", "version": "2.0.0"},
                    "paths": {
                        "/documents/{document_id}/claims": {
                            "get": {"summary": "Get Claims", "operationId": "get_claims"}
                        },
                        "/knowledge-bases/{knowledge_base_id}/claims": {
                            "get": {
                                "summary": "Get Knowledge Base Claims",
                                "operationId": "get_knowledge_base_claims",
                            }
                        },
                    },
                },
            )
        if request.url.path == "/knowledge-bases/7/claims":
            assert request.url.params["limit"] == "1000"
            return httpx.Response(
                200,
                json={
                    "knowledge_base_id": 7,
                    "claims": [
                        {
                            "id": 2,
                            "document_id": 11,
                            "filename": "fmt-paper.pdf",
                            "chunk_id": 4,
                            "section_title": "Results",
                            "subject_text": "Collinsella",
                            "subject_type": "Microbe",
                            "subject_normalized_id": "NCBITaxon:102106",
                            "subject_entity_id": 2,
                            "predicate": "MODULATES",
                            "object_text": "cholesterol pathway gene expression",
                            "object_type": "Pathway",
                            "object_normalized_id": None,
                            "object_entity_id": 4,
                            "evidence_text": "Collinsella modulated cholesterol pathway expression.",
                            "confidence": 0.9,
                            "negated": False,
                            "speculative": False,
                            "claim_json": {
                                "qualifiers": {"species": "mice", "assay": "RNA sequencing"}
                            },
                        }
                    ],
                    "limit": 1000,
                    "offset": 0,
                },
            )
        return httpx.Response(404)

    adapter = ClaimApiAdapter(
        "http://10.181.8.92:8080",
        knowledge_base_id=7,
        transport=httpx.MockTransport(handler),
    )
    feature = FeatureObservation(
        feature_id="NCBITaxon:102106",
        feature_name="Collinsella",
        feature_type="microbe",
        value=2.1,
        unit="percent",
        provenance=Provenance(source="test", source_version="v1"),
    )
    claims = await adapter.search_claims(ClaimQuery(features=[feature], limit=10))
    assert adapter.search_path == "/knowledge-bases/{knowledge_base_id}/claims"
    assert len(claims) == 1
    claim = claims[0]
    assert claim.claim_id == "litkg:claim:2"
    assert claim.subject.id == "NCBITaxon:102106"
    assert claim.object.id == "litkg:entity:4"
    assert claim.qualifiers["document_id"] == 11
    assert claim.qualifiers["species"] == "mice"
    assert claim.evidence.source_id == "document:11"
    assert await adapter.version() == "litkg:2.0.0:kb-7"
