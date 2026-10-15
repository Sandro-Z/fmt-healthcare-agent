import json

import httpx
import pytest

from wgs_fmt_platform.knowledge import LitKGDocumentClient, UploadDocument


@pytest.mark.asyncio
async def test_document_upload_status_and_claim_contract() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(202, json={"batch_id": 9, "status": "queued"})
        if request.url.path == "/knowledge-bases/7/documents":
            return httpx.Response(
                200,
                json={
                    "documents": [
                        {"id": 4, "status": "done", "claim_count": 95}
                    ]
                },
            )
        if request.url.path == "/knowledge-bases/7/batches":
            return httpx.Response(200, json={"batches": [{"id": 9, "status": "done"}]})
        if request.url.path == "/documents/4/claims":
            return httpx.Response(
                200,
                json={"claims": [{"id": 343, "document_id": 4}]},
            )
        return httpx.Response(404)

    client = LitKGDocumentClient(
        "http://litkg.test",
        knowledge_base_id=7,
        transport=httpx.MockTransport(handler),
    )
    uploaded = await client.upload_documents(
        [UploadDocument("paper.pdf", b"%PDF-test")],
        batch_name="fmt-evidence",
    )
    documents = await client.list_documents()
    batches = await client.list_batches()
    claims = await client.get_document_claims(4)

    assert uploaded == {"batch_id": 9, "status": "queued"}
    assert documents["documents"][0]["claim_count"] == 95
    assert batches["batches"][0]["status"] == "done"
    assert claims["claims"][0]["id"] == 343
    assert requests[0].url.path == "/knowledge-bases/7/documents"
    body = requests[0].content.decode("utf-8", errors="ignore")
    assert "paper.pdf" in body
    assert "fmt-evidence" in body


@pytest.mark.asyncio
async def test_document_client_rejects_non_object_response() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=json.dumps([]))

    client = LitKGDocumentClient(
        "http://litkg.test",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(Exception, match="JSON object"):
        await client.list_documents()
