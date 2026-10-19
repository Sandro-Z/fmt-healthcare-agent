#!/usr/bin/env python3
"""回填现有文献元数据到 SQLite 数据库"""

import json
import sqlite3
import sys
from pathlib import Path
from wgs_fmt_platform.paths import knowledge_db_path, runtime_path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = knowledge_db_path()
DOCUMENTS_DIR = runtime_path("WGS_KB_DIR", "knowledge", "documents")
INDEX_PATH = DOCUMENTS_DIR / "papers" / "_index.json"


def get_all_pmids(index_path: Path = INDEX_PATH) -> list[str]:
    """从 _index.json 提取所有 PMID"""
    if not index_path.exists():
        print(f"⚠️  Index not found: {index_path}")
        return []

    data = json.loads(index_path.read_text(encoding="utf-8"))
    pmids = list(data.get("pmids", {}).keys())
    print(f"📋 Found {len(pmids)} PMIDs in index")
    return pmids


def markdown_to_db(conn: sqlite3.Connection):
    """从现有 Markdown 文件补充元数据（无需重新调用 PubMed API）"""
    papers_dir = DOCUMENTS_DIR / "papers"
    markdown_files = list(papers_dir.glob("**/*.md"))

    updated = 0
    for md_file in markdown_files:
        if md_file.name.startswith("_"):
            continue

        content = md_file.read_text(encoding="utf-8")
        pmid = _extract_pmid(content)
        if not pmid:
            continue

        # 检查是否已存在于数据库
        existing = conn.execute("SELECT id FROM papers WHERE pmid = ?", (pmid,)).fetchone()
        if existing:
            # 用 Markdown 内容补充 study_context（PMC 全文摘要）
            conn.execute(
                "UPDATE papers SET study_context = ?, last_updated = CURRENT_TIMESTAMP WHERE pmid = ?",
                (content[:5000], pmid),
            )
            updated += 1
            print(f"   ✅ PMID {pmid}: study_context updated from {md_file.name}")

    conn.commit()
    print(f"   📝 Updated {updated} papers from Markdown files")
    return updated


def _extract_pmid(content: str) -> str | None:
    """从 Markdown 内容提取 PMID"""
    import re
    # 格式: **PMID**: [40659786](https://pubmed.ncbi.nlm.nih.gov/40659786/)
    m = re.search(r'\*\*PMID\*\*:\s*\[(\d+)\]', content)
    if m:
        return m.group(1)
    # 格式: - [1] PMID: 12345678
    m = re.search(r'PMID[:=]\s*(\d+)', content)
    return m.group(1) if m else None


def main():
    import argparse

    parser = argparse.ArgumentParser(description="回填现有文献到 SQLite 知识库")
    parser.add_argument("--fetch", action="store_true", help="通过 PubMed API 重新抓取全部文献")
    parser.add_argument("--markdown", action="store_true", help="从现有 Markdown 文件补充元数据")
    parser.add_argument("--all", action="store_true", help="执行全部操作")
    args = parser.parse_args()

    if not any([args.fetch, args.markdown, args.all]):
        parser.print_help()
        print("\n💡 推荐用法：")
        print("  python backfill_existing.py --all    # 全量回填")
        print("  python backfill_existing.py --fetch  # 只从 PubMed API 抓取")
        print("  python backfill_existing.py --markdown  # 只从 Markdown 补充")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = ON")

    do_fetch = args.fetch or args.all
    do_md = args.markdown or args.all

    if do_fetch:
        print("📥 Step 1: Fetching from PubMed API...")
        pmids = get_all_pmids()
        if pmids:
            sys.path.insert(0, str(ROOT.parent.parent))
            from knowledge_base.scripts.pubmed_pipeline import batch_process
            batch_process(pmids, DB_PATH)
        else:
            print("   ⚠️  No PMIDs found, skipping.")

    if do_md:
        print("\n📝 Step 2: Updating from Markdown files...")
        markdown_to_db(conn)

    # 验证
    count = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
    print(f"\n✅ Backfill complete: {count} papers in database")

    conn.close()


if __name__ == "__main__":
    main()
