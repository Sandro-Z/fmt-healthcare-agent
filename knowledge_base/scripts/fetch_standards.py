#!/usr/bin/env python3
"""下载国际标准数据：ICD-11、NCBI taxonomy、益生菌名录、期刊影响因子"""

from __future__ import annotations

import csv
import json
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "kb.db"


# ===================== ICD-11 疾病分类 =====================

def fetch_icd11_builtin() -> list[dict]:
    """
    返回常见微生物组相关疾病的 ICD-11 映射（内置）。
    如需完整 ICD-11 数据，后续可调用 WHO API。
    """
    diseases = [
        # 消化系统肿瘤
        {"code": "2B91.0", "name_en": "Malignant neoplasm of colon", "name_cn": "结肠恶性肿瘤（结肠癌）", "parent_code": "2B91", "chapter": "02", "category": "肿瘤"},
        {"code": "2B91.1", "name_en": "Malignant neoplasm of rectosigmoid junction", "name_cn": "乙状结肠直肠恶性肿瘤", "parent_code": "2B91", "chapter": "02", "category": "肿瘤"},
        {"code": "2B92", "name_en": "Malignant neoplasm of stomach", "name_cn": "胃恶性肿瘤（胃癌）", "parent_code": "2B92", "chapter": "02", "category": "肿瘤"},
        # 代谢性疾病
        {"code": "5A11", "name_en": "Type 2 diabetes mellitus", "name_cn": "2型糖尿病", "parent_code": "5A1", "chapter": "05", "category": "内分泌/代谢"},
        {"code": "5B81", "name_en": "Obesity", "name_cn": "肥胖症", "parent_code": "5B81", "chapter": "05", "category": "内分泌/代谢"},
        # 炎症性肠病
        {"code": "DD70", "name_en": "Crohn disease", "name_cn": "克罗恩病", "parent_code": "DD70", "chapter": "13", "category": "消化系统"},
        {"code": "DD71", "name_en": "Ulcerative colitis", "name_cn": "溃疡性结肠炎", "parent_code": "DD71", "chapter": "13", "category": "消化系统"},
        # 感染
        {"code": "1A01", "name_en": "Clostridioides difficile enterocolitis", "name_cn": "艰难梭菌肠炎", "parent_code": "1A0", "chapter": "01", "category": "感染"},
        # 神经精神
        {"code": "6A20", "name_en": "Schizophrenia", "name_cn": "精神分裂症", "parent_code": "6A20", "chapter": "06", "category": "精神/神经"},
        {"code": "6A70", "name_en": "Depressive disorders", "name_cn": "抑郁症", "parent_code": "6A70", "chapter": "06", "category": "精神/神经"},
        {"code": "6A80", "name_en": "Attention deficit hyperactivity disorder", "name_cn": "ADHD（注意缺陷多动障碍）", "parent_code": "6A80", "chapter": "06", "category": "精神/神经"},
        # 心血管
        {"code": "BA00", "name_en": "Essential hypertension", "name_cn": "原发性高血压", "parent_code": "BA00", "chapter": "11", "category": "心血管"},
        {"code": "BA40", "name_en": "Atherosclerosis", "name_cn": "动脉粥样硬化", "parent_code": "BA40", "chapter": "11", "category": "心血管"},
        # 肝病
        {"code": "DB99.1", "name_en": "Non-alcoholic fatty liver disease", "name_cn": "非酒精性脂肪性肝病", "parent_code": "DB99", "chapter": "13", "category": "消化系统"},
        {"code": "DB96", "name_en": "Cirrhosis of liver", "name_cn": "肝硬化", "parent_code": "DB96", "chapter": "13", "category": "消化系统"},
    ]
    return diseases


# ===================== NCBI 物种分类（含中文名） =====================

def fetch_ncbi_taxonomy_builtin() -> list[dict]:
    """
    返回常见肠道微生物物种的 NCBI Taxonomy 映射（内置）。
    后续可以从 taxdump.tar.gz 动态加载完整 taxonomy。
    """
    microbes = [
        # 厚壁菌门
        {"taxid": 853, "scientific_name": "Faecalibacterium prausnitzii", "chinese_name": "普拉梭菌", "rank": "species", "parent_taxid": 929, "lineage": "Bacteria;Firmicutes;Clostridia;Clostridiales;Ruminococcaceae;Faecalibacterium"},
        {"taxid": 820, "scientific_name": "Roseburia intestinalis", "chinese_name": "肠道罗斯氏菌", "rank": "species", "parent_taxid": 841, "lineage": "Bacteria;Firmicutes;Clostridia;Clostridiales;Lachnospiraceae;Roseburia"},
        {"taxid": 823, "scientific_name": "Eubacterium rectale", "chinese_name": "直肠真杆菌", "rank": "species", "parent_taxid": 1730, "lineage": "Bacteria;Firmicutes;Clostridia;Clostridiales;Lachnospiraceae"},
        # 拟杆菌门
        {"taxid": 821, "scientific_name": "Bacteroides vulgatus", "chinese_name": "普通拟杆菌", "rank": "species", "parent_taxid": 816, "lineage": "Bacteria;Bacteroidetes;Bacteroidia;Bacteroidales;Bacteroidaceae;Bacteroides"},
        {"taxid": 817, "scientific_name": "Bacteroides fragilis", "chinese_name": "脆弱拟杆菌", "rank": "species", "parent_taxid": 816, "lineage": "Bacteria;Bacteroidetes;Bacteroidia;Bacteroidales;Bacteroidaceae;Bacteroides"},
        {"taxid": 818, "scientific_name": "Bacteroides thetaiotaomicron", "chinese_name": "多形拟杆菌", "rank": "species", "parent_taxid": 816, "lineage": "Bacteria;Bacteroidetes;Bacteroidia;Bacteroidales;Bacteroidaceae;Bacteroides"},
        # 疣微菌门
        {"taxid": 349935, "scientific_name": "Akkermansia muciniphila", "chinese_name": "嗜粘蛋白阿克曼氏菌", "rank": "species", "parent_taxid": 512293, "lineage": "Bacteria;Verrucomicrobia;Verrucomicrobiae;Verrucomicrobiales;Akkermansiaceae;Akkermansia"},
        # 放线菌门
        {"taxid": 1682, "scientific_name": "Bifidobacterium longum", "chinese_name": "长双歧杆菌", "rank": "species", "parent_taxid": 1678, "lineage": "Bacteria;Actinobacteria;Bifidobacteriales;Bifidobacteriaceae;Bifidobacterium"},
        {"taxid": 1681, "scientific_name": "Bifidobacterium adolescentis", "chinese_name": "青春双歧杆菌", "rank": "species", "parent_taxid": 1678, "lineage": "Bacteria;Actinobacteria;Bifidobacteriales;Bifidobacteriaceae;Bifidobacterium"},
        {"taxid": 1685, "scientific_name": "Bifidobacterium breve", "chinese_name": "短双歧杆菌", "rank": "species", "parent_taxid": 1678, "lineage": "Bacteria;Actinobacteria;Bifidobacteriales;Bifidobacteriaceae;Bifidobacterium"},
        # 变形菌门
        {"taxid": 562, "scientific_name": "Escherichia coli", "chinese_name": "大肠杆菌", "rank": "species", "parent_taxid": 543, "lineage": "Bacteria;Proteobacteria;Gammaproteobacteria;Enterobacterales;Enterobacteriaceae;Escherichia"},
        # 梭杆菌门
        {"taxid": 851, "scientific_name": "Fusobacterium nucleatum", "chinese_name": "具核梭杆菌", "rank": "species", "parent_taxid": 848, "lineage": "Bacteria;Fusobacteria;Fusobacteriia;Fusobacteriales;Fusobacteriaceae;Fusobacterium"},
        # 乳酸菌
        {"taxid": 1579, "scientific_name": "Lactobacillus acidophilus", "chinese_name": "嗜酸乳杆菌", "rank": "species", "parent_taxid": 1578, "lineage": "Bacteria;Firmicutes;Bacilli;Lactobacillales;Lactobacillaceae;Lactobacillus"},
        {"taxid": 1582, "scientific_name": "Lactobacillus rhamnosus", "chinese_name": "鼠李糖乳杆菌", "rank": "species", "parent_taxid": 1578, "lineage": "Bacteria;Firmicutes;Bacilli;Lactobacillales;Lactobacillaceae;Lactobacillus"},
        {"taxid": 1580, "scientific_name": "Lactobacillus plantarum", "chinese_name": "植物乳杆菌", "rank": "species", "parent_taxid": 1578, "lineage": "Bacteria;Firmicutes;Bacilli;Lactobacillales;Lactobacillaceae;Lactobacillus"},
        {"taxid": 1613, "scientific_name": "Lactococcus lactis", "chinese_name": "乳酸乳球菌", "rank": "species", "parent_taxid": 1357, "lineage": "Bacteria;Firmicutes;Bacilli;Lactobacillales;Streptococcaceae;Lactococcus"},
        # 其他
        {"taxid": 1313, "scientific_name": "Streptococcus thermophilus", "chinese_name": "嗜热链球菌", "rank": "species", "parent_taxid": 1301, "lineage": "Bacteria;Firmicutes;Bacilli;Lactobacillales;Streptococcaceae;Streptococcus"},
        {"taxid": 1654, "scientific_name": "Blautia obeum", "chinese_name": "卵形布劳特氏菌", "rank": "species", "parent_taxid": 89014, "lineage": "Bacteria;Firmicutes;Clostridia;Clostridiales;Lachnospiraceae;Blautia"},
        {"taxid": 219814, "scientific_name": "Ruminococcus bromii", "chinese_name": "布氏瘤胃球菌", "rank": "species", "parent_taxid": 1263, "lineage": "Bacteria;Firmicutes;Clostridia;Clostridiales;Ruminococcaceae;Ruminococcus"},
        {"taxid": 74426, "scientific_name": "Coprococcus eutactus", "chinese_name": "粪球菌", "rank": "species", "parent_taxid": 33042, "lineage": "Bacteria;Firmicutes;Clostridia;Clostridiales;Lachnospiraceae;Coprococcus"},
        {"taxid": 55601, "scientific_name": "Prevotella copri", "chinese_name": "科普里普雷沃氏菌", "rank": "species", "parent_taxid": 838, "lineage": "Bacteria;Bacteroidetes;Bacteroidia;Bacteroidales;Prevotellaceae;Prevotella"},
        {"taxid": 797, "scientific_name": "Helicobacter pylori", "chinese_name": "幽门螺杆菌", "rank": "species", "parent_taxid": 209, "lineage": "Bacteria;Proteobacteria;Epsilonproteobacteria;Campylobacterales;Helicobacteraceae;Helicobacter"},
    ]
    return microbes


# ===================== 益生菌名录 =====================

def fetch_probiotics_builtin() -> list[dict]:
    """返回 ISAPP/FAO 认可的益生菌名录（内置）"""
    probiotics = [
        {"taxid": 1579, "species": "Lactobacillus acidophilus", "chinese_name": "嗜酸乳杆菌", "evidence_level": "strong", "health_claims": "改善乳糖不耐受, 维持肠道屏障", "safety_status": "GRAS"},
        {"taxid": 1582, "species": "Lactobacillus rhamnosus", "chinese_name": "鼠李糖乳杆菌", "evidence_level": "strong", "health_claims": "增强免疫, 预防抗生素相关腹泻", "safety_status": "GRAS"},
        {"taxid": 1580, "species": "Lactobacillus plantarum", "chinese_name": "植物乳杆菌", "evidence_level": "strong", "health_claims": "降低胆固醇, 改善IBS症状", "safety_status": "GRAS"},
        {"taxid": 1681, "species": "Bifidobacterium adolescentis", "chinese_name": "青春双歧杆菌", "evidence_level": "strong", "health_claims": "抑制致病菌, 调节免疫", "safety_status": "GRAS"},
        {"taxid": 1682, "species": "Bifidobacterium longum", "chinese_name": "长双歧杆菌", "evidence_level": "strong", "health_claims": "改善便秘, 抗炎作用", "safety_status": "GRAS"},
        {"taxid": 1685, "species": "Bifidobacterium breve", "chinese_name": "短双歧杆菌", "evidence_level": "strong", "health_claims": "减少肠道通透性, 调节菌群", "safety_status": "GRAS"},
        {"taxid": 1613, "species": "Lactococcus lactis", "chinese_name": "乳酸乳球菌", "evidence_level": "moderate", "health_claims": "发酵产物, 食品工业应用", "safety_status": "GRAS"},
        {"taxid": 1313, "species": "Streptococcus thermophilus", "chinese_name": "嗜热链球菌", "evidence_level": "strong", "health_claims": "乳糖发酵, 改善菌群平衡", "safety_status": "GRAS"},
        {"taxid": 349935, "species": "Akkermansia muciniphila", "chinese_name": "嗜粘蛋白阿克曼氏菌", "evidence_level": "emerging", "health_claims": "增强肠屏障, 改善代谢指标, 提高免疫治疗反应", "safety_status": "Novel Food (EU approved)"},
        {"taxid": 853, "species": "Faecalibacterium prausnitzii", "chinese_name": "普拉梭菌", "evidence_level": "emerging", "health_claims": "产生丁酸, 抗炎, IBD 有益", "safety_status": "Next-generation probiotic candidate"},
    ]
    return probiotics


# ===================== 期刊影响因子 =====================

def fetch_journal_if_builtin() -> list[dict]:
    """
    返回常见肠道微生物组期刊的 JCR 影响因子（内置 2024 数据）。
    后续可通过 scimagojr API 或 Clarivate JCR 实时更新。
    """
    journals = [
        {"issn": "0028-0836", "journal_name": "Nature", "if_year": 2024, "impact_factor": 64.8, "quartile": "Q1"},
        {"issn": "0036-8075", "journal_name": "Science", "if_year": 2024, "impact_factor": 56.9, "quartile": "Q1"},
        {"issn": "0092-8674", "journal_name": "Cell", "if_year": 2024, "impact_factor": 64.5, "quartile": "Q1"},
        {"issn": "1087-0156", "journal_name": "Nature Biotechnology", "if_year": 2024, "impact_factor": 46.9, "quartile": "Q1"},
        {"issn": "1078-8956", "journal_name": "Nature Medicine", "if_year": 2024, "impact_factor": 82.9, "quartile": "Q1"},
        {"issn": "0017-5749", "journal_name": "Gut", "if_year": 2024, "impact_factor": 24.5, "quartile": "Q1"},
        {"issn": "0016-5085", "journal_name": "Gastroenterology", "if_year": 2024, "impact_factor": 29.4, "quartile": "Q1"},
        {"issn": "1471-0056", "journal_name": "Nature Reviews Gastroenterology & Hepatology", "if_year": 2024, "impact_factor": 65.1, "quartile": "Q1"},
        {"issn": "0028-4793", "journal_name": "New England Journal of Medicine", "if_year": 2024, "impact_factor": 158.5, "quartile": "Q1"},
        {"issn": "0140-6736", "journal_name": "The Lancet", "if_year": 2024, "impact_factor": 168.9, "quartile": "Q1"},
        {"issn": "0027-8424", "journal_name": "Proceedings of the National Academy of Sciences", "if_year": 2024, "impact_factor": 11.1, "quartile": "Q1"},
        {"issn": "2041-1723", "journal_name": "Nature Communications", "if_year": 2024, "impact_factor": 16.6, "quartile": "Q1"},
        {"issn": "1061-4036", "journal_name": "Nature Genetics", "if_year": 2024, "impact_factor": 30.8, "quartile": "Q1"},
        {"issn": "1745-2473", "journal_name": "Nature Microbiology", "if_year": 2024, "impact_factor": 28.3, "quartile": "Q1"},
        {"issn": "1932-6203", "journal_name": "PLoS ONE", "if_year": 2024, "impact_factor": 3.7, "quartile": "Q2"},
        {"issn": "1664-302X", "journal_name": "Frontiers in Microbiology", "if_year": 2024, "impact_factor": 5.2, "quartile": "Q1-Q2"},
        {"issn": "2076-2607", "journal_name": "Microorganisms", "if_year": 2024, "impact_factor": 4.5, "quartile": "Q2"},
        {"issn": "2296-861X", "journal_name": "Frontiers in Nutrition", "if_year": 2024, "impact_factor": 4.0, "quartile": "Q2"},
        {"issn": "2161-8313", "journal_name": "Advances in Nutrition", "if_year": 2024, "impact_factor": 9.3, "quartile": "Q1"},
        {"issn": "1932-6203", "journal_name": "PLoS ONE", "if_year": 2024, "impact_factor": 3.7, "quartile": "Q2"},
    ]
    return journals


# ===================== 数据库导入 =====================

def import_to_db(conn: sqlite3.Connection):
    """将所有标准数据导入数据库"""

    # ICD-11
    diseases = fetch_icd11_builtin()
    conn.executemany(
        "INSERT OR REPLACE INTO icd11_diseases (code, name_en, name_cn, parent_code, chapter, category) "
        "VALUES (:code, :name_en, :name_cn, :parent_code, :chapter, :category)",
        diseases,
    )
    print(f"   ✅ icd11_diseases: {len(diseases)} rows")

    # NCBI taxonomy
    microbes = fetch_ncbi_taxonomy_builtin()
    conn.executemany(
        "INSERT OR REPLACE INTO ncbi_taxonomy (taxid, scientific_name, chinese_name, rank, parent_taxid, lineage) "
        "VALUES (:taxid, :scientific_name, :chinese_name, :rank, :parent_taxid, :lineage)",
        microbes,
    )
    print(f"   ✅ ncbi_taxonomy: {len(microbes)} rows")

    # Probiotics
    probiotics = fetch_probiotics_builtin()
    conn.executemany(
        "INSERT OR REPLACE INTO probiotics (taxid, species, chinese_name, evidence_level, health_claims, safety_status) "
        "VALUES (:taxid, :species, :chinese_name, :evidence_level, :health_claims, :safety_status)",
        probiotics,
    )
    print(f"   ✅ probiotics: {len(probiotics)} rows")

    # Journals IF
    journals = fetch_journal_if_builtin()
    conn.executemany(
        "INSERT OR REPLACE INTO journal_impact_factors (issn, journal_name, if_year, impact_factor, quartile) "
        "VALUES (:issn, :journal_name, :if_year, :impact_factor, :quartile)",
        journals,
    )
    print(f"   ✅ journal_impact_factors: {len(journals)} rows")

    conn.commit()


def main():
    print(f"📥 Downloading standard reference data...")
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = ON")
    import_to_db(conn)
    conn.close()
    print(f"✅ All standard data imported to: {DB_PATH}")


if __name__ == "__main__":
    main()