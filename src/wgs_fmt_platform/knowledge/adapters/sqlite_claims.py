from __future__ import annotations

import sqlite3
from pathlib import Path

from wgs_fmt_platform.contracts import KnowledgeClaim
from wgs_fmt_platform.knowledge.base import ClaimQuery


class SqliteClaimAdapter:
    """Read-only fallback for normalized Claim JSON records."""

    def __init__(self, database: Path, default_version: str = "local") -> None:
        self.database = database.resolve()
        self.default_version = default_version

    async def search_claims(self, query: ClaimQuery) -> list[KnowledgeClaim]:
        if not self.database.exists() or not query.features:
            return []
        feature_ids = list(dict.fromkeys(item.feature_id for item in query.features))
        placeholders = ",".join("?" for _ in feature_ids)
        sql = f"""
            SELECT payload_json
            FROM claims
            WHERE active = 1
              AND (subject_id IN ({placeholders}) OR object_id IN ({placeholders}))
              AND knowledge_version IN (?, 'current')
            ORDER BY human_verified DESC, parser_score DESC
            LIMIT ?
        """
        connection = sqlite3.connect(f"file:{self.database}?mode=ro", uri=True)
        try:
            rows = connection.execute(
                sql,
                (*feature_ids, *feature_ids, query.knowledge_version, query.limit),
            ).fetchall()
        finally:
            connection.close()
        return [KnowledgeClaim.model_validate_json(row[0]) for row in rows]

    async def version(self) -> str:
        if not self.database.exists():
            return f"{self.default_version}-unavailable"
        connection = sqlite3.connect(f"file:{self.database}?mode=ro", uri=True)
        try:
            row = connection.execute(
                "SELECT value FROM metadata WHERE key = 'knowledge_version'"
            ).fetchone()
        except sqlite3.Error:
            row = None
        finally:
            connection.close()
        return str(row[0]) if row else self.default_version

