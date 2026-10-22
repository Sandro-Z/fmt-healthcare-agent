#!/usr/bin/env python3
"""初始化知识库数据库 (SQLite)"""

import sqlite3
from datetime import datetime
from pathlib import Path
from wgs_fmt_platform.paths import knowledge_db_path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "schema.sql"
DB_PATH = knowledge_db_path()


def init_database(db_path: Path = DB_PATH, schema_path: Path = SCHEMA_PATH) -> sqlite3.Connection:
    """读取 schema.sql 并创建所有表，返回数据库连接"""
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema not found: {schema_path}")

    schema_sql = schema_path.read_text(encoding="utf-8")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(schema_sql)

    # 写入 schema 版本记录
    conn.execute(
        "INSERT OR REPLACE INTO schema_version (version, description) VALUES (?, ?)",
        ("1.0.0", f"Initial schema applied at {datetime.now().isoformat()}"),
    )
    conn.commit()

    # 验证表是否创建
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    print(f"✅ Database initialized: {db_path}")
    print(f"   Tables created: {len(tables)}")
    for t in tables:
        print(f"     - {t[0]}")

    return conn


if __name__ == "__main__":
    init_database()
