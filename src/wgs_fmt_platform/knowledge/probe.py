from __future__ import annotations

import asyncio
import json

from wgs_fmt_platform.config import get_settings
from wgs_fmt_platform.knowledge.adapters import ClaimApiAdapter


async def probe() -> dict[str, object]:
    settings = get_settings()
    adapter = ClaimApiAdapter(
        settings.claim_api_url,
        settings.claim_api_token,
        settings.claim_api_timeout,
        openapi_path=settings.claim_api_openapi_path,
        search_path=settings.claim_api_search_path,
        search_method=settings.claim_api_search_method,
        version_path=settings.claim_api_version_path,
        knowledge_base_id=settings.claim_api_knowledge_base_id,
        scan_limit=settings.claim_api_scan_limit,
    )
    return await adapter.probe()


def main() -> None:
    print(json.dumps(asyncio.run(probe()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
