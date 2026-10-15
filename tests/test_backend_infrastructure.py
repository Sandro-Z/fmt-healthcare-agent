from __future__ import annotations

import json

from wgs_fmt_platform.infrastructure.database import hash_password
from wgs_fmt_platform.infrastructure.memory import RedisMemoryStore
from wgs_fmt_platform.infrastructure.search import HybridKnowledgeSearch
from wgs_fmt_platform.infrastructure.sandbox import SandboxExecutor, SandboxPolicy


class FakeRedis:
    def __init__(self) -> None:
        self.rows: dict[str, list[tuple[float, str]]] = {}
        self.expirations: dict[str, int] = {}

    def zadd(self, key, mapping):
        self.rows.setdefault(key, []).extend((score, value) for value, score in mapping.items())

    def expire(self, key, ttl):
        self.expirations[key] = ttl

    def zrevrange(self, key, start, end):
        return [value for _, value in sorted(self.rows.get(key, []), reverse=True)][start:end + 1]

    def delete(self, *keys):
        count = 0
        for key in keys:
            count += int(key in self.rows)
            self.rows.pop(key, None)
        return count


def test_password_hash_is_salted_and_does_not_store_plaintext() -> None:
    first = hash_password("a-strong-test-password")
    second = hash_password("a-strong-test-password")
    assert first.startswith("pbkdf2_sha256$310000$")
    assert first != second
    assert "a-strong-test-password" not in first


def test_redis_memory_supports_short_and_long_scopes() -> None:
    client = FakeRedis()
    store = RedisMemoryStore(client=client)
    store.remember("u1", "short note", scope="short")
    store.remember("u1", "long note", scope="long")
    assert store.recall("u1", scope="short")[0]["content"] == "short note"
    assert store.recall("u1", scope="long")[0]["content"] == "long note"
    assert client.expirations["wgs:memory:short:u1"] == store.short_ttl


def test_rrf_fuses_keyword_vector_and_graph_without_duplicate_documents() -> None:
    keyword = [{"id": "a", "channel": "keyword"}, {"id": "b", "channel": "keyword"}]
    vector = [{"id": "b", "channel": "vector"}, {"id": "c", "channel": "vector"}]
    graph = [{"id": "g", "channel": "graph"}]
    result = HybridKnowledgeSearch._merge([keyword, vector, graph], 10)
    assert [row["id"] for row in result][0] == "b"
    assert set(result[0]["channels"]) == {"keyword", "vector"}
    assert len(result) == 4


def test_process_sandbox_enforces_workspace_and_command_allowlist(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    executor = SandboxExecutor(SandboxPolicy(mode="process", workspace=workspace, allowed_root=tmp_path, allowed_commands=frozenset({"python3"})))
    assert executor.command(["python3", "-V"]) == ["python3", "-V"]
    try:
        executor.command(["curl", "https://example.com"])
    except PermissionError:
        pass
    else:
        raise AssertionError("unlisted commands must be denied")


def test_sandbox_rejects_workspace_outside_allowed_root(tmp_path) -> None:
    try:
        SandboxPolicy(mode="process", workspace=tmp_path.parent, allowed_root=tmp_path, allowed_commands=frozenset({"python3"})).validate()
    except ValueError:
        pass
    else:
        raise AssertionError("workspace traversal must be rejected")
