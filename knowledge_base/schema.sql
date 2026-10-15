-- ============================================================
-- WGS.FMT 知识库 Schema (SQLite)
-- 标准化文献与多组学数据存储
-- ============================================================

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- ===================== 文献主表 =====================
CREATE TABLE IF NOT EXISTS papers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pmid            TEXT UNIQUE NOT NULL,               -- PubMed ID
    doi             TEXT,                               -- DOI（唯一标识）
    title           TEXT NOT NULL,
    abstract        TEXT,                               -- PubMed 摘要

    -- 期刊
    journal_name    TEXT,
    issn            TEXT,                               -- 期刊 ISSN
    impact_factor   REAL,                               -- 最新影响因子 (JCR)
    if_year         INTEGER,                            -- IF 年份
    publication_year INTEGER,                           -- 发表年份

    -- 测序策略
    sequencing_strategy TEXT,                           -- 16S rRNA, Shotgun Metagenomics, Long-read
    sequencing_platform  TEXT,                          -- Illumina NovaSeq, PacBio, Nanopore

    -- 样本信息
    sample_source   TEXT,                               -- Feces, Gut Mucosa, Saliva
    geographic_location TEXT,                           -- 国家/地区
    population_info TEXT,                               -- 人种/人群描述

    -- 研究对象
    target_disease_code TEXT,                           -- ICD-11 编码 (如 2B91.0)
    target_disease_name TEXT,                           -- 疾病中文名（如 结直肠癌）
    cohort_case     INTEGER,                            -- 病例组人数
    cohort_control  INTEGER,                            -- 对照组人数
    cohort_total    INTEGER,                            -- 总人数

    -- 全文
    pmc_id          TEXT,                               -- PubMed Central ID
    full_text_available BOOLEAN DEFAULT 0,
    study_context   TEXT,                               -- 研究摘要精炼 / PMC 全文关键段落

    -- 数据更新
    added_date      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_papers_pmid ON papers(pmid);
CREATE INDEX IF NOT EXISTS idx_papers_year   ON papers(publication_year);
CREATE INDEX IF NOT EXISTS idx_papers_impact ON papers(impact_factor);
CREATE INDEX IF NOT EXISTS idx_papers_disease_code ON papers(target_disease_code);
CREATE INDEX IF NOT EXISTS idx_papers_sample  ON papers(sample_source);

-- ===================== 数据集编号 =====================
CREATE TABLE IF NOT EXISTS accessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id        INTEGER NOT NULL,
    accession_id    TEXT NOT NULL,                      -- PRJNA/GSE/MGYS/SRP
    accession_type  TEXT,                               -- SRA, GEO, MGnify
    direct_link     TEXT,
    FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_accessions_paper ON accessions(paper_id);

-- ===================== 关键微生物 =====================
CREATE TABLE IF NOT EXISTS key_microbes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id        INTEGER NOT NULL,
    taxid           INTEGER,                            -- NCBI Taxonomy ID
    scientific_name TEXT NOT NULL,                      -- 学名 (如 Akkermansia muciniphila)
    chinese_name    TEXT,                                -- 中文名（如 嗜粘蛋白阿克曼氏菌）
    rank_level      TEXT,                                -- species / genus

    role            TEXT,                                -- marker, enhancer, depleted, pathogen
    abundance_change TEXT,                               -- +2.5x, -50%, N/A
    fold_change     REAL,                               -- 数值化的倍数变化
    p_value         REAL,                               -- 显著性
    effect_size     TEXT,                                -- 效应量描述

    FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_microbes_paper ON key_microbes(paper_id);
CREATE INDEX IF NOT EXISTS idx_microbes_taxid ON key_microbes(taxid);
CREATE INDEX IF NOT EXISTS idx_microbes_name  ON key_microbes(scientific_name);

-- ===================== 代谢通路 =====================
CREATE TABLE IF NOT EXISTS functional_pathways (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id        INTEGER NOT NULL,
    pathway_name    TEXT NOT NULL,
    pathway_id      TEXT,                               -- KEGG / MetaCyc 通路 ID
    database_source TEXT,                               -- KEGG, MetaCyc, HUMAnN
    enrichment_score REAL,
    p_value         REAL,
    direction       TEXT DEFAULT 'N/A',                 -- upregulated / downregulated / N/A
    description_cn  TEXT,                               -- 通路中文描述

    FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pathways_paper ON functional_pathways(paper_id);
CREATE INDEX IF NOT EXISTS idx_pathways_name  ON functional_pathways(pathway_name);

-- ===================== 代谢物 =====================
CREATE TABLE IF NOT EXISTS metabolites (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id        INTEGER NOT NULL,
    metabolite_name TEXT NOT NULL,
    hmdb_id         TEXT,                               -- HMDB ID
    kegg_compound   TEXT,                               -- KEGG Compound ID

    direction       TEXT DEFAULT 'N/A',                 -- increased / decreased / unchanged
    fold_change     REAL,
    reference_range TEXT,                               -- 参考范围（如 0.5-5.0 uM）

    FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_metabolites_paper ON metabolites(paper_id);
CREATE INDEX IF NOT EXISTS idx_metabolites_hmdb  ON metabolites(hmdb_id);

-- ===================== 干预措施 =====================
CREATE TABLE IF NOT EXISTS treatments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id        INTEGER NOT NULL,
    treatment_name  TEXT NOT NULL,
    treatment_type  TEXT DEFAULT 'N/A',                 -- drug / diet / FMT / probiotic / surgery
    dosage_info     TEXT,                               -- 剂量信息
    duration        TEXT,                               -- 干预持续时长
    outcomes_summary TEXT,                              -- 主要结局

    FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE
);

-- ===================== 药物-菌群交互 =====================
CREATE TABLE IF NOT EXISTS drug_microbe_interactions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id        INTEGER NOT NULL,
    drug_name       TEXT NOT NULL,
    drug_atc        TEXT,                               -- ATC 分类编码
    microbe_species TEXT NOT NULL,
    interaction_type TEXT,                              -- positive / negative / modulation
    mechanism       TEXT,                               -- 机制简述
    evidence_level  TEXT,                               -- strong / moderate / weak

    FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE
);


-- ===================== 标准参考数据表 =====================

-- ICD-11 疾病分类（WHO）
CREATE TABLE IF NOT EXISTS icd11_diseases (
    code            TEXT PRIMARY KEY,                   -- 2E84.0
    name_en         TEXT,
    name_cn         TEXT,
    parent_code     TEXT,
    chapter         TEXT,                               -- 章节编号
    category        TEXT                                -- 疾病大类
);

CREATE INDEX IF NOT EXISTS idx_icd11_name_en ON icd11_diseases(name_en);
CREATE INDEX IF NOT EXISTS idx_icd11_name_cn ON icd11_diseases(name_cn);

-- NCBI 物种分类（含中文名）
CREATE TABLE IF NOT EXISTS ncbi_taxonomy (
    taxid           INTEGER PRIMARY KEY,
    scientific_name TEXT NOT NULL,
    chinese_name    TEXT,
    rank            TEXT,                                -- species / genus / family
    parent_taxid    INTEGER,
    lineage         TEXT                                 -- 完整分类 lineage
);

CREATE INDEX IF NOT EXISTS idx_ncbi_name  ON ncbi_taxonomy(scientific_name);
CREATE INDEX IF NOT EXISTS idx_ncbi_rank  ON ncbi_taxonomy(rank);

-- 益生菌名录
CREATE TABLE IF NOT EXISTS probiotics (
    taxid           INTEGER PRIMARY KEY,
    species         TEXT NOT NULL,
    chinese_name    TEXT,
    evidence_level  TEXT,                                -- strong / moderate / emerging
    health_claims   TEXT,
    safety_status   TEXT DEFAULT 'Generally Recognized as Safe',
    FOREIGN KEY (taxid) REFERENCES ncbi_taxonomy(taxid)
);

-- 期刊影响因子
CREATE TABLE IF NOT EXISTS journal_impact_factors (
    issn            TEXT,
    journal_name    TEXT NOT NULL,
    if_year         INTEGER NOT NULL,
    impact_factor   REAL,
    quartile        TEXT,                                -- Q1 / Q2 / Q3 / Q4
    PRIMARY KEY (issn, if_year)
);

-- ===================== 元信息表 =====================
CREATE TABLE IF NOT EXISTS schema_version (
    version         TEXT PRIMARY KEY,
    applied_date    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    description     TEXT
);