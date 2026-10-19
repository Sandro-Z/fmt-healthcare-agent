from __future__ import annotations

from typing import Any

import httpx
from elasticsearch import Elasticsearch

from wgs_fmt_platform.config import get_settings


class HybridKnowledgeSearch:
    def __init__(self, client: Elasticsearch | None = None) -> None:
        settings = get_settings()
        kwargs: dict[str, Any] = {}
        if settings.elasticsearch_api_key:
            kwargs["api_key"] = settings.elasticsearch_api_key
        elif settings.elasticsearch_password_file is not None:
            password = settings.elasticsearch_password_file.read_text().strip()
            if not password:
                raise ValueError("Elasticsearch password file is empty")
            kwargs["basic_auth"] = (settings.elasticsearch_username, password)
        self.client = client or Elasticsearch(settings.elasticsearch_url, **kwargs)
        self.index = settings.elasticsearch_index
        self.dimensions = settings.embedding_dimensions
        self.settings = settings

    def ensure_index(self) -> None:
        if self.client.indices.exists(index=self.index):
            return
        self.client.indices.create(index=self.index, mappings={"properties": {"title": {"type": "text"}, "content": {"type": "text"}, "source": {"type": "keyword"}, "document_id": {"type": "keyword"}, "metadata": {"type": "object", "enabled": False}, "embedding": {"type": "dense_vector", "dims": self.dimensions, "index": True, "similarity": "cosine"}}})

    def index_document(self, document_id: str, *, title: str, content: str, source: str, embedding: list[float] | None = None, metadata: dict[str, Any] | None = None) -> None:
        if embedding is not None and len(embedding) != self.dimensions:
            raise ValueError(f"embedding must contain {self.dimensions} values")
        body: dict[str, Any] = {"title": title, "content": content, "source": source, "document_id": document_id, "metadata": metadata or {}}
        if embedding is not None:
            body["embedding"] = embedding
        self.client.index(index=self.index, id=document_id, document=body, refresh=False)

    @staticmethod
    def _merge(rankings: list[list[dict[str, Any]]], limit: int) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for ranking in rankings:
            for rank, item in enumerate(ranking, 1):
                key = str(item.get("id"))
                row = merged.setdefault(key, {**item, "score": 0.0, "channels": []})
                row["score"] += 1.0 / (60 + rank)
                row["channels"].append(item.get("channel", "unknown"))
        return sorted(merged.values(), key=lambda row: row["score"], reverse=True)[:limit]

    def search(self, query: str, *, vector: list[float] | None = None, limit: int = 10) -> list[dict[str, Any]]:
        keyword = self.client.search(index=self.index, query={"multi_match": {"query": query, "fields": ["title^2", "content"]}}, size=limit)
        keyword_rows = [{"id": hit["_id"], **hit["_source"], "channel": "keyword", "raw_score": hit["_score"]} for hit in keyword["hits"]["hits"]]
        rankings = [keyword_rows]
        if vector is not None:
            if len(vector) != self.dimensions:
                raise ValueError(f"query vector must contain {self.dimensions} values")
            dense = self.client.search(index=self.index, knn={"field": "embedding", "query_vector": vector, "k": limit, "num_candidates": max(50, limit * 5)}, size=limit)
            rankings.append([{"id": hit["_id"], **hit["_source"], "channel": "vector", "raw_score": hit["_score"]} for hit in dense["hits"]["hits"]])
        return self._merge(rankings, limit)

    async def graph_search(self, query: str, limit: int) -> list[dict[str, Any]]:
        path = self.settings.graph_text_search_path.format(knowledge_base_id=self.settings.claim_api_knowledge_base_id)
        headers = {"Authorization": f"Bearer {self.settings.claim_api_token}"} if self.settings.claim_api_token else {}
        async with httpx.AsyncClient(base_url=self.settings.claim_api_url, headers=headers, timeout=self.settings.claim_api_timeout) as client:
            response = await client.get(path, params={"q": query, "limit": limit})
            response.raise_for_status()
            payload = response.json()
        rows = payload.get("claims", payload.get("items", payload if isinstance(payload, list) else []))
        return [{"id": f"graph:{row.get('id', index)}", "title": row.get("subject_text", "") + " → " + row.get("object_text", ""), "content": row.get("evidence_text", row.get("sentence", "")), "source": "knowledge-graph", "channel": "graph", "metadata": row} for index, row in enumerate(rows[:limit])]

    async def fused_search(self, query: str, *, vector: list[float] | None = None, limit: int = 10) -> dict[str, Any]:
        errors: list[str] = []
        try:
            elastic = self.search(query, vector=vector, limit=limit)
        except Exception as exc:
            elastic = []
            errors.append(f"elasticsearch: {exc}")
        try:
            graph = await self.graph_search(query, limit)
        except Exception as exc:
            graph = []
            errors.append(f"knowledge_graph: {exc}")
        return {"results": self._merge([elastic, graph], limit), "errors": errors, "degraded": bool(errors)}
