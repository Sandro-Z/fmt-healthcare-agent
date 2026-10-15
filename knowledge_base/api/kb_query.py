#!/usr/bin/env python3
"""
知识库结构化查询 API

支持：
- 多条件组合查询（年份、IF、疾病、物种、通路、代谢物、药物等）
- 模糊搜索标题/摘要
- 关联表 JOIN 查询
- 分页支持
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "kb.db"


class KnowledgeBaseQuery:
    """知识库查询入口"""

    def __init__(self, db_path: Path | str = DB_PATH):
        self.db_path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    # ─── 文献查询 ───

    def search_papers(
        self,
        *,
        query: str | None = None,            # 标题/摘要关键词
        year_from: int | None = None,        # 起始年份
        year_to: int | None = None,          # 截止年份
        min_if: float | None = None,         # 最低影响因子
        disease_code: str | None = None,     # ICD-11 编码（精确匹配）
        disease_keyword: str | None = None,  # 疾病关键词（like 匹配）
        microbe: str | None = None,          # 物种名（学名/中文名）
        pathway: str | None = None,          # 代谢通路关键词
        metabolite: str | None = None,       # 代谢物关键词
        drug: str | None = None,             # 药物关键词
        sample_source: str | None = None,    # 样本来源
        sequencing: str | None = None,       # 测序策略
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """
        多条件组合查询文献

        Examples:
            >>> kb = KnowledgeBaseQuery()
            >>> # 查询 2020 年后 IF>10 的糖尿病相关文献
            >>> kb.search_papers(disease_keyword="diabetes", year_from=2020, min_if=10)
            >>> # 查询涉及 Akkermansia 的文献
            >>> kb.search_papers(microbe="Akkermansia")
        """
        conn = self._connect()
        try:
            where_clauses = []
            params: list[Any] = []

            # 关键词搜索（标题 + 摘要）
            if query:
                where_clauses.append("(p.title LIKE ? OR p.abstract LIKE ?)")
                kw = f"%{query}%"
                params.extend([kw, kw])

            # 年份范围
            if year_from is not None:
                where_clauses.append("p.publication_year >= ?")
                params.append(year_from)
            if year_to is not None:
                where_clauses.append("p.publication_year <= ?")
                params.append(year_to)

            # 影响因子
            if min_if is not None:
                where_clauses.append("p.impact_factor >= ?")
                params.append(min_if)

            # ICD-11 疾病编码
            if disease_code:
                where_clauses.append("p.target_disease_code = ?")
                params.append(disease_code)

            if disease_keyword:
                where_clauses.append(
                    "(p.target_disease_name LIKE ? OR "
                    "p.target_disease_code IN (SELECT code FROM icd11_diseases WHERE name_en LIKE ?))"
                )
                kw = f"%{disease_keyword}%"
                params.extend([kw, kw])

            # 物种（学名/中文名）→ 子查询 key_microbes
            if microbe:
                where_clauses.append("""
                    p.id IN (
                        SELECT paper_id FROM key_microbes
                        WHERE scientific_name LIKE ? OR chinese_name LIKE ?
                    )
                """)
                kw = f"%{microbe}%"
                params.extend([kw, kw])

            # 通路
            if pathway:
                where_clauses.append("""
                    p.id IN (
                        SELECT paper_id FROM functional_pathways
                        WHERE pathway_name LIKE ?
                    )
                """)
                params.append(f"%{pathway}%")

            # 代谢物
            if metabolite:
                where_clauses.append("""
                    p.id IN (
                        SELECT paper_id FROM metabolites
                        WHERE metabolite_name LIKE ?
                    )
                """)
                params.append(f"%{metabolite}%")

            # 药物
            if drug:
                where_clauses.append("""
                    p.id IN (
                        SELECT paper_id FROM drug_microbe_interactions
                        WHERE drug_name LIKE ?
                    )
                """)
                params.append(f"%{drug}%")

            # 样本来源
            if sample_source:
                where_clauses.append("p.sample_source = ?")
                params.append(sample_source)

            # 测序策略
            if sequencing:
                where_clauses.append("p.sequencing_strategy = ?")
                params.append(sequencing)

            # 组装 SQL
            where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
            sql = f"""
                SELECT p.*,
                       GROUP_CONCAT(DISTINCT acc.accession_id) AS accessions,
                       GROUP_CONCAT(DISTINCT km.scientific_name) AS key_microbes
                FROM papers p
                LEFT JOIN accessions acc ON p.id = acc.paper_id
                LEFT JOIN key_microbes km ON p.id = km.paper_id
                WHERE {where_sql}
                GROUP BY p.id
                ORDER BY p.impact_factor DESC, p.publication_year DESC
                LIMIT ? OFFSET ?
            """
            params.extend([limit, offset])

            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ─── 单个文献详情（含所有关联表） ───

    def get_paper_detail(self, pmid: str) -> dict[str, Any] | None:
        """获取文献完整详情，包含所有关联表数据"""
        conn = self._connect()
        try:
            paper = conn.execute(
                "SELECT * FROM papers WHERE pmid = ?", (pmid,)
            ).fetchone()
            if not paper:
                return None

            paper_row = dict(paper)

            # 数据集
            paper_row["accessions"] = [
                dict(r) for r in conn.execute(
                    "SELECT * FROM accessions WHERE paper_id = ?",
                    (paper_row["id"],),
                ).fetchall()
            ]

            # 关键微生物
            paper_row["key_microbes"] = [
                dict(r) for r in conn.execute(
                    "SELECT * FROM key_microbes WHERE paper_id = ?",
                    (paper_row["id"],),
                ).fetchall()
            ]

            # 代谢通路
            paper_row["pathways"] = [
                dict(r) for r in conn.execute(
                    "SELECT * FROM functional_pathways WHERE paper_id = ?",
                    (paper_row["id"],),
                ).fetchall()
            ]

            # 代谢物
            paper_row["metabolites"] = [
                dict(r) for r in conn.execute(
                    "SELECT * FROM metabolites WHERE paper_id = ?",
                    (paper_row["id"],),
                ).fetchall()
            ]

            # 干预措施
            paper_row["treatments"] = [
                dict(r) for r in conn.execute(
                    "SELECT * FROM treatments WHERE paper_id = ?",
                    (paper_row["id"],),
                ).fetchall()
            ]

            # 药物-菌群交互
            paper_row["drug_interactions"] = [
                dict(r) for r in conn.execute(
                    "SELECT * FROM drug_microbe_interactions WHERE paper_id = ?",
                    (paper_row["id"],),
                ).fetchall()
            ]

            # 期刊 IF
            if paper_row.get("issn"):
                if_row = conn.execute(
                    "SELECT * FROM journal_impact_factors WHERE issn = ? LIMIT 1",
                    (paper_row["issn"],),
                ).fetchone()
                if if_row:
                    paper_row["journal_if"] = dict(if_row)

            # ICD-11 疾病
            if paper_row.get("target_disease_code"):
                icd = conn.execute(
                    "SELECT * FROM icd11_diseases WHERE code = ?",
                    (paper_row["target_disease_code"],),
                ).fetchone()
                if icd:
                    paper_row["icd11"] = dict(icd)

            return paper_row
        finally:
            conn.close()

    # ─── 统计查询 ───

    def get_stats(self) -> dict[str, Any]:
        """获取知识库统计信息"""
        conn = self._connect()
        try:
            return {
                "total_papers": conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0],
                "total_microbes": conn.execute("SELECT COUNT(DISTINCT scientific_name) FROM key_microbes").fetchone()[0],
                "total_pathways": conn.execute("SELECT COUNT(DISTINCT pathway_name) FROM functional_pathways").fetchone()[0],
                "total_metabolites": conn.execute("SELECT COUNT(DISTINCT metabolite_name) FROM metabolites").fetchone()[0],
                "total_accessions": conn.execute("SELECT COUNT(*) FROM accessions").fetchone()[0],
                "standard_diseases": conn.execute("SELECT COUNT(*) FROM icd11_diseases").fetchone()[0],
                "standard_taxonomy": conn.execute("SELECT COUNT(*) FROM ncbi_taxonomy").fetchone()[0],
                "standard_probiotics": conn.execute("SELECT COUNT(*) FROM probiotics").fetchone()[0],
                "standard_journals": conn.execute("SELECT COUNT(*) FROM journal_impact_factors").fetchone()[0],
                "year_range": conn.execute(
                    "SELECT MIN(publication_year), MAX(publication_year) FROM papers"
                ).fetchone(),
                "disease_distribution": [
                    dict(r) for r in conn.execute(
                        "SELECT target_disease_name, COUNT(*) as count FROM papers "
                        "WHERE target_disease_name IS NOT NULL "
                        "GROUP BY target_disease_name ORDER BY count DESC LIMIT 10"
                    ).fetchall()
                ],
            }
        finally:
            conn.close()

    # ─── 物种查询 ───

    def search_microbes(
        self,
        name: str | None = None,
        chinese_name: str | None = None,
        role: str | None = None,
        is_probiotic: bool | None = None,
    ) -> list[dict[str, Any]]:
        """查询关键微生物"""
        conn = self._connect()
        try:
            where = ["1=1"]
            params: list[Any] = []

            if name:
                where.append("km.scientific_name LIKE ?")
                params.append(f"%{name}%")
            if chinese_name:
                where.append("km.chinese_name LIKE ?")
                params.append(f"%{chinese_name}%")
            if role:
                where.append("km.role = ?")
                params.append(role)
            if is_probiotic is True:
                where.append("km.taxid IN (SELECT taxid FROM probiotics)")
            elif is_probiotic is False:
                where.append("km.taxid NOT IN (SELECT taxid FROM probiotics)")

            sql = f"""
                SELECT km.*, p.title AS paper_title, p.pmid,
                       pr.evidence_level AS probiotic_evidence
                FROM key_microbes km
                JOIN papers p ON km.paper_id = p.id
                LEFT JOIN probiotics pr ON km.taxid = pr.taxid
                WHERE {' AND '.join(where)}
                ORDER BY p.impact_factor DESC
                LIMIT 50
            """
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ─── 获取标准参考数据 ───

    def get_icd11_codes(self, query: str | None = None) -> list[dict[str, Any]]:
        """获取 ICD-11 疾病编码列表"""
        conn = self._connect()
        try:
            if query:
                rows = conn.execute(
                    "SELECT * FROM icd11_diseases WHERE name_en LIKE ? OR name_cn LIKE ? OR code LIKE ?",
                    (f"%{query}%", f"%{query}%", f"%{query}%"),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM icd11_diseases ORDER BY category").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_taxonomy(self, name: str | None = None) -> list[dict[str, Any]]:
        """获取 NCBI 物种分类（含中文名）"""
        conn = self._connect()
        try:
            if name:
                rows = conn.execute(
                    "SELECT * FROM ncbi_taxonomy WHERE scientific_name LIKE ? OR chinese_name LIKE ?",
                    (f"%{name}%", f"%{name}%"),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM ncbi_taxonomy ORDER BY rank, scientific_name LIMIT 100").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_probiotics(self) -> list[dict[str, Any]]:
        """获取益生菌名录"""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT pr.*, nt.chinese_name AS taxonomy_cn FROM probiotics pr "
                "JOIN ncbi_taxonomy nt ON pr.taxid = nt.taxid "
                "ORDER BY pr.evidence_level DESC"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_journal_if(self, journal_name: str | None = None) -> list[dict[str, Any]]:
        """获取期刊影响因子"""
        conn = self._connect()
        try:
            if journal_name:
                rows = conn.execute(
                    "SELECT * FROM journal_impact_factors WHERE journal_name LIKE ? ORDER BY impact_factor DESC",
                    (f"%{journal_name}%",),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM journal_impact_factors ORDER BY impact_factor DESC"
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


# ─── CLI 测试 ───

if __name__ == "__main__":
    kb = KnowledgeBaseQuery()

    # 统计
    stats = kb.get_stats()
    print("📊 Knowledge Base Stats:")
    for k, v in stats.items():
        print(f"   {k}: {v}")

    # 示例：按疾病查询
    print("\n🔍 Papers by Disease (IBD):")
    papers = kb.search_papers(disease_keyword="IBD", limit=3)
    for p in papers:
        print(f"   - [{p['publication_year']}] {p['title'][:70]}... (IF={p.get('impact_factor', 'N/A')})")