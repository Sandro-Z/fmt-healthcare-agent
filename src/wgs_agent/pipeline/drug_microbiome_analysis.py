#!/usr/bin/env python3
"""
==============================================================================
肠道微生物-药物关联分析：数据驱动 vs. 推理分析综合测试
==============================================================================

两种分析策略的对比：

方法A: 基于样本数据 (Data-Driven) —— 直接利用 MAS 类数据库
  - 输入: 样本的代谢物含量矩阵
  - 方法: 查询知识库中哪些代谢物与哪些药物有已知关联
  - 输出: 基于代谢物丰度积分的药物暴露/敏感性评分

方法B: 通路推理分析 (Pathway Reasoning)
  - 输入: 样本的通路丰度矩阵
  - 方法: 药物靶向哪些通路 → 通路丰度反映药物敏感性
  - 输出: 基于通路丰度的药物靶向评分

综合方法C: 代谢物+通路融合分析
  - 结合A和B的互补信息

测试用药物列表（30种常见药物）：
  metformin, atorvastatin, omeprazole, metronidazole, ciprofloxacin,
  sulfamethoxazole, methotrexate, irinotecan, acetaminophen, morphine,
  warfarin, simvastatin, levodopa, digoxin, mesalamine

用法:
  python drug_microbiome_analysis.py
==============================================================================
"""

import os
import sys
import json
import logging
import time
from typing import Dict, List, Optional
from collections import defaultdict

import pandas as pd
import numpy as np

# 添加知识库
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from drug_metabolite_knowledge_base import DrugMicrobiomeKB, export_knowledge_base


# ============================================================================
# 配置
# ============================================================================

from wgs_fmt_platform.paths import legacy_output_root

DATA_DIR = str(legacy_output_root())
METABOLITE_FILE = os.path.join(DATA_DIR, "06_metabolite", "metabolite_content_matrix.tsv")
PATHWAY_FILE = os.path.join(DATA_DIR, "04_pathway", "pathway_abundance_known.tsv")
SUMMARY_FILE = os.path.join(DATA_DIR, "06_metabolite", "metabolite_content_matrix_summary.tsv")
OUTPUT_DIR = os.path.join(DATA_DIR, "07_drug_analysis")
KB_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "drug_microbiome_kb.json")
LOG_DIR = os.path.join(DATA_DIR, "log")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)


# ============================================================================
# 日志设置
# ============================================================================

def setup_logging(prefix: str = "drug_analysis"):
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(LOG_DIR, f"{prefix}_{timestamp}.log")

    logger = logging.getLogger("DrugAnalysis")
    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    fh = logging.FileHandler(log_file)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    return logger


# ============================================================================
# 数据加载
# ============================================================================

def load_data(logger: logging.Logger = None):
    """加载代谢物和通路数据"""
    if logger is None:
        logger = setup_logging()

    data = {}

    # 代谢物含量矩阵
    if os.path.exists(METABOLITE_FILE):
        met_df = pd.read_csv(METABOLITE_FILE, sep='\t', index_col=0)
        data['metabolite'] = met_df
        logger.info(f"代谢物矩阵: {met_df.shape[0]} 代谢物 x {met_df.shape[1]} 样本")
    else:
        logger.error(f"代谢物文件不存在: {METABOLITE_FILE}")
        data['metabolite'] = pd.DataFrame()

    # 通路丰度矩阵
    if os.path.exists(PATHWAY_FILE):
        pw_df = pd.read_csv(PATHWAY_FILE, sep='\t', index_col=0)
        data['pathway'] = pw_df
        logger.info(f"通路矩阵: {pw_df.shape[0]} 通路 x {pw_df.shape[1]} 样本")

        # 提取纯净的通路ID
        pw_df_clean = pw_df.copy()
        pw_df_clean.index = [i.split(":")[0].strip() for i in pw_df_clean.index]
        data['pathway_clean'] = pw_df_clean
    else:
        logger.error(f"通路文件不存在: {PATHWAY_FILE}")
        data['pathway'] = pd.DataFrame()

    # 统计摘要
    if os.path.exists(SUMMARY_FILE):
        summary_df = pd.read_csv(SUMMARY_FILE, sep='\t', index_col=0)
        data['summary'] = summary_df
        logger.info(f"统计摘要: {summary_df.shape[0]} 代谢物")
    else:
        data['summary'] = pd.DataFrame()

    return data


# ============================================================================
# 方法A: 数据驱动 (Data-Driven / MASI式分析)
# ============================================================================

def analyze_method_A_data_driven(kb: DrugMicrobiomeKB,
                                  data: Dict,
                                  sample_id: str = None,
                                  logger: logging.Logger = None) -> Dict:
    """
    方法A: 基于代谢物含量数据直接查询药物关联

    原理：
      类似 MASI (Microbiota-Active Substance Interactions) 的思路，
      直接使用已发表的药物-微生物相互作用知识，结合样本的代谢物含量
      谱，通过丰度加权计算药物暴露评分。

    评分公式：
      score(drug) = Σ(met_i * w_i)  for all met_i linked to that drug
      其中 met_i 是代谢物含量，w_i 是该代谢物对药物的关联权重
    """
    if logger is None:
        logger = setup_logging()

    met_df = data.get('metabolite')
    if met_df is None or met_df.empty:
        logger.error("没有代谢物数据")
        return {}

    logger.info("=" * 60)
    logger.info("方法A: 数据驱动分析 (Data-Driven / MASI式)")
    logger.info("  原理: 根据已知文献的代谢物-药物关联，")
    logger.info("        用样本代谢物含量加权打分")
    logger.info("=" * 60)

    # 获取分析结果
    result = kb.summarize_drug_hits(met_df, sample_id)

    logger.info(f"\n  Drug Hits (Top 10):")
    logger.info(f"  {'药物':<30s} {'评分':>10s} {'贡献代谢物数':>12s}")
    logger.info(f"  {'-'*54}")
    for d in result['top_drugs'][:10]:
        n_met = len(d['contributing_metabolites'])
        logger.info(f"  {d['drug']:<30s} {d['score']:>10.2f} {n_met:>12d}")

    logger.info(f"\n  共有 {result['total_metabolites_associated']} 个代谢物与药物关联")

    return result


# ============================================================================
# 方法B: 通路推理分析 (Pathway Reasoning)
# ============================================================================

def analyze_method_B_pathway_reasoning(kb: DrugMicrobiomeKB,
                                       data: Dict,
                                       sample_id: str = None,
                                       logger: logging.Logger = None) -> Dict:
    """
    方法B: 基于通路丰度推理药物作用

    原理：
      药物通过靶向特定代谢通路发挥作用。如果某药物的靶向通路在样本中
      丰度高，说明该菌群对药物敏感，或者正在被药物调控。

    推理步骤：
      1. 药物X靶向通路P（已知知识）
      2. 通路P在样本中丰度为A
      3. 如果A高 → 菌群有较强的通路活性 → 可能受药物X影响
      4. 多条通路加权 = 综合药物作用评分

    评分公式：
      score(drug) = Σ(pw_j)  for all pw_j targeted by that drug
      其中 pw_j 是各应通路丰度
    """
    if logger is None:
        logger = setup_logging()

    pw_df = data.get('pathway_clean', data.get('pathway'))
    if pw_df is None or pw_df.empty:
        logger.error("没有通路数据")
        return {}

    logger.info("=" * 60)
    logger.info("方法B: 通路推理分析 (Pathway Reasoning)")
    logger.info("  原理: 药物靶向特定代谢通路 → 通路丰度反映药物敏感性")
    logger.info("=" * 60)

    result = kb.pathway_to_drug_analysis(pw_df, sample_id)

    logger.info(f"\n  Drug Hits (Top 10):")
    logger.info(f"  {'药物':<30s} {'通路评分':>12s}")
    logger.info(f"  {'-'*42}")
    for d in result['top_drugs_pathway_based'][:10]:
        logger.info(f"  {d['drug']:<30s} {d['pathway_score']:>12.2f}")

    logger.info(f"\n  受影响的通路数: {len(result['pathway_details'])}")

    return result


# ============================================================================
# 方法C: 代谢物+通路融合分析 (综合分析)
# ============================================================================

def analyze_method_C_combined(kb: DrugMicrobiomeKB,
                              data: Dict,
                              sample_id: str = None,
                              logger: logging.Logger = None) -> Dict:
    """
    方法C: 代谢物+通路融合分析 (推荐方法)

    原理：
      代谢物含量反映菌群的"代谢状态"，通路丰度反映菌群的"代谢潜能"。
      两者提供互补信息：
        - 代谢物: 实际执行的代谢功能（接近 MAS 方法）
        - 通路: 潜在可执行的代谢功能

      融合策略：
        score_combined = Σ(met_abundance * w_met) + α * Σ(pw_abundance * w_pw)
        α 为通路权重系数

    优势：
      1. 代谢物数据直接反映药物-代谢物已知关联（文献证据强度高）
      2. 通路数据预测可能的药物敏感性（覆盖度更广）
      3. 两者结合提高信噪比
    """
    if logger is None:
        logger = setup_logging()

    met_df = data.get('metabolite')
    pw_df = data.get('pathway_clean', data.get('pathway'))

    if met_df is None or met_df.empty or pw_df is None or pw_df.empty:
        logger.error("需要代谢物和通路两种数据")
        return {}

    logger.info("=" * 60)
    logger.info("方法C: 代谢物+通路融合分析 (推荐)")
    logger.info("  原理: 代谢物反映实际执行状态 + 通路反映代谢潜能")
    logger.info("        两者加权融合，提高药物关联分析的鲁棒性")
    logger.info("=" * 60)

    result = kb.full_drug_analysis(met_df, pw_df, sample_id)

    logger.info(f"\n  Combined Drug Hits (Top 10):")
    logger.info(f"  {'药物':<30s} {'代谢物评分':>10s} {'通路评分':>10s} {'综合评分':>10s}")
    logger.info(f"  {'-'*60}")
    for d in result['combined_results'][:10]:
        logger.info(f"  {d['drug']:<30s} {d['metabolite_based_score']:>10.2f} "
                     f"{d['pathway_based_score']:>10.2f} {d['combined_score']:>10.2f}")

    logger.info(f"\n  总代谢物: {result['summary']['total_metabolites']}")
    logger.info(f"  总通路: {result['summary']['total_pathways']}")
    logger.info(f"  药物相关代谢物: {result['summary']['drug_related_metabolites']}")
    logger.info(f"  检测到药物关联: {result['summary']['drugs_detected']}")

    return result


# ============================================================================
# 对比分析: A vs B vs C 方法对比
# ============================================================================

def compare_methods(result_a: Dict, result_b: Dict, result_c: Dict,
                    logger: logging.Logger = None) -> pd.DataFrame:
    """
    对比三种分析方法的药物关联结果

    输出：
      每种方法的 Top 药物列表及交集情况
    """
    if logger is None:
        logger = setup_logging()

    logger.info("=" * 60)
    logger.info("方法对比分析")
    logger.info("=" * 60)

    # 提取 Top 药物
    a_drugs = {d['drug']: d.get('score', 0) for d in result_a.get('top_drugs', [])}
    b_drugs = {d['drug']: d.get('pathway_score', 0) for d in result_b.get('top_drugs_pathway_based', [])}
    c_drugs = {d['drug']: d.get('combined_score', 0) for d in result_c.get('combined_results', [])}

    all_drugs = set(list(a_drugs.keys())[:15] +
                    list(b_drugs.keys())[:15] +
                    list(c_drugs.keys())[:15])

    # 标记各方法的检测情况
    comparison = []
    for drug in sorted(all_drugs):
        comparison.append({
            'drug': drug,
            'method_A_rank': list(a_drugs.keys()).index(drug) + 1 if drug in a_drugs else '-',
            'method_A_score': a_drugs.get(drug, 0),
            'method_B_rank': list(b_drugs.keys()).index(drug) + 1 if drug in b_drugs else '-',
            'method_B_score': b_drugs.get(drug, 0),
            'method_C_rank': list(c_drugs.keys()).index(drug) + 1 if drug in c_drugs else '-',
            'method_C_score': c_drugs.get(drug, 0),
            'detected_by': sum([
                drug in a_drugs,
                drug in b_drugs,
                drug in c_drugs
            ]),
        })

    comp_df = pd.DataFrame(comparison)
    comp_df = comp_df.sort_values('detected_by', ascending=False)

    logger.info(f"\n  方法对比 (Top 交集分析):")
    logger.info(f"  {'药物':<30s} {'A(数据驱动)':>12s} {'B(通路推理)':>12s} {'C(融合)':>12s} {'方法数':>6s}")
    logger.info(f"  {'-'*72}")
    for _, row in comp_df.iterrows():
        a_rank = f"#{row['method_A_rank']}" if row['method_A_rank'] != '-' else '-'
        b_rank = f"#{row['method_B_rank']}" if row['method_B_rank'] != '-' else '-'
        c_rank = f"#{row['method_C_rank']}" if row['method_C_rank'] != '-' else '-'
        logger.info(f"  {row['drug']:<30s} {a_rank:>12s} {b_rank:>12s} {c_rank:>12s} {row['detected_by']:>6d}")

    # 统计
    n_a = sum(1 for d in all_drugs if d in a_drugs)
    n_b = sum(1 for d in all_drugs if d in b_drugs)
    n_c = sum(1 for d in all_drugs if d in c_drugs)
    n_ab = sum(1 for d in all_drugs if d in a_drugs and d in b_drugs)
    n_bc = sum(1 for d in all_drugs if d in b_drugs and d in c_drugs)
    n_ac = sum(1 for d in all_drugs if d in a_drugs and d in c_drugs)
    n_all = sum(1 for d in all_drugs if d in a_drugs and d in b_drugs and d in c_drugs)

    logger.info(f"\n  Venn 分析:")
    logger.info(f"    方法A(数据驱动): {n_a} 种药物")
    logger.info(f"    方法B(通路推理): {n_b} 种药物")
    logger.info(f"    方法C(融合)   : {n_c} 种药物")
    logger.info(f"    三法交集     : {n_all} 种药物")
    logger.info(f"    A∩B          : {n_ab} 种药物")
    logger.info(f"    B∩C          : {n_bc} 种药物")
    logger.info(f"    A∩C          : {n_ac} 种药物")

    return comp_df


# ============================================================================
# 输出报告
# ============================================================================

def generate_report(result_a, result_b, result_c, comp_df,
                    data, sample_id: str,
                    output_dir: str = OUTPUT_DIR,
                    logger: logging.Logger = None):
    """生成完整分析报告"""
    if logger is None:
        logger = setup_logging()

    report_path = os.path.join(output_dir, f"drug_analysis_report_{sample_id}.tsv")
    summary_path = os.path.join(output_dir, "method_comparison_summary.tsv")

    # 1. 融合分析结果 (主要输出)
    c_results = pd.DataFrame(result_c.get('combined_results', []))
    if not c_results.empty:
        c_results.to_csv(report_path, sep='\t', index=False)
        logger.info(f"融合分析结果: {report_path}")

    # 2. 方法对比
    if comp_df is not None and not comp_df.empty:
        comp_df.to_csv(summary_path, sep='\t', index=False)
        logger.info(f"方法对比表: {summary_path}")

    # 3. 代谢物-药物关联明细
    met_hits = result_c.get('metabolite_hits', [])
    if met_hits:
        met_df = pd.DataFrame(met_hits)
        met_path = os.path.join(output_dir, "metabolite_drug_links.tsv")
        met_df.to_csv(met_path, sep='\t', index=False)
        logger.info(f"代谢物-药物关联: {met_path}")

    return {
        'report': report_path,
        'comparison': summary_path,
    }


# ============================================================================
# 主执行函数
# ============================================================================

def main():
    """主函数: 执行完整的药物关联分析"""
    logger = setup_logging()

    print("=" * 70)
    print("  肠道微生物-药物关联分析")
    print("  方法A: 数据驱动 (Data-Driven / MASI式)")
    print("  方法B: 通路推理 (Pathway Reasoning)")
    print("  方法C: 融合分析 (推荐)")
    print("=" * 70)

    # 1. 初始化知识库并导出
    logger.info("步骤1: 初始化药物-微生物组知识库...")
    kb = DrugMicrobiomeKB()

    # 导出知识库JSON供其他工具使用
    kb_json = export_knowledge_base(KB_JSON)
    logger.info(f"  知识库统计: {kb_json['metadata']}")

    # 2. 加载样本数据
    logger.info("\n步骤2: 加载样本数据...")
    data = load_data(logger)

    if 'metabolite' not in data or data['metabolite'].empty:
        logger.error("无法加载代谢物数据，退出")
        return

    # 确定样本ID
    met_df = data['metabolite']
    sample_ids = list(met_df.columns)
    sample_id = sample_ids[0] if sample_ids else "ERR1297681"
    logger.info(f"  分析样本: {sample_id}")

    # 3. 三种方法并行分析
    logger.info("\n步骤3: 执行三种分析方法...")

    # A: 数据驱动
    start = time.time()
    result_a = analyze_method_A_data_driven(kb, data, sample_id, logger)
    time_a = time.time() - start

    # B: 通路推理
    start = time.time()
    result_b = analyze_method_B_pathway_reasoning(kb, data, sample_id, logger)
    time_b = time.time() - start

    # C: 融合分析
    start = time.time()
    result_c = analyze_method_C_combined(kb, data, sample_id, logger)
    time_c = time.time() - start

    # 4. 方法对比
    logger.info("\n步骤4: 方法对比分析...")
    comp_df = compare_methods(result_a, result_b, result_c, logger)

    # 5. 性能统计
    logger.info(f"\n  性能统计:")
    logger.info(f"    方法A(数据驱动): {time_a:.2f}s")
    logger.info(f"    方法B(通路推理): {time_b:.2f}s")
    logger.info(f"    方法C(融合分析): {time_c:.2f}s")

    # 6. 输出
    logger.info("\n步骤5: 输出报告...")
    outputs = generate_report(result_a, result_b, result_c, comp_df,
                              data, sample_id, OUTPUT_DIR, logger)

    # 7. 总结
    logger.info("\n" + "=" * 70)
    logger.info("分析完成!")
    logger.info("=" * 70)
    logger.info(f"  输入:")
    logger.info(f"    - 代谢物: {met_df.shape[0]} 种")
    logger.info(f"    - 通路: {data['pathway'].shape[0]} 条")
    logger.info(f"    - 样本: {sample_id}")
    logger.info(f"  输出:")
    logger.info(f"    - {outputs['report']}")
    logger.info(f"    - {outputs['comparison']}")
    logger.info(f"  知识库: {KB_JSON}")
    logger.info("=" * 70)

    return {
        'result_a': result_a,
        'result_b': result_b,
        'result_c': result_c,
        'comparison': comp_df,
        'outputs': outputs,
    }


# ============================================================================
# 交互式查询
# ============================================================================

def interactive_query():
    """交互式药物/代谢物查询"""
    kb = DrugMicrobiomeKB()

    print("\n" + "=" * 60)
    print("  药物-微生物组知识库交互查询")
    print("  输入 'quit' 退出")
    print("=" * 60)

    while True:
        print("\n查询选项:")
        print("  1. 查询药物 (drug)")
        print("  2. 查询代谢物 (met)")
        print("  3. 查询通路 (pw)")
        print("  4. 列出所有药物 (list_drugs)")
        print("  5. 退出 (quit)")

        cmd = input("\n> ").strip().lower()

        if cmd in ('quit', '5', 'q'):
            break
        elif cmd in ('list_drugs', '4'):
            print("\n已知微生物代谢药物:")
            for name, info in sorted(kb.drug_metabolism.items()):
                print(f"  - {info['name']:<40s} | {info['drug_class']:<20s} | {info['relevance']}")
        elif cmd in ('drug', '1'):
            name = input("药物名称: ").strip()
            result = kb.query_drug(name)
            print("\n" + json.dumps({
                'microbial_metabolism': result['microbial_metabolism'],
                'metabolite_interactions': len(result['metabolite_interactions']),
                'pathway_interactions': len(result['pathway_interactions']),
            }, ensure_ascii=False, indent=2))
        elif cmd in ('met', '2'):
            name = input("代谢物名称: ").strip()
            result = kb.query_metabolite(name)
            print(f"\n代谢物: {name}")
            print(f"已知关联: {result['known_links']['relevance'] if result['known_links'] else '无'}")
            print(f"来源通路: {result['source_pathways']}")
            print(f"相关药物数: {len(result['related_drugs'])}")
        elif cmd in ('pw', '3'):
            name = input("通路ID: ").strip()
            result = kb.query_pathway(name)
            print(f"\n通路: {name}")
            for d in result['interacting_drugs']:
                print(f"  药物类: {d['drug_class']}")
                print(f"  药物: {d['drugs']}")
                print(f"  机制: {d['mechanism']}")


# ============================================================================
# 入口
# ============================================================================

if __name__ == "__main__":
    # 检查是否要交互查询
    if len(sys.argv) > 1 and sys.argv[1] == "--interactive":
        interactive_query()
    else:
        main()
