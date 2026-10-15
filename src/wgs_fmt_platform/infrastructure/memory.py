from __future__ import annotations

import json
import time
import uuid
from typing import Any

from redis import Redis

from wgs_fmt_platform.config import get_settings


class RedisMemoryStore:
    def __init__(self, client: Redis | None = None) -> None:
        settings = get_settings()
        self.client = client or Redis.from_url(settings.redis_url, decode_responses=True)
        self.short_ttl = settings.memory_short_ttl_seconds
        self.long_ttl = settings.memory_long_ttl_seconds

    def remember(self, user_id: str, content: str, *, scope: str = "short", conversation_id: str = "", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        if scope not in {"short", "long"}:
            raise ValueError("memory scope must be short or long")
        item = {"id": str(uuid.uuid4()), "user_id": user_id, "conversation_id": conversation_id, "scope": scope, "content": content, "metadata": metadata or {}, "created_at": time.time()}
        key = f"wgs:memory:{scope}:{user_id}"
        self.client.zadd(key, {json.dumps(item, ensure_ascii=False): item["created_at"]})
        ttl = self.short_ttl if scope == "short" else self.long_ttl
        if ttl > 0:
            self.client.expire(key, ttl)
        return item

    def recall(self, user_id: str, *, scope: str = "short", limit: int = 20) -> list[dict[str, Any]]:
        key = f"wgs:memory:{scope}:{user_id}"
        rows = self.client.zrevrange(key, 0, max(0, limit - 1))
        return [json.loads(row) for row in rows]

    def forget(self, user_id: str, *, scope: str | None = None) -> int:
        scopes = [scope] if scope else ["short", "long"]
        return int(self.client.delete(*(f"wgs:memory:{value}:{user_id}" for value in scopes)))
