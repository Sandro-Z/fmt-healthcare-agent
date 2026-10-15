from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


class LitKGDocumentError(RuntimeError):
    """Raised when the LitKG document ingestion contract is not satisfied."""


@dataclass(frozen=True)
class UploadDocument:
    filename: str
    content: bytes
    content_type: str = "application/pdf"


class LitKGDocumentClient:
    """Small REST client for LitKG document ingestion and status tracking."""

    def __init__(
        self,
        base_url: str,
        *,
        token: str = "",
        timeout: float = 60.0,
        knowledge_base_id: int = 7,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.knowledge_base_id = knowledge_base_id
        self.transport = transport

    @classmethod
    def from_settings(cls) -> "LitKGDocumentClient":
        from wgs_fmt_platform.config import get_settings

        settings = get_settings()
        return cls(
            settings.claim_api_url,
            token=settings.claim_api_token,
            timeout=max(60.0, settings.claim_api_timeout),
            knowledge_base_id=settings.claim_api_knowledge_base_id,
        )

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._headers(),
            timeout=self.timeout,
            transport=self.transport,
        )

    @staticmethod
    def _object(response: httpx.Response) -> dict[str, Any]:
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise LitKGDocumentError("LitKG response must be a JSON object")
        return payload

    async def upload_documents(
        self,
        documents: list[UploadDocument],
        *,
        batch_name: str | None = None,
        force_reprocess: bool = False,
    ) -> dict[str, Any]:
        if not documents:
            raise ValueError("at least one document is required")
        files = [
            ("files", (item.filename, item.content, item.content_type))
            for item in documents
        ]
        data = {
            "force_reprocess": "true" if force_reprocess else "false",
        }
        if batch_name:
            data["batch_name"] = batch_name
        path = f"/knowledge-bases/{self.knowledge_base_id}/documents"
        async with self._client() as client:
            response = await client.post(path, files=files, data=data)
        return self._object(response)

    async def list_documents(self, *, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        path = f"/knowledge-bases/{self.knowledge_base_id}/documents"
        async with self._client() as client:
            response = await client.get(path, params={"limit": limit, "offset": offset})
        return self._object(response)

    async def get_document(self, document_id: int) -> dict[str, Any]:
        async with self._client() as client:
            response = await client.get(f"/documents/{document_id}")
        return self._object(response)

    async def list_batches(self, *, limit: int = 50) -> dict[str, Any]:
        path = f"/knowledge-bases/{self.knowledge_base_id}/batches"
        async with self._client() as client:
            response = await client.get(path, params={"limit": limit})
        return self._object(response)

    async def get_batch(self, batch_id: int) -> dict[str, Any]:
        async with self._client() as client:
            response = await client.get(f"/ingestion-batches/{batch_id}")
        return self._object(response)

    async def get_document_claims(
        self, document_id: int, *, limit: int = 1000, offset: int = 0
    ) -> dict[str, Any]:
        async with self._client() as client:
            response = await client.get(
                f"/documents/{document_id}/claims",
                params={"limit": limit, "offset": offset},
            )
        return self._object(response)

    def document_claims_url(self, document_id: int) -> str:
        return f"{self.base_url}/documents/{document_id}/claims"
