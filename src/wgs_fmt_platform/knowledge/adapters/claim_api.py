from __future__ import annotations

import hashlib
import json
from typing import Any

import httpx

from wgs_fmt_platform.contracts import KnowledgeClaim, Provenance
from wgs_fmt_platform.contracts.models import ClaimEntity, ClaimEvidence
from wgs_fmt_platform.knowledge.base import ClaimQuery


class ClaimApiContractError(RuntimeError):
    pass


class ClaimApiAdapter:
    """OpenAPI-aware adapter for an HTTP REST Claim knowledge service."""

    _WRAPPER_KEYS = ("claims", "items", "results", "records", "data")

    def __init__(
        self,
        base_url: str,
        token: str = "",
        timeout: float = 20.0,
        *,
        openapi_path: str = "/openapi.json",
        search_path: str = "",
        search_method: str = "AUTO",
        version_path: str = "",
        knowledge_base_id: int | None = None,
        scan_limit: int = 1000,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.openapi_path = self._path(openapi_path)
        self.search_path = self._path(search_path) if search_path else ""
        self.search_method = search_method.upper()
        self.version_path = self._path(version_path) if version_path else ""
        self.knowledge_base_id = knowledge_base_id
        self.scan_limit = min(1000, max(1, scan_limit))
        self.transport = transport
        self._last_version = "unknown"
        self._openapi: dict[str, Any] | None = None

    @staticmethod
    def _path(path: str) -> str:
        return "/" + path.lstrip("/")

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers=self._headers(),
            transport=self.transport,
        )

    async def probe(self) -> dict[str, Any]:
        async with self._client() as client:
            response = await client.get(self.openapi_path)
            response.raise_for_status()
        document = response.json()
        if not isinstance(document, dict) or not isinstance(document.get("paths"), dict):
            raise ClaimApiContractError("OpenAPI document has no paths object")
        self._openapi = document
        self._last_version = str(document.get("info", {}).get("version", "unknown"))
        candidates = self._claim_operations(document)
        if not self.search_path and candidates:
            selected = candidates[0]
            self.search_path = selected["path"]
            self.search_method = selected["method"]
        return {
            "base_url": self.base_url,
            "openapi_version": document.get("openapi", "unknown"),
            "service_title": document.get("info", {}).get("title", "unknown"),
            "service_version": self._last_version,
            "claim_operations": candidates,
            "selected_search_path": self.search_path or None,
            "selected_search_method": self.search_method,
        }

    @staticmethod
    def _claim_operations(document: dict[str, Any]) -> list[dict[str, str]]:
        candidates: list[tuple[int, dict[str, str]]] = []
        for path, operations in document.get("paths", {}).items():
            if not isinstance(operations, dict):
                continue
            for method, operation in operations.items():
                method_upper = method.upper()
                if method_upper not in {"GET", "POST"} or not isinstance(operation, dict):
                    continue
                text = " ".join(
                    [
                        path,
                        str(operation.get("operationId", "")),
                        str(operation.get("summary", "")),
                        " ".join(str(tag) for tag in operation.get("tags", [])),
                    ]
                ).lower()
                if "claim" not in text:
                    continue
                score = 10
                if any(word in text for word in ("search", "query", "list", "retrieve")):
                    score += 8
                if "knowledge-base" in text or "knowledge_base" in text:
                    score += 10
                if method_upper == "POST":
                    score += 2
                candidates.append(
                    (
                        score,
                        {
                            "path": path,
                            "method": method_upper,
                            "operation_id": str(operation.get("operationId", "")),
                            "summary": str(operation.get("summary", "")),
                        },
                    )
                )
        return [item for _, item in sorted(candidates, key=lambda pair: pair[0], reverse=True)]

    @staticmethod
    def _payload(query: ClaimQuery) -> dict[str, Any]:
        return {
            "feature_ids": [feature.feature_id for feature in query.features],
            "features": [
                {
                    "id": feature.feature_id,
                    "name": feature.feature_name,
                    "type": feature.feature_type,
                    "value": feature.value,
                    "unit": feature.unit,
                    "status": feature.status,
                }
                for feature in query.features
            ],
            "task": query.task,
            "population": query.population,
            "knowledge_version": query.knowledge_version,
            "limit": query.limit,
        }

    async def search_claims(self, query: ClaimQuery) -> list[KnowledgeClaim]:
        if not self.search_path or self.search_method == "AUTO":
            await self.probe()
        if not self.search_path:
            raise ClaimApiContractError(
                "no Claim operation found in OpenAPI; set WGS_CLAIM_API_SEARCH_PATH"
            )
        payload = self._payload(query)
        resolved_path = self.search_path
        if "{knowledge_base_id}" in resolved_path:
            if self.knowledge_base_id is None:
                raise ClaimApiContractError(
                    "Claim route requires knowledge_base_id; set WGS_CLAIM_API_KNOWLEDGE_BASE_ID"
                )
            resolved_path = resolved_path.replace(
                "{knowledge_base_id}", str(self.knowledge_base_id)
            )
        async with self._client() as client:
            if self.search_method == "GET":
                response = await client.get(
                    resolved_path,
                    params={
                        "limit": self.scan_limit,
                        "offset": 0,
                    },
                )
            elif self.search_method == "POST":
                response = await client.post(resolved_path, json=payload)
            else:
                raise ClaimApiContractError(
                    f"unsupported Claim search method: {self.search_method}"
                )
            response.raise_for_status()
            data = response.json()
        if isinstance(data, dict):
            self._last_version = str(
                data.get("knowledge_version")
                or data.get("version")
                or self._last_version
            )
        normalized = [self._normalize_claim(item) for item in self._items(data)]
        if query.features:
            normalized = [
                claim for claim in normalized if self._matches_features(claim, query)
            ]
        return normalized[: query.limit]

    @staticmethod
    def _matches_features(claim: KnowledgeClaim, query: ClaimQuery) -> bool:
        claim_values = {
            claim.subject.id.casefold(),
            claim.subject.name.casefold(),
            claim.object.id.casefold(),
            claim.object.name.casefold(),
        }
        for feature in query.features:
            feature_values = {
                feature.feature_id.casefold(),
                feature.feature_name.casefold(),
            }
            if claim_values & feature_values:
                return True
            for feature_value in feature_values:
                if len(feature_value) >= 4 and any(
                    feature_value in claim_value or claim_value in feature_value
                    for claim_value in claim_values
                    if len(claim_value) >= 4
                ):
                    return True
        return False

    @classmethod
    def _items(cls, data: Any) -> list[dict[str, Any]]:
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if not isinstance(data, dict):
            raise ClaimApiContractError("Claim response must be a JSON object or array")
        for key in cls._WRAPPER_KEYS:
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                for nested_key in cls._WRAPPER_KEYS:
                    nested = value.get(nested_key)
                    if isinstance(nested, list):
                        return [item for item in nested if isinstance(item, dict)]
        if any(key in data for key in ("subject", "source", "head")):
            return [data]
        raise ClaimApiContractError(
            "Claim response contains none of claims/items/results/records/data"
        )

    @classmethod
    def _normalize_claim(cls, item: dict[str, Any]) -> KnowledgeClaim:
        try:
            return KnowledgeClaim.model_validate(item)
        except Exception:
            pass

        if item.get("subject_text") is not None and item.get("object_text") is not None:
            return cls._normalize_litkg_claim(item)

        subject_raw = cls._first(item, "subject", "source", "head", "entity1")
        object_raw = cls._first(item, "object", "target", "tail", "entity2")
        predicate = cls._first(item, "predicate", "relation", "relationship", "claim_type")
        if subject_raw is None or object_raw is None or not predicate:
            raise ClaimApiContractError(
                "Claim record must contain subject/source, predicate/relation, and object/target"
            )
        subject = cls._entity(subject_raw, fallback_type="Unknown")
        object_entity = cls._entity(object_raw, fallback_type="Unknown")
        evidence_raw = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
        source_id = str(
            cls._first(evidence_raw, "source_id", "pmid", "doi", "id")
            or cls._first(item, "source_id", "pmid", "doi", "document_id")
            or "unknown"
        )
        canonical = json.dumps(
            [subject.id, str(predicate), object_entity.id, source_id],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        claim_id = str(
            cls._first(item, "claim_id", "id", "uuid")
            or "claim-" + hashlib.sha256(canonical.encode()).hexdigest()[:20]
        )
        api_version = str(cls._first(item, "knowledge_version", "version") or "unknown")
        return KnowledgeClaim(
            claim_id=claim_id,
            subject=subject,
            predicate=str(predicate),
            object=object_entity,
            qualifiers=item.get("qualifiers", {}) if isinstance(item.get("qualifiers"), dict) else {},
            evidence=ClaimEvidence(
                source_type=str(
                    cls._first(evidence_raw, "source_type", "type")
                    or cls._first(item, "source_type")
                    or "literature"
                ),
                source_id=source_id,
                sentence=str(
                    cls._first(evidence_raw, "sentence", "text", "quote")
                    or cls._first(item, "sentence", "evidence_text", "text")
                    or ""
                ),
                evidence_level=str(
                    cls._first(evidence_raw, "evidence_level", "level")
                    or cls._first(item, "evidence_level")
                    or "unknown"
                ),
            ),
            parser_score=cls._float_or_none(
                cls._first(item, "parser_score", "confidence", "score")
            ),
            entity_resolution_score=cls._float_or_none(
                cls._first(item, "entity_resolution_score", "linking_score")
            ),
            review_status=str(cls._first(item, "review_status", "status") or "machine_extracted"),
            provenance=Provenance(
                source="claim-rest-api",
                source_version=api_version,
                parameters={"base_url": "external-rest-api"},
            ),
        )

    @classmethod
    def _normalize_litkg_claim(cls, item: dict[str, Any]) -> KnowledgeClaim:
        claim_json = item.get("claim_json") if isinstance(item.get("claim_json"), dict) else {}
        subject_id = (
            item.get("subject_normalized_id")
            or f"litkg:entity:{item.get('subject_entity_id', item.get('subject_text'))}"
        )
        object_id = (
            item.get("object_normalized_id")
            or f"litkg:entity:{item.get('object_entity_id', item.get('object_text'))}"
        )
        qualifiers = dict(
            claim_json.get("qualifiers", {})
            if isinstance(claim_json.get("qualifiers"), dict)
            else {}
        )
        qualifiers.update(
            {
                "document_id": item.get("document_id"),
                "chunk_id": item.get("chunk_id"),
                "filename": item.get("filename"),
                "section_title": item.get("section_title"),
                "negated": bool(item.get("negated", False)),
                "speculative": bool(item.get("speculative", False)),
            }
        )
        qualifiers = {key: value for key, value in qualifiers.items() if value is not None}
        source_id = (
            f"document:{item['document_id']}" if item.get("document_id") is not None
            else str(item.get("filename") or "unknown")
        )
        return KnowledgeClaim(
            claim_id=f"litkg:claim:{item.get('id')}",
            subject=ClaimEntity(
                id=str(subject_id),
                name=str(item.get("subject_text")),
                type=str(item.get("subject_type") or "Unknown"),
            ),
            predicate=str(item.get("predicate")),
            object=ClaimEntity(
                id=str(object_id),
                name=str(item.get("object_text")),
                type=str(item.get("object_type") or "Unknown"),
            ),
            qualifiers=qualifiers,
            evidence=ClaimEvidence(
                source_type="literature",
                source_id=source_id,
                sentence=str(item.get("evidence_text") or ""),
                evidence_level="unknown",
            ),
            parser_score=cls._float_or_none(item.get("confidence")),
            review_status="machine_extracted",
            provenance=Provenance(
                source="litkg-rest-api",
                source_version="2.0.0",
                parameters={
                    "document_id": item.get("document_id"),
                    "filename": item.get("filename"),
                },
            ),
        )

    @staticmethod
    def _first(mapping: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            value = mapping.get(key)
            if value is not None and value != "":
                return value
        return None

    @classmethod
    def _entity(cls, value: Any, fallback_type: str) -> ClaimEntity:
        if isinstance(value, dict):
            entity_id = str(cls._first(value, "id", "entity_id", "curie", "identifier") or "")
            name = str(cls._first(value, "name", "label", "text", "title") or entity_id)
            entity_type = str(cls._first(value, "type", "entity_type", "category") or fallback_type)
        else:
            name = str(value)
            entity_id = name
            entity_type = fallback_type
        if not entity_id:
            entity_id = name
        return ClaimEntity(id=entity_id, name=name, type=entity_type)

    @staticmethod
    def _float_or_none(value: Any) -> float | None:
        if value is None:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return min(1.0, max(0.0, number))

    async def version(self) -> str:
        if self._last_version != "unknown":
            return self._version_label()
        if self.version_path:
            async with self._client() as client:
                response = await client.get(self.version_path)
                response.raise_for_status()
            payload = response.json()
            self._last_version = str(
                payload.get("version", "unknown") if isinstance(payload, dict) else "unknown"
            )
            return self._version_label()
        await self.probe()
        return self._version_label()

    def _version_label(self) -> str:
        if self.knowledge_base_id is None:
            return self._last_version
        return f"litkg:{self._last_version}:kb-{self.knowledge_base_id}"
