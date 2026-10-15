#!/usr/bin/env python3
"""
PubMed 自动抓取管道

功能：
1. 通过 PMID 从 PubMed API 抓取完整元数据
2. 自动提取：DOI、期刊、测序策略、样本量、疾病、微生物、通路、代谢物等
3. 缺失字段标注为 N/A
4. 支持批量处理
"""

from __future__ import annotations

import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "kb.db"

# PubMed API 配置
PUBMED_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
PUBMED_EFETCH = f"{PUBMED_BASE}/efetch.fcgi?db=pubmed&rettype=abstract&retmode=xml"
PUBMED_ESEARCH = f"{PUBMED_BASE}/esearch.fcgi?db=pubmed&retmode=xml"
EMAIL = "wgsfmt@example.com"  # 后续可从环境变量获取

# ─── 正则表达式 ───

RE_DOI = re.compile(r'10\.\d{4,}/[-._;()/:a-zA-Z0-9]+')
# 数据集编号
RE_ACCESSION = re.compile(r'\b(?:PRJNA\d+|GSE\d+|MGYS\d+|SRP\d+|ERP\d+|DRP\d+|CRA\d+)\b')
RE_ARRAY_EXPRESS = re.compile(r'\bE-MTAB-\d+\b')
# 样本量提取
RE_CASE_CTRL = re.compile(r'(?:n\s*[=:]\s*)?(\d+)\s*(?:cases?|patients?|subjects?|CRC|T2D|IBD|AD|PD)(?:.*?)(?:and|vs?\.?)\s*(?:n\s*[=:]\s*)?(\d+)\s*(?:controls?|healthy)', re.IGNORECASE)
RE_COHORT = re.compile(r'(?:included|recruited|enrolled|cohort of)\s+(\d+)\s+(?:patients?|subjects?|individuals?|participants?)', re.IGNORECASE)
# 测序策略
RE_SEQ_STRATEGY = re.compile(r'(16S\s*(?:rRNA\s*)?(?:gene\s*)?(?:amplicon\s*)?(?:V\d[-–]V\d\s*)?(?:sequencing|profiling)?)', re.IGNORECASE)
RE_SHOTGUN = re.compile(r'(?:whole[\s_-]?genome|shotgun|WGS|metagenomic[s]?)\s+(?:sequencing|shotgun)', re.IGNORECASE)
RE_SEQ_PLATFORM = re.compile(r'(Illumina\s*(?:HiSeq|MiSeq|NextSeq|NovaSeq)\s*\d*)', re.IGNORECASE)
RE_PACBIO = re.compile(r'(PacBio|Pacific\s*Biosciences|Sequel|Revio)', re.IGNORECASE)
RE_NANOPORE = re.compile(r'(ONT|Oxford\s*Nanopore|MinION|GridION|PromethION)', re.IGNORECASE)
# 样本来源
RE_FECES = re.compile(r'(feces|faeces|fecal|faecal|stool)', re.IGNORECASE)
RE_MUCOSA = re.compile(r'(mucosa[l]?|mucosal\s*biopsy|intestinal\s*biopsy)', re.IGNORECASE)
RE_SALIVA = re.compile(r'(saliva)', re.IGNORECASE)
# 地理位置
RE_LOCATION = re.compile(r'(?:from|in|at)\s+(Japan|China|Korea|India|Thailand|Vietnam|USA|United States|UK|United Kingdom|Germany|France|Italy|Spain|Denmark|Sweden|Norway|Finland|Netherlands|Belgium|Switzerland|Austria|Canada|Australia|Brazil|Mexico|Argentina)', re.IGNORECASE)
RE_POPULATION = re.compile(r'(Asian[s]?|Caucasian[s]?|African American[s]?|Hispanic[s]?|European[s]?|Japanese|Chinese|Korean|Indian)', re.IGNORECASE)

# 代谢通路关键词
PATHWAY_KEYWORDS = [
    "BUTYRATE", "PROPIONATE", "ACETATE", "SUCCINATE", "LACTATE",
    "TRYPTOPHAN", "ARGININE", "FOLATE", "BIOTIN", "COBALAMIN",
    "Bile acid", "LPS biosynthesis", "Flagellar assembly",
    "TCA cycle", "Glycolysis", "Methane metabolism",
    "Hydrogen sulfide", "Sulfur metabolism", "Nitrogen metabolism",
]

# 代谢物关键词
METABOLITE_KEYWORDS = [
    "butyrate", "propionate", "acetate", "succinate", "lactate",
    "indole", "serotonin", "GABA", "TMAO", "deoxycholate",
    "cholate", "chenodeoxycholate", "ursodeoxycholate",
    "trimethylamine", "choline", "carnitine",
    "p-cresol", "indoxyl sulfate", "hippurate",
]


# ─── PubMed API 抓取 ───

def _fetch_pubmed_xml(pmids: list[str]) -> str:
    """通过 eFetch API 获取 PubMed XML"""
    from urllib.request import urlopen, Request

    ids = ",".join(pmids)
    url = f"{PUBMED_EFETCH}&id={ids}"
    req = Request(url)
    req.add_header("User-Agent", f"WGS.FMT-KB/1.0 (mailto:{EMAIL})")
    with urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")

def _parse_pubmed_xml(xml_str: str) -> list[dict[str, Any]]:
    """解析 PubMed eFetch XML 为结构化数据"""
    root = ElementTree.fromstring(xml_str)
    papers = []
    for article in root.findall(".//PubmedArticle"):
        paper: dict[str, Any] = {}

        # PMID
        pmid_el = article.find(".//PMID")
        paper["pmid"] = pmid_el.text if pmid_el is not None else "N/A"

        # 文章信息
        art = article.find(".//Article")
        if art is None:
            continue

        # Title
        title_el = art.find("ArticleTitle")
        paper["title"] = "".join(title_el.itertext()) if title_el is not None else "N/A"

        # Abstract
        abs_el = art.find("Abstract")
        abstract_parts = []
        if abs_el is not None:
            for at in abs_el.findall("AbstractText"):
                label = at.get("Label", "")
                text = "".join(at.itertext())
                if label:
                    abstract_parts.append(f"{label}: {text}")
                else:
                    abstract_parts.append(text)
        abstract = " ".join(abstract_parts) if abstract_parts else "N/A"
        paper["abstract"] = abstract

        # DOI
        doi = "N/A"
        for eid in article.findall(".//ELocationID"):
            if eid.get("EIdType") == "doi" and eid.text:
                doi = eid.text
        if doi == "N/A":
            for aid in article.findall(".//ArticleId"):
                if aid.get("IdType") == "doi" and aid.text:
                    doi = aid.text
            if doi == "N/A":
                # 尝试从摘要中提取 DOI
                doi_match = RE_DOI.search(abstract)
                if doi_match:
                    doi = doi_match.group(0)
        paper["doi"] = doi

        # 期刊信息
        journal_el = art.find("Journal")
        paper["journal_name"] = "N/A"
        paper["issn"] = "N/A"
        if journal_el is not None:
            title = journal_el.find("Title")
            if title is not None:
                paper["journal_name"] = title.text or "N/A"
            issn = journal_el.find("ISSN")
            if issn is not None:
                paper["issn"] = issn.text or "N/A"

        # 发表年份
        year = "N/A"
        pub_date = art.find(".//PubDate")
        if pub_date is not None:
            year_el = pub_date.find("Year")
            if year_el is not None and year_el.text:
                year = year_el.text
        paper["publication_year"] = int(year) if year.isdigit() else 2020

        # PMC ID
        pmc_id = "N/A"
        for aid in article.findall(".//ArticleId"):
            if aid.get("IdType") == "pmc" and aid.text:
                pmc_id = aid.text
        paper["pmc_id"] = pmc_id

        papers.append(paper)

    return papers


# ─── 文本挖掘（从摘要中提取结构化字段） ───

def _extract_sequencing_info(abstract: str) -> tuple[str, str]:
    """提取测序策略和平台"""
    strategy = "N/A"
    platform = "N/A"

    # 策略
    if RE_SHOTGUN.search(abstract):
        strategy = "Shotgun Metagenomics"
    elif RE_SEQ_STRATEGY.search(abstract):
        m = RE_SEQ_STRATEGY.search(abstract)
        strategy = m.group(1)

    # 平台
    plat_matches = RE_SEQ_PLATFORM.findall(abstract)
    if plat_matches:
        platform = plat_matches[0]
    elif RE_PACBIO.search(abstract):
        platform = "PacBio"
    elif RE_NANOPORE.search(abstract):
        platform = "Nanopore"

    return strategy, platform


def _extract_sample_source(abstract: str) -> str:
    """提取样本来源"""
    if RE_FECES.search(abstract):
        return "Feces"
    if RE_MUCOSA.search(abstract):
        return "Gut Mucosa"
    if RE_SALIVA.search(abstract):
        return "Saliva"
    return "N/A"


def _extract_cohort(abstract: str) -> tuple[int | None, int | None, int | None]:
    """提取样本量"""
    case, ctrl, total = None, None, None

    # 病例-对照
    m = RE_CASE_CTRL.search(abstract)
    if m:
        case = int(m.group(1))
        ctrl = int(m.group(2))
        total = case + ctrl
    else:
        m = RE_COHORT.search(abstract)
        if m:
            total = int(m.group(1))

    return case, ctrl, total


def _extract_location(abstract: str) -> tuple[str, str]:
    """提取地理位置和人群信息"""
    loc = "N/A"
    pop = "N/A"
    loc_match = RE_LOCATION.search(abstract)
    if loc_match:
        loc = loc_match.group(1)
    pop_match = RE_POPULATION.search(abstract)
    if pop_match:
        pop = pop_match.group(1)
    return loc, pop


def _extract_pathways(abstract: str) -> list[str]:
    """从摘要提取代谢通路关键词"""
    found = []
    for kw in PATHWAY_KEYWORDS:
        if kw.lower() in abstract.lower():
            found.append(kw)
    return found


def _extract_metabolites(abstract: str) -> list[str]:
    """从摘要提取代谢物关键词"""
    found = []
    for kw in METABOLITE_KEYWORDS:
        if kw.lower() in abstract.lower():
            found.append(kw)
    return found


def _extract_accessions(abstract: str) -> list[str]:
    """提取数据集编号"""
    found = set(RE_ACCESSION.findall(abstract))
    found.update(RE_ARRAY_EXPRESS.findall(abstract))
    return list(found)


# ─── 疾病映射 ───

def _map_disease_to_icd11(title: str, abstract: str, conn: sqlite3.Connection) -> tuple[str | None, str | None]:
    """
    通过关键词匹配和数据库查询，将文献映射到 ICD-11 疾病分类
    """
    text = (title + " " + abstract).lower()

    # 常见关键词 → ICD-11 编码映射
    keyword_map = {
        "colorectal cancer": "2B91.0",
        "colon cancer": "2B91.0",
        "gastric cancer": "2B92",
        "stomach cancer": "2B92",
        "type 2 diabetes": "5A11",
        "t2d": "5A11",
        "t2dm": "5A11",
        "obesity": "5B81",
        "obese": "5B81",
        "crohn": "DD70",
        "ulcerative colitis": "DD71",
        "inflammatory bowel disease": "DD71",
        "c. difficile": "1A01",
        "clostridioides difficile": "1A01",
        "schizophrenia": "6A20",
        "depression": "6A70",
        "depressive": "6A70",
        "adhd": "6A80",
        "hypertension": "BA00",
        "atherosclerosis": "BA40",
        "nafld": "DB99.1",
        "fatty liver": "DB99.1",
        "cirrhosis": "DB96",
        "liver cirrhosis": "DB96",
    }

    best_code = None
    best_name = None

    for kw, code in keyword_map.items():
        if kw in text:
            best_code = code
            # 从数据库获取中文名
            row = conn.execute(
                "SELECT name_cn FROM icd11_diseases WHERE code = ?", (code,)
            ).fetchone()
            best_name = row[0] if row else kw.title()
            break

    return best_code, best_name


# ─── 主处理函数 ───

def process_pmid(pmid: str, conn: sqlite3.Connection) -> dict[str, Any]:
    """
    处理单个 PMID：PubMed 抓取 → 数据提取 → 数据库写入
    返回处理后的 paper dict
    """
    # 1. 抓取 PubMed 数据
    xml_str = _fetch_pubmed_xml([pmid])
    papers = _parse_pubmed_xml(xml_str)

    if not papers:
        raise ValueError(f"No data found for PMID {pmid}")

    raw = papers[0]
    abstract = raw.get("abstract", "N/A")
    title = raw.get("title", "N/A")

    # 2. 提取字段
    strategy, platform = _extract_sequencing_info(abstract)
    sample_source = _extract_sample_source(abstract)
    case, ctrl, total = _extract_cohort(abstract)
    loc, pop = _extract_location(abstract)
    disease_code, disease_name = _map_disease_to_icd11(title, abstract, conn)

    # 3. 获取期刊 IF
    issn = raw.get("issn", "N/A")
    if_row = conn.execute(
        "SELECT impact_factor FROM journal_impact_factors WHERE issn = ? ORDER BY if_year DESC LIMIT 1",
        (issn,),
    ).fetchone()
    impact_factor = if_row[0] if if_row else None

    # 4. 组装 paper 数据
    paper = {
        "pmid": raw["pmid"],
        "doi": raw["doi"],
        "title": title,
        "abstract": abstract,
        "journal_name": raw["journal_name"],
        "issn": issn,
        "impact_factor": impact_factor,
        "if_year": 2024,
        "publication_year": raw["publication_year"],
        "sequencing_strategy": strategy,
        "sequencing_platform": platform,
        "sample_source": sample_source,
        "geographic_location": loc,
        "population_info": pop,
        "target_disease_code": disease_code,
        "target_disease_name": disease_name,
        "cohort_case": case,
        "cohort_control": ctrl,
        "cohort_total": total,
        "pmc_id": raw["pmc_id"] if raw["pmc_id"] != "N/A" else None,
        "full_text_available": 1 if (raw["pmc_id"] and raw["pmc_id"] != "N/A") else 0,
    }

    # 5. 写入数据库
    _insert_paper(conn, paper)

    # 6. 写入关联表
    paper_id = conn.execute("SELECT id FROM papers WHERE pmid = ?", (paper["pmid"],)).fetchone()[0]

    # 数据集编号
    accessions = _extract_accessions(abstract)
    for acc in accessions:
        acc_type = "SRA" if acc.startswith("SRP") or acc.startswith("PRJNA") else \
                   "GEO" if acc.startswith("GSE") else \
                   "MGnify" if acc.startswith("MGYS") else "N/A"
        conn.execute(
            "INSERT OR IGNORE INTO accessions (paper_id, accession_id, accession_type) VALUES (?, ?, ?)",
            (paper_id, acc, acc_type),
        )

    # 代谢通路
    pathways = _extract_pathways(abstract)
    for p in pathways:
        conn.execute(
            "INSERT OR IGNORE INTO functional_pathways (paper_id, pathway_name) VALUES (?, ?)",
            (paper_id, p),
        )

    # 代谢物
    metabolites = _extract_metabolites(abstract)
    for m in metabolites:
        conn.execute(
            "INSERT OR IGNORE INTO metabolites (paper_id, metabolite_name) VALUES (?, ?)",
            (paper_id, m),
        )

    conn.commit()
    return paper


def _insert_paper(conn: sqlite3.Connection, paper: dict[str, Any]):
    """插入或更新 paper 主表记录"""
    conn.execute(
        """
        INSERT OR REPLACE INTO papers (
            pmid, doi, title, abstract,
            journal_name, issn, impact_factor, if_year, publication_year,
            sequencing_strategy, sequencing_platform,
            sample_source, geographic_location, population_info,
            target_disease_code, target_disease_name,
            cohort_case, cohort_control, cohort_total,
            pmc_id, full_text_available, last_updated
        ) VALUES (
            :pmid, :doi, :title, :abstract,
            :journal_name, :issn, :impact_factor, :if_year, :publication_year,
            :sequencing_strategy, :sequencing_platform,
            :sample_source, :geographic_location, :population_info,
            :target_disease_code, :target_disease_name,
            :cohort_case, :cohort_control, :cohort_total,
            :pmc_id, :full_text_available, CURRENT_TIMESTAMP
        )
        """,
        paper,
    )


def batch_process(pmids: list[str], db_path: Path = DB_PATH) -> dict[str, dict]:
    """批量处理多个 PMID，返回 {pmid: paper} 映射"""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")

    results = {}
    for pmid in pmids:
        try:
            paper = process_pmid(pmid, conn)
            results[pmid] = paper
            print(f"  ✅ PMID {pmid}: {paper['title'][:80]}...")
        except Exception as e:
            print(f"  ❌ PMID {pmid}: {e}")
        time.sleep(0.35)  # PubMed API 限速：3 req/s (无 API key)

    conn.close()
    return results


# ─── CLI ───

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python pubmed_pipeline.py <PMID> [PMID ...]")
        print("  e.g.: python pubmed_pipeline.py 40659786 36058786")
        sys.exit(1)

    pmids = sys.argv[1:]
    print(f"📥 Processing {len(pmids)} PMID(s)...")
    results = batch_process(pmids)
    print(f"✅ Done: {len(results)} papers imported.")