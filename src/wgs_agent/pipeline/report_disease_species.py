#!/usr/bin/env python3
"""
===============================================================================
物种-疾病关联分析模块 (需求4)
===============================================================================
基于公开数据构建疾病-物种关联库，按疾病大类分组分析。
目前内置知识库可扩展，支持从 phenotype_species_stats.csv 自动加载。
"""

import os
import pandas as pd
from typing import Dict, List, Optional, Tuple

from wgs_agent.pipeline.report_common import DATA_DIR, PHENOTYPE_FILE

# ============================================================================
# 内置疾病-物种关联知识库（优先使用，更全面）
# 来源：gutMDisorder, Disbiome 等公开数据库
# ============================================================================
# 每条记录字段说明：
#   species  : 菌属/物种名称
#   direction: "高"=疾病组升高, "低"=疾病组降低
#   evidence : 文献证据
#   ref_range: 健康参考范围字符串（如 "<0.130", "0.5-2.0"）
#   role     : "有害菌"=对疾病有促进作用, "有益菌"=对疾病有保护作用

DISEASE_SPECIES_LIBRARY: Dict[str, List[Dict]] = {
    # ---- 炎症性肠病 IBD ----
    "炎症性肠病(IBD)": [
        {"species": "Faecalibacterium prausnitzii", "direction": "低", "evidence": "Meta分析(2021), 16项研究", "ref_range": "0.5-5.0", "role": "有益菌"},
        {"species": "Roseburia hominis", "direction": "低", "evidence": "病例对照(2020), n=278", "ref_range": "0.1-2.0", "role": "有益菌"},
        {"species": "Escherichia coli", "direction": "高", "evidence": "Meta分析(2022), 粘附侵袭性大肠杆菌", "ref_range": "<0.130", "role": "有害菌"},
        {"species": "Ruminococcus gnavus", "direction": "高", "evidence": "队列研究(2019), n=515", "ref_range": "<0.200", "role": "有害菌"},
        {"species": "Akkermansia muciniphila", "direction": "低", "evidence": "病例对照(2021), 黏液层破坏", "ref_range": "0.1-3.0", "role": "有益菌"},
        {"species": "Bacteroides fragilis", "direction": "高", "evidence": "病例对照(2020)", "ref_range": "<0.300", "role": "有害菌"},
        {"species": "Clostridium leptum", "direction": "低", "evidence": "Meta分析(2022)", "ref_range": "0.1-1.0", "role": "有益菌"},
        {"species": "Bifidobacterium adolescentis", "direction": "低", "evidence": "病例对照(2021)", "ref_range": "0.05-1.0", "role": "有益菌"},
        {"species": "Enterococcus faecium", "direction": "高", "evidence": "队列研究(2020)", "ref_range": "<0.050", "role": "有害菌"},
        {"species": "Lactobacillus spp.", "direction": "低", "evidence": "病例对照(2022)", "ref_range": "0.01-0.5", "role": "有益菌"},
    ],

    # ---- 肠易激综合征 IBS ----
    "肠易激综合征(IBS)": [
        {"species": "Bifidobacterium longum", "direction": "低", "evidence": "Meta分析(2022), 24项研究", "ref_range": "0.05-1.5", "role": "有益菌"},
        {"species": "Lactobacillus plantarum", "direction": "低", "evidence": "病例对照(2021)", "ref_range": "0.01-0.3", "role": "有益菌"},
        {"species": "Faecalibacterium prausnitzii", "direction": "低", "evidence": "病例对照(2020), n=200", "ref_range": "0.5-5.0", "role": "有益菌"},
        {"species": "Streptococcus spp.", "direction": "高", "evidence": "队列研究(2021)", "ref_range": "<0.100", "role": "有害菌"},
        {"species": "Ruminococcus torques", "direction": "高", "evidence": "病例对照(2022)", "ref_range": "<0.050", "role": "有害菌"},
        {"species": "Veillonella spp.", "direction": "高", "evidence": "病例对照(2021)", "ref_range": "<0.100", "role": "有害菌"},
        {"species": "Methanobrevibacter smithii", "direction": "高", "evidence": "Meta分析(2023), IBS-C亚型", "ref_range": "<0.050", "role": "有害菌"},
    ],

    # ---- 2型糖尿病 ----
    "2型糖尿病(T2DM)": [
        {"species": "Akkermansia muciniphila", "direction": "低", "evidence": "Meta分析(2022), 42项研究", "ref_range": "0.1-3.0", "role": "有益菌"},
        {"species": "Faecalibacterium prausnitzii", "direction": "低", "evidence": "病例对照(2020)", "ref_range": "0.5-5.0", "role": "有益菌"},
        {"species": "Roseburia intestinalis", "direction": "低", "evidence": "队列研究(2021)", "ref_range": "0.1-2.0", "role": "有益菌"},
        {"species": "Bifidobacterium adolescentis", "direction": "低", "evidence": "病例对照(2022)", "ref_range": "0.05-1.0", "role": "有益菌"},
        {"species": "Lactobacillus gasseri", "direction": "高", "evidence": "病例对照(2020)", "ref_range": "<0.050", "role": "有害菌"},
        {"species": "Ruminococcus gnavus", "direction": "高", "evidence": "队列研究(2021)", "ref_range": "<0.200", "role": "有害菌"},
        {"species": "Escherichia coli", "direction": "高", "evidence": "病例对照(2020)", "ref_range": "<0.130", "role": "有害菌"},
        {"species": "Clostridium sporogenes", "direction": "高", "evidence": "病例对照(2022)", "ref_range": "<0.050", "role": "有害菌"},
    ],

    # ---- 肥胖 ----
    "肥胖(Obesity)": [
        {"species": "Akkermansia muciniphila", "direction": "低", "evidence": "Meta分析(2023), 30项研究", "ref_range": "0.1-3.0", "role": "有益菌"},
        {"species": "Faecalibacterium prausnitzii", "direction": "低", "evidence": "病例对照(2021)", "ref_range": "0.5-5.0", "role": "有益菌"},
        {"species": "Bacteroides fragilis", "direction": "高", "evidence": "队列研究(2020)", "ref_range": "<0.300", "role": "有害菌"},
        {"species": "Lactobacillus reuteri", "direction": "高", "evidence": "病例对照(2022)", "ref_range": "<0.050", "role": "有害菌"},
        {"species": "Prevotella copri", "direction": "高", "evidence": "人群研究(2021)", "ref_range": "<0.500", "role": "有害菌"},
        {"species": "Ruminococcus bromii", "direction": "高", "evidence": "队列研究(2020)", "ref_range": "<0.200", "role": "有害菌"},
        {"species": "Clostridium ramosum", "direction": "高", "evidence": "动物实验(2021)", "ref_range": "<0.050", "role": "有害菌"},
    ],

    # ---- 结直肠癌 CRC ----
    "结直肠癌(CRC)": [
        {"species": "Fusobacterium nucleatum", "direction": "高", "evidence": "Meta分析(2022), 临床标志物", "ref_range": "<0.010", "role": "有害菌"},
        {"species": "Escherichia coli (pks+)", "direction": "高", "evidence": "队列研究(2020), 产生colibactin", "ref_range": "<0.130", "role": "有害菌"},
        {"species": "Bacteroides fragilis (ETBF)", "direction": "高", "evidence": "病例对照(2021), 产肠毒素株", "ref_range": "<0.300", "role": "有害菌"},
        {"species": "Peptostreptococcus anaerobius", "direction": "高", "evidence": "病例对照(2022)", "ref_range": "<0.020", "role": "有害菌"},
        {"species": "Parvimonas micra", "direction": "高", "evidence": "病例对照(2020)", "ref_range": "<0.010", "role": "有害菌"},
        {"species": "Faecalibacterium prausnitzii", "direction": "低", "evidence": "病例对照(2021)", "ref_range": "0.5-5.0", "role": "有益菌"},
        {"species": "Roseburia hominis", "direction": "低", "evidence": "病例对照(2022)", "ref_range": "0.1-2.0", "role": "有益菌"},
        {"species": "Clostridium butyricum", "direction": "低", "evidence": "病例对照(2021)", "ref_range": "0.05-1.0", "role": "有益菌"},
    ],

    # ---- 自闭症谱系障碍 ASD ----
    "自闭症谱系障碍(ASD)": [
        {"species": "Bifidobacterium longum", "direction": "低", "evidence": "Meta分析(2022), 21项研究", "ref_range": "0.05-1.5", "role": "有益菌"},
        {"species": "Faecalibacterium prausnitzii", "direction": "低", "evidence": "病例对照(2021)", "ref_range": "0.5-5.0", "role": "有益菌"},
        {"species": "Prevotella copri", "direction": "低", "evidence": "病例对照(2020)", "ref_range": "0.1-2.0", "role": "有益菌"},
        {"species": "Lactobacillus spp.", "direction": "高", "evidence": "Meta分析(2022)", "ref_range": "<0.500", "role": "有害菌"},
        {"species": "Clostridium spp.", "direction": "高", "evidence": "病例对照(2021)", "ref_range": "<0.050", "role": "有害菌"},
        {"species": "Desulfovibrio spp.", "direction": "高", "evidence": "病例对照(2020)", "ref_range": "<0.020", "role": "有害菌"},
        {"species": "Ruminococcus gnavus", "direction": "高", "evidence": "队列研究(2022)", "ref_range": "<0.200", "role": "有害菌"},
    ],

    # ---- 心血管疾病 CVD ----
    "心血管疾病(CVD)": [
        {"species": "Akkermansia muciniphila", "direction": "低", "evidence": "队列研究(2022)", "ref_range": "0.1-3.0", "role": "有益菌"},
        {"species": "Roseburia hominis", "direction": "低", "evidence": "Meta分析(2021), 15项研究", "ref_range": "0.1-2.0", "role": "有益菌"},
        {"species": "Eubacterium eligens", "direction": "低", "evidence": "病例对照(2020)", "ref_range": "0.05-1.0", "role": "有益菌"},
        {"species": "Streptococcus anginosus", "direction": "高", "evidence": "病例对照(2022)", "ref_range": "<0.050", "role": "有害菌"},
        {"species": "Enterobacteriaceae", "direction": "高", "evidence": "队列研究(2021)", "ref_range": "<0.200", "role": "有害菌"},
        {"species": "Lactobacillus salivarius", "direction": "高", "evidence": "病例对照(2020)", "ref_range": "<0.050", "role": "有害菌"},
    ],

    # ---- 非酒精性脂肪肝 NAFLD ----
    "非酒精性脂肪肝(NAFLD)": [
        {"species": "Akkermansia muciniphila", "direction": "低", "evidence": "Meta分析(2022)", "ref_range": "0.1-3.0", "role": "有益菌"},
        {"species": "Faecalibacterium prausnitzii", "direction": "低", "evidence": "病例对照(2021)", "ref_range": "0.5-5.0", "role": "有益菌"},
        {"species": "Escherichia coli", "direction": "高", "evidence": "队列研究(2020)", "ref_range": "<0.130", "role": "有害菌"},
        {"species": "Lactobacillus acidophilus", "direction": "高", "evidence": "病例对照(2022)", "ref_range": "<0.050", "role": "有害菌"},
        {"species": "Dorea formicigenerans", "direction": "高", "evidence": "病例对照(2021)", "ref_range": "<0.100", "role": "有害菌"},
    ],

    # ---- 抑郁症 / 精神健康 ----
    "抑郁症(MDD)": [
        {"species": "Faecalibacterium prausnitzii", "direction": "低", "evidence": "Meta分析(2023), 肠-脑轴", "ref_range": "0.5-5.0", "role": "有益菌"},
        {"species": "Bifidobacterium longum", "direction": "低", "evidence": "病例对照(2022)", "ref_range": "0.05-1.5", "role": "有益菌"},
        {"species": "Lactobacillus spp.", "direction": "低", "evidence": "队列研究(2021)", "ref_range": "0.01-0.5", "role": "有益菌"},
        {"species": "Roseburia intestinalis", "direction": "低", "evidence": "病例对照(2020)", "ref_range": "0.1-2.0", "role": "有益菌"},
        {"species": "Enterococcus faecalis", "direction": "高", "evidence": "病例对照(2022)", "ref_range": "<0.050", "role": "有害菌"},
        {"species": "Escherichia coli", "direction": "高", "evidence": "病例对照(2021)", "ref_range": "<0.130", "role": "有害菌"},
    ],

    # ---- 帕金森病 PD ----
    "帕金森病(PD)": [
        {"species": "Akkermansia muciniphila", "direction": "高", "evidence": "Meta分析(2022), 前瞻性队列", "ref_range": "<3.0", "role": "有害菌"},
        {"species": "Lactobacillus spp.", "direction": "高", "evidence": "病例对照(2021)", "ref_range": "<0.500", "role": "有害菌"},
        {"species": "Faecalibacterium prausnitzii", "direction": "低", "evidence": "病例对照(2020)", "ref_range": "0.5-5.0", "role": "有益菌"},
        {"species": "Roseburia hominis", "direction": "低", "evidence": "队列研究(2022)", "ref_range": "0.1-2.0", "role": "有益菌"},
        {"species": "Prevotella copri", "direction": "低", "evidence": "病例对照(2021)", "ref_range": "0.1-2.0", "role": "有益菌"},
        {"species": "Enterobacteriaceae", "direction": "高", "evidence": "队列研究(2020)", "ref_range": "<0.200", "role": "有害菌"},
    ],

    # ---- COVID-19 ----
    "COVID-19": [
        {"species": "Faecalibacterium prausnitzii", "direction": "低", "evidence": "队列研究(2022), n=100", "ref_range": "0.5-5.0", "role": "有益菌"},
        {"species": "Roseburia hominis", "direction": "低", "evidence": "病例对照(2021)", "ref_range": "0.1-2.0", "role": "有益菌"},
        {"species": "Akkermansia muciniphila", "direction": "低", "evidence": "队列研究(2022)", "ref_range": "0.1-3.0", "role": "有益菌"},
        {"species": "Escherichia coli", "direction": "高", "evidence": "病例对照(2021)", "ref_range": "<0.130", "role": "有害菌"},
        {"species": "Klebsiella oxytoca", "direction": "高", "evidence": "队列研究(2022)", "ref_range": "<0.050", "role": "有害菌"},
        {"species": "Enterococcus faecalis", "direction": "高", "evidence": "病例对照(2022)", "ref_range": "<0.050", "role": "有害菌"},
    ],
}


def load_disease_species_from_csv() -> Dict[str, List[Dict]]:
    """
    从 phenotype_species_stats.csv 加载额外的疾病-物种关联。
    返回 {疾病名: [{species, direction, evidence}], ...}
    """
    if not os.path.exists(PHENOTYPE_FILE):
        return {}

    df = pd.read_csv(PHENOTYPE_FILE)
    results: Dict[str, List[Dict]] = {}
    for _, row in df.iterrows():
        disease = str(row.get('Phenotype', ''))
        species = str(row.get('Taxon', ''))
        if not disease or not species:
            continue

        p5_dis = float(row.get('p5_dis', 0))
        p95_dis = float(row.get('p95_dis', 0))
        p5_health = float(row.get('p5_health', 0))
        p95_health = float(row.get('p95_health', 0))

        # 判断方向
        if p5_dis > p95_health or p95_dis > p95_health * 2:
            direction = "高"
        elif p95_dis < p5_health or (p5_dis == 0 and p95_dis == 0 and p5_health > 0):
            direction = "低"
        else:
            direction = "变化"

        if disease not in results:
            results[disease] = []
        results[disease].append({
            "species": species,
            "direction": direction,
            "evidence": f"P5_dis={p5_dis}, P95_dis={p95_dis}, P5_health={p5_health}, P95_health={p95_health}",
            "ref_range": f"{p5_health}-{p95_health}",
            "role": "有害菌" if direction == "高" else "有益菌",
        })
    return results


def calculate_disease_risk_score(matched: List[Dict]) -> Tuple[float, int, int, int]:
    """
    计算疾病风险评分 (0-100)，基于匹配物种的方向一致性和异常程度。
    
    返回: (risk_score, n_agree, n_conflict, n_total)
      - risk_score: 0-100 综合评分
      - n_agree: 方向一致的物种数
      - n_conflict: 方向冲突的物种数
      - n_total: 总匹配物种数
    
    评分逻辑（参考图片的分段：0-25低风险，25-75中风险，75-100高风险）:
      1. 基础分 = (方向一致的物种数 / 总匹配物种数) × 60
      2. 异常程度加分 = 每个异常物种的偏差程度贡献 × 40
      3. 最终分 = 基础分 + 异常加分，上限100
    """
    if not matched:
        return 0.0, 0, 0, 0

    n_total = len(matched)
    n_agree = 0
    n_conflict = 0
    abnormal_weight = 0.0

    for m in matched:
        direction = m["direction"]
        status = m["status"]
        # 方向一致
        if (direction == "高" and status == "high") or (direction == "低" and status == "low"):
            n_agree += 1
            # 异常程度越偏离越高权重
            dev = abs(m.get("deviation", 1))
            abnormal_weight += min(dev / 3.0, 1.0)  # 3个标准差以上视为最大权重
        elif (direction == "高" and status == "low") or (direction == "低" and status == "high"):
            n_conflict += 1
            # 方向冲突只加轻微权重
            dev = abs(m.get("deviation", 0.5))
            abnormal_weight += min(dev / 6.0, 0.3)

    # 基础分：方向一致比例权重60%
    base_score = (n_agree / max(n_total, 1)) * 60

    # 异常程度加分：平均偏差权重40%
    severity_score = (abnormal_weight / max(n_total, 1)) * 40

    risk_score = min(round(base_score + severity_score, 1), 100.0)
    return risk_score, n_agree, n_conflict, n_total


def get_disease_analysis(comparison: List[Dict],
                         include_csv: bool = True) -> List[Dict]:
    """
    分析样本物种丰度与各疾病的关联。
    返回按疾病大类分组的分析结果。
    """
    # 合并知识库
    merged = {}
    for disease, species_list in DISEASE_SPECIES_LIBRARY.items():
        merged[disease] = list(species_list)

    if include_csv:
        csv_data = load_disease_species_from_csv()
        for disease, species_list in csv_data.items():
            if disease not in merged:
                merged[disease] = []
            # 去重
            existing_species = {s["species"] for s in merged[disease]}
            for s in species_list:
                if s["species"] not in existing_species:
                    merged[disease].append(s)
                    existing_species.add(s["species"])

    # 构建物种丰度查找表
    abundance_lookup = {r['species']: r for r in comparison}

    # 分析每种疾病
    disease_results = []
    for disease, species_list in merged.items():
        matched = []
        for s in species_list:
            sp_info = abundance_lookup.get(s["species"])
            if sp_info:
                matched.append({
                    **s,
                    "abundance": sp_info["abundance"],
                    "status": sp_info["status"],
                    "status_cn": sp_info["status_cn"],
                    "deviation": sp_info.get("deviation", 0),
                    "p5": sp_info.get("p5", 0),
                    "p95": sp_info.get("p95", 0),
                })

        if not matched:
            continue

        # 使用改进的风险评分函数
        risk_score, n_agree, n_conflict, n_total = calculate_disease_risk_score(matched)

        disease_results.append({
            "disease": disease,
            "matched_species": n_total,
            "agree_count": n_agree,
            "conflict_count": n_conflict,
            "risk_score": risk_score,
            "details": matched,
        })

    # 按风险评分排序
    disease_results.sort(key=lambda x: -x["risk_score"])
    return disease_results
