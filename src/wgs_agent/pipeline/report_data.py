#!/usr/bin/env python3
"""
===============================================================================
报告数据加载模块 - 物种、通路、代谢物、药物数据加载
===============================================================================
"""

import os
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional

from wgs_fmt_platform.paths import bioinformatics_root

from wgs_agent.pipeline.report_common import (
    METAPHLAN_SPECIES_FILE, METAPHLAN_GENUS_FILE,
    PATHWAY_KNOWN_FILE, PATHWAY_CONTRIB_FILE, PATHWAY_COMBINED_FILE,
    METABOLITE_MATRIX_FILE, METABOLITE_SUMMARY_FILE, METABOLITE_CONTRIB_FILE,
    DRUG_ANALYSIS_DIR, DRUG_ANALYSIS_FILE, METABOLITE_DRUG_FILE,
    METHOD_COMPARISON_FILE,
    SPECIES_REF_FILE, SPECIES_REF_EXTENDED, SPECIES_STATS_FILE, PHENOTYPE_FILE,
    metaphlan_name_to_species, metaphlan_name_to_genus,
    get_health_status, parse_p5p95,
)


def _bioinformatics_output_root() -> Path:
    return bioinformatics_root()


def _finite_nonnegative_profile(values: pd.Series) -> pd.Series:
    """Keep reported zeros; missing or invalid values are not zero measurements."""
    numeric = pd.to_numeric(values, errors="coerce")
    return numeric[numeric.notna() & np.isfinite(numeric) & (numeric >= 0)].sort_values(ascending=False)


def _load_single_metaphlan(sample_id: str, rank: str) -> Optional[pd.Series]:
    """Read one uploaded sample directly from the resumable pipeline output."""
    profile = _bioinformatics_output_root() / "profiles/metaphlan" / f"{sample_id}_profile.tsv"
    if not profile.is_file():
        return None
    prefix = f"{rank}__"
    values: dict[str, float] = {}
    try:
        with profile.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip() or line.startswith("#"):
                    continue
                columns = line.rstrip("\n").split("\t")
                leaf = columns[0].rsplit("|", 1)[-1]
                if leaf.startswith(prefix):
                    values[columns[0]] = float(columns[2])
    except (OSError, ValueError, IndexError):
        return None
    if not values:
        return None
    return pd.Series(values, name=sample_id, dtype=float).sort_values(ascending=False)


def _load_single_humann_pathways(sample_id: str) -> Optional[pd.Series]:
    path = (
        _bioinformatics_output_root()
        / "profiles/humann"
        / f"{sample_id}_pathabundance_relab.tsv"
    )
    if not path.is_file():
        return None
    try:
        frame = pd.read_csv(path, sep="\t", comment="#", header=None, index_col=0)
        if frame.empty:
            return None
        values = pd.to_numeric(frame.iloc[:, 0], errors="coerce").dropna()
        # Unstratified rows describe the total pathway abundance; species
        # contributions remain available in the original HUMAnN artifact.
        values = values[~values.index.astype(str).str.contains("|", regex=False)]
        return _finite_nonnegative_profile(values)
    except (OSError, ValueError, IndexError):
        return None


# ============================================================================
# 1. 物种数据
# ============================================================================

def load_species_data(sample_id: str) -> Tuple[pd.Series, pd.DataFrame, pd.DataFrame]:
    """
    加载物种丰度及健康参考数据
    返回: (sample_species_series, ref_p5p95_df, ref_stats_df)
    """
    sp = _read_tsv_index(METAPHLAN_SPECIES_FILE)
    col = _best_col(sp, sample_id, warn=False) if sp is not None else None
    if col is not None:
        sample_data = sp[col]
    else:
        sample_data = _load_single_metaphlan(sample_id, "s")
        if sample_data is None:
            if sp is not None:
                _best_col(sp, sample_id, warn=True)
            return pd.Series(dtype=float), None, None
    sample_data = sample_data[sample_data > 0]

    # 优先使用扩充参考库（694 种物种），回退到旧库
    ref_p5p95 = None
    ref_stats = None
    ref_source = "无"

    # ── 层级 1: 扩充参考库 (扩展长表格式) ──
    if os.path.exists(SPECIES_REF_EXTENDED):
        try:
            reference_separator = (
                '\t' if str(SPECIES_REF_EXTENDED).lower().endswith(('.tsv', '.txt')) else ','
            )
            ref_p5p95 = pd.read_csv(SPECIES_REF_EXTENDED, sep=reference_separator)
            # 验证格式：必须包含 species/p5/p95 列
            if 'species' in ref_p5p95.columns and 'p5' in ref_p5p95.columns and 'p95' in ref_p5p95.columns:
                ref_source = f"扩充库 ({len(ref_p5p95)} 种)"
                print(f"       [参考] ✅ 使用扩充参考库 ({len(ref_p5p95)} 种)")
            else:
                print(f"       [参考] ⚠️ 扩充库格式不符，回退...")
                ref_p5p95 = None
        except Exception as e:
            print(f"       [参考] ⚠️ 扩充库加载失败: {e}，回退...")
            ref_p5p95 = None

    # ── 层级 2: 旧版参考库 (宽表格式) ──
    if ref_p5p95 is None:
        if os.path.exists(SPECIES_REF_FILE):
            try:
                ref_p5p95 = pd.read_csv(SPECIES_REF_FILE).set_index('Phenotype')
                ref_stats = pd.read_csv(SPECIES_STATS_FILE)
                ref_source = f"旧参考库 ({len(ref_p5p95.columns)} 种)"
                print(f"       [参考] ✅ 使用旧版参考库 ({len(ref_p5p95.columns)} 种)")
            except Exception as e:
                print(f"       [参考] ⚠️ 旧参考库加载失败: {e}")
                ref_p5p95 = None
                ref_stats = None
        else:
            print(f"       [参考] ⚠️ 旧参考库文件不存在: {SPECIES_REF_FILE}")

    # ── 层级 3: 无参考 — 所有物种标记为 unknown ──
    if ref_p5p95 is None:
        print(f"       [参考] ❌ 无可用参考库，所有物种将标记为「无参考」")

    return sample_data, ref_p5p95, ref_stats


# ============================================================================
# 2. 肠型判定
# ============================================================================

def determine_enterotype(sample_id: str) -> Dict:
    """基于属水平丰度判定肠型"""
    genus = _read_tsv_index(METAPHLAN_GENUS_FILE)
    col = _best_col(genus, sample_id, warn=False) if genus is not None else None
    if col is not None:
        row = genus[col]
    else:
        row = _load_single_metaphlan(sample_id, "g")
        if row is None:
            return {"type": "未知", "confidence": 0}
    total = row.sum()
    if total == 0:
        return {"type": "未知", "confidence": 0}

    genus_map = {}
    for col_name in row.index:
        g = metaphlan_name_to_genus(col_name)
        genus_map[g] = row[col_name]

    bact = genus_map.get('Bacteroides', 0) + genus_map.get('Phocaeicola', 0)
    prev = genus_map.get('Prevotella', 0) + genus_map.get('Segatella', 0)
    runinococcus = genus_map.get('Faecalibacterium', 0)

    b_r = bact / total * 100
    p_r = prev / total * 100
    r_r = runinococcus / total * 100

    if b_r > max(p_r, r_r) and b_r > 10:
        etype = "Bacteroides型（肠型1）"
        conf = min(b_r / 30, 1.0) * 100
        summary = "西方饮食模式常见，擅长分解动物蛋白和脂肪"
    elif p_r > max(b_r, r_r) and p_r > 5:
        etype = "Prevotella型（肠型2）"
        conf = min(p_r / 30, 1.0) * 100
        summary = "植物性饮食相关，纤维发酵能力强"
    else:
        etype = "Ruminococcus型（肠型3）"
        conf = min(max(r_r, b_r) / 20, 1.0) * 100
        summary = "混合型肠型，通常与高多样性相关"

    return {
        "type": etype, "confidence": round(conf, 1),
        "Bacteroides_ratio": round(b_r, 2),
        "Prevotella_ratio": round(p_r, 2),
        "Faecalibacterium_ratio": round(r_r, 2),
        "summary": summary,
        "top_genus": sorted(genus_map.items(), key=lambda x: -x[1])[:5]
    }


# ============================================================================
# 3. 物种-健康参考对比
# ============================================================================

def _is_unclassified_sgb(species_name: str) -> bool:
    name = str(species_name or "").strip().lower()
    return not name or name.startswith("sgb") or " sgb" in name or "unclassified" in name


def compare_species_with_reference(sample_data: pd.Series,
                                   ref_p5p95: pd.DataFrame,
                                   ref_stats: pd.DataFrame,
                                   top_n: int | None = None) -> List[Dict]:
    """将样本物种丰度与健康参考范围逐一比较

    支持两种参考库格式：
    1. 扩展长表: columns = [species, p5, p25, p50, p75, p95, ...]
    2. 旧宽表: index='Phenotype', species as columns with 'P5-P95' range strings
    """
    results = []
    if ref_p5p95 is None:
        for metaphlan_name, abundance in sample_data.items():
            species_name = metaphlan_name_to_species(metaphlan_name)
            if _is_unclassified_sgb(species_name):
                continue
            results.append(dict(
                species=species_name, abundance=round(abundance, 4),
                p5=0, p95=0, status='unknown', status_cn='无参考',
                deviation=0, mean_health=0, n_health=0
            ))
        return results if top_n is None else results[:top_n]

    # 检测格式：长表有 'species' 列，宽表有 'Phenotype' 索引
    ref_ranges: dict[str, tuple[float, float]] = {}
    n_health_lookup: dict[str, int] = {}

    if 'species' in ref_p5p95.columns and 'p5' in ref_p5p95.columns and 'p95' in ref_p5p95.columns:
        # ── 扩展长表格式 ──
        for _, row in ref_p5p95.iterrows():
            species_key = str(row['species']).strip()
            # 去掉 s__ 前缀（兼容 MetaPhlAn 命名风格）
            if species_key.startswith('s__'):
                species_key = species_key[3:]
            species_key = species_key.replace('_', ' ').lower().strip()
            p5 = float(row.get('p5', 0) or 0)
            p95 = float(row.get('p95', 0) or 0)
            ref_ranges[species_key] = (p5, p95)
            n_health_lookup[species_key] = int(row.get('n_detected', 0) or 0)
    else:
        # ── 旧宽表格式 ──
        for col in ref_p5p95.columns:
            val = ref_p5p95[col].values[0]
            p5, p95 = parse_p5p95(str(val))
            ref_ranges[col.lower().strip()] = (p5, p95)

        stats_lookup = {}
        if ref_stats is not None:
            for _, r in ref_stats.iterrows():
                stats_lookup[r['Taxon'].lower().strip()] = r

    for metaphlan_name, abundance in sample_data.items():
        species_name = metaphlan_name_to_species(metaphlan_name)
        if _is_unclassified_sgb(species_name):
            continue
        key = species_name.lower().strip()
        p5, p95 = ref_ranges.get(key, (0, 0))
        status, status_cn = get_health_status(abundance, p5, p95)

        n_health = n_health_lookup.get(key, 0)
        mean_health = 0

        deviation = 0
        if p95 > p5:
            mid = (p5 + p95) / 2
            half = (p95 - p5) / 2
            if abundance > 0:
                deviation = (abundance - mid) / half

        results.append(dict(
            species=species_name, abundance=round(abundance, 4),
            p5=round(p5, 4), p95=round(p95, 4),
            status=status, status_cn=status_cn,
            deviation=round(deviation, 2),
            mean_health=mean_health, n_health=n_health,
        ))

    status_order = {'high': 0, 'low': 1, 'unknown': 2, 'normal': 3, 'absent': 4}
    results.sort(key=lambda x: (status_order.get(x['status'], 9), -abs(x['deviation'])))
    return results if top_n is None else results[:top_n]


# ============================================================================
# 4. 通路数据
# ============================================================================

def load_pathway_data(sample_id: str) -> Tuple[pd.Series, Optional[pd.DataFrame]]:
    """加载通路丰度数据：返回 (pathway_series, contribution_df)"""
    try:
        pw = _read_tsv_index(PATHWAY_KNOWN_FILE)
        best = _best_col(pw, sample_id, warn=False) if pw is not None else None
        if best is not None:
            path_data = _finite_nonnegative_profile(pw[best])
            contrib = _read_tsv_index(PATHWAY_CONTRIB_FILE)
            print(f'       通路数: {len(path_data)}（列: {best}）')
            return path_data, contrib
    except Exception as e:
        print(f'       通路加载失败: {e}')

    uploaded = _load_single_humann_pathways(sample_id)
    if uploaded is not None:
        return uploaded, None

    # 兜底
    try:
        contrib = _read_tsv_index(PATHWAY_CONTRIB_FILE)
        best = _best_col(contrib, sample_id)
        path_data = _finite_nonnegative_profile(contrib[best])
        print(f'       通路数: {len(path_data)}（贡献文件列: {best}）')
        return path_data, contrib
    except:
        return None, None


# ============================================================================
# 5. 代谢物数据
# ============================================================================

def load_metabolite_data(sample_id: str) -> Tuple[pd.Series, Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """加载代谢物含量数据：返回 (met_values, summary_df, contribution_df)"""
    met = _read_tsv_index(METABOLITE_MATRIX_FILE)
    if met is None:
        return None, None, None

    col = _best_col(met, sample_id, warn=True)
    met_values = _finite_nonnegative_profile(met[col])
    print(f'       代谢物数: {len(met_values)}（列: {col}）')

    summary = _read_tsv(METABOLITE_SUMMARY_FILE)
    contrib = _read_tsv_index(METABOLITE_CONTRIB_FILE)
    return met_values, summary, contrib


# ============================================================================
# 6. 药物数据
# ============================================================================

def load_drug_data(sample_id: str) -> Optional[pd.DataFrame]:
    """加载药物-微生物组交互分析结果"""
    # 方法1: 精确匹配
    drug_file = DRUG_ANALYSIS_FILE.format(sample=sample_id)
    if os.path.exists(drug_file):
        return _read_tsv(drug_file)

    # 方法2: 目录搜索
    if os.path.isdir(DRUG_ANALYSIS_DIR):
        for f in sorted(os.listdir(DRUG_ANALYSIS_DIR)):
            if sample_id in f and f.endswith('.tsv') and 'drug' in f.lower():
                df = _read_tsv(os.path.join(DRUG_ANALYSIS_DIR, f))
                if df is not None:
                    print(f'       找到药物文件: {f}')
                    return df

    # 方法3: 方法对比汇总
    mc = _read_tsv(METHOD_COMPARISON_FILE)
    if mc is not None and 'method_C_score' in mc.columns:
        mc = mc.rename(columns={
            'method_C_score': 'combined_score',
            'method_A_score': 'metabolite_based_score',
            'method_B_score': 'pathway_based_score',
        })
        for col in ['metabolite_based_score', 'pathway_based_score', 'combined_score']:
            if col in mc.columns:
                mc[col] = pd.to_numeric(mc[col], errors='coerce').fillna(0)
        print(f'       使用方法对比汇总，药物数: {len(mc)}')
        return mc
    return None


def load_metabolite_drug_links() -> Optional[pd.DataFrame]:
    """加载代谢物-药物关联数据"""
    return _read_tsv(METABOLITE_DRUG_FILE)


# ============================================================================
# 内部工具
# ============================================================================

def _read_tsv(path: str) -> Optional[pd.DataFrame]:
    try:
        return pd.read_csv(path, sep='\t')
    except:
        return None


def _read_tsv_index(path: str) -> Optional[pd.DataFrame]:
    try:
        return pd.read_csv(path, sep='\t', index_col=0)
    except:
        return None


def _best_col(df: pd.DataFrame, sid: str, warn: bool = True) -> Optional[str]:
    """找到最匹配样本ID的列，找不到返回 None（不静默回退到随机列）"""
    cols = [str(c) for c in df.columns]
    exact = [c for c in cols if sid == c]
    if exact:
        return exact[0]
    partial = [c for c in cols if sid in c]
    if partial:
        return partial[0]
    if warn and cols:
        # 列出前 10 个可用样本帮助用户纠错
        sample_ids = [c for c in cols if c.startswith("SRR") or c.startswith("ERR")][:10]
        msg = f"样本 '{sid}' 不在矩阵中。可用样本: {', '.join(sample_ids)} ..."
        print(f"       提示: {msg}")
        raise KeyError(msg)
    return None
