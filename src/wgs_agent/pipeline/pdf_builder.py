# -*- coding: utf-8 -*-
"""
pdf_builder.py
将报告 Markdown 文本转为结构化数据后，渲染进 LaTeX 模板, 然后调用 xelatex 编译为 PDF。

注意:
- 需要本机安装 TeX 发行版 (Linux: TeX Live), 并确保 xelatex 命令在 PATH 中。
- 需要本机安装支持中文的字体 (如 Noto Sans CJK SC), 并在字体路径正确。
- LaTeX 对特殊字符敏感(如 % & # _ 等), 本模块会自动转义正文中的这些字符,
  避免编译失败。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime as _dt
from typing import Any

import jinja2

# ── 配置 ─────────────────────────────────────────────────────────────

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_TEMPLATES_DIR = os.path.join(_CURRENT_DIR, "templates")
_DEFAULT_OUTPUT_DIR = "/storage1/zhangrongpeng/fmt-data/output/reports"

# xelatex 路径（texlive 用户目录安装）
_LATEX_ENGINE = os.path.expanduser("~/texlive/2026/bin/x86_64-linux/xelatex")

# CJK 字体（Noto Sans CJK SC）
_CJK_FONT_MAIN = "Noto Sans CJK SC"
_CJK_FONT_SANS = "Noto Sans CJK SC"
_CJK_FONT_PATH = os.path.expanduser("~/.fonts/noto-cjk.otf")

# ── LaTeX 特殊字符转义表 ─────────────────────────────────────────────

_LATEX_SPECIAL_CHARS = {
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
    "\\": r"\textbackslash{}",
}

_ESCAPE_RE = re.compile("|".join(re.escape(k) for k in _LATEX_SPECIAL_CHARS.keys()))

_BENEFICIAL_KEYWORDS = (
    "faecalibacterium", "bifidobacterium", "lactobacillus", "akkermansia",
    "roseburia", "eubacterium", "coprococcus", "butyricicoccus",
    "anaerobutyricum", "fusicatenibacter", "subdoligranulum",
)

_HARMFUL_KEYWORDS = (
    "escherichia", "shigella", "klebsiella", "enterococcus", "clostridioides",
    "fusobacterium", "desulfovibrio", "bilophila", "campylobacter",
    "streptococcus", "veillonella", "prevotella copri",
)


def escape_latex(text: str | None) -> str:
    """转义文本中的 LaTeX 特殊字符，同时保留 **粗体** 标记转换为 \\textbf{}"""
    if text is None:
        return ""

    # 先处理 **粗体** -> 占位符, 避免被转义破坏
    bold_pattern = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
    placeholders: list[str] = []

    def _store_bold(m: re.Match) -> str:
        placeholders.append(m.group(1))
        return f"@@BOLD{len(placeholders)-1}@@"

    text = bold_pattern.sub(_store_bold, text)

    # 转义特殊字符
    text = _ESCAPE_RE.sub(lambda m: _LATEX_SPECIAL_CHARS[m.group(0)], text)

    # 还原粗体(对内容也做转义)
    def _restore_bold(m: re.Match) -> str:
        idx = int(m.group(1))
        content = placeholders[idx]
        content_escaped = _ESCAPE_RE.sub(lambda mm: _LATEX_SPECIAL_CHARS[mm.group(0)], content)
        return r"\textbf{" + content_escaped + "}"

    text = re.sub(r"@@BOLD(\d+)@@", _restore_bold, text)

    return text


def latex_image_path(path: str | None) -> str:
    if not path:
        return ""
    return str(path).replace("\\", "/")


def _fmt_ref_range(item: dict[str, Any]) -> str:
    if item.get("ref_range"):
        return str(item.get("ref_range"))
    if item.get("p5") is not None or item.get("p95") is not None:
        return f"{item.get('p5', 0):.4f}-{item.get('p95', 0):.4f}"
    if item.get("lower") is not None or item.get("upper") is not None:
        return f"{item.get('lower', 0):.4f}-{item.get('upper', 0):.4f}"
    return "-"


def _pick_species_rows(species_data: dict[str, Any], sp_list: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    explicit = species_data.get(f"{kind}_species", [])
    if explicit:
        return explicit

    keywords = _BENEFICIAL_KEYWORDS if kind == "beneficial" else _HARMFUL_KEYWORDS
    rows = []
    for item in sp_list:
        name = str(item.get("species", "")).lower()
        if any(keyword in name for keyword in keywords):
            rows.append(item)

    rows.sort(key=lambda item: float(item.get("abundance", 0) or 0), reverse=True)
    return rows[:8]


# ── Jinja2 环境 ──────────────────────────────────────────────────────

def _get_jinja_env() -> jinja2.Environment:
    """创建 Jinja2 环境, 使用自定义定界符避免与 LaTeX 语法冲突"""
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(_TEMPLATES_DIR),
        variable_start_string="<{",
        variable_end_string="}>",
        block_start_string="<%",
        block_end_string="%>",
        comment_start_string="<#",
        comment_end_string="#>",
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return env


# ── 数据准备：将 report_maker 输出的 dict 转为模板上下文 ─────────────

def build_context(
    sample_id: str,
    species_data: dict[str, Any],
    compare_data: dict[str, Any],
    enterotype_data: dict[str, Any],
    pathway_data: dict[str, Any],
    metabolite_data: dict[str, Any],
    drug_data: dict[str, Any],
    disease_data: dict[str, Any],
    knowledge_data: dict[str, Any],
    llm_advice: str = "",
    fmt_matching_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """将各模块数据字典转换为 LaTeX 模板所需的上下文"""
    ctx: dict[str, Any] = {}

    # 基本信息
    ctx["sample_id"] = escape_latex(sample_id)
    ctx["report_date"] = _dt.now().strftime("%Y-%m-%d %H:%M UTC")

    # ── 物种数据 ──
    sp_list = species_data.get("species_list", species_data.get("species_list", []))
    if not sp_list and isinstance(species_data, dict):
        sp_list = species_data.get("species_list", [])
    abnormal = species_data.get("abnormal_species", [])
    if not abnormal:
        abnormal = [s for s in (sp_list or []) if s.get("status") in ("high", "low")]
    n_total = len(sp_list)
    n_normal = sum(1 for s in sp_list if s.get("status") == "normal")
    n_high = sum(1 for s in sp_list if s.get("status") == "high")
    n_low = sum(1 for s in sp_list if s.get("status") == "low")
    n_known = n_total - sum(1 for s in sp_list if s.get("status") == "unknown")
    species_score = round((n_normal / max(n_known, 1)) * 100, 1)

    ctx["n_total"] = n_total
    ctx["n_normal"] = n_normal
    ctx["n_high"] = n_high
    ctx["n_low"] = n_low
    ctx["species_score"] = species_score
    if n_high or n_low:
        species_interp = (
            f"本次检测有 {n_high + n_low} 个物种偏离健康参考范围，提示肠道菌群存在一定波动。"
            "建议优先关注异常表格中的物种，并结合近期饮食、抗生素使用、腹泻或便秘等情况综合判断。"
        )
    else:
        species_interp = "本次检测物种整体处于参考范围内，说明菌群组成相对平稳，可继续保持规律饮食和作息。"
    ctx["species_patient_interpretation"] = escape_latex(species_interp)

    from wgs_agent.tools.report_maker import _species_comment

    def _build_species_table_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = []
        for s in items:
            rows.append({
                "species": escape_latex(str(s.get("species", "?"))[:48]),
                "chinese_name": escape_latex(str(s.get("chinese_name", ""))[:18]),
                "abundance": f"{float(s.get('abundance', 0) or 0):.4f}",
                "ref_range": escape_latex(_fmt_ref_range(s)),
                "status_cn": escape_latex(str(s.get("status_cn") or s.get("status") or "")),
                "summary": escape_latex(str(s.get("summary") or _species_comment(s))[:120]),
            })
        return rows

    def _status_cn(item: dict[str, Any]) -> str:
        status = str(item.get("status_cn") or item.get("status") or "")
        if status == "high":
            return "偏高"
        if status == "low":
            return "偏低"
        if status == "normal":
            return "正常"
        if status == "unknown":
            return "未知"
        return status or "-"

    if abnormal:
        abnormal_rows = []
        for s in abnormal[:15]:
            deviation = s.get("deviation", 0)
            try:
                deviation_text = f"{float(deviation):+.2f}"
            except (TypeError, ValueError):
                deviation_text = str(deviation or "-")
            abnormal_rows.append({
                "species": escape_latex(str(s.get("species", "?"))[:45]),
                "chinese_name": escape_latex(str(s.get("chinese_name", ""))[:16]),
                "abundance": f"{float(s.get('abundance', 0) or 0):.4f}",
                "status": escape_latex(_status_cn(s)),
                "deviation": escape_latex(deviation_text),
                "summary": escape_latex(str(s.get("summary") or _species_comment(s))[:110]),
            })
        ctx["abnormal_species"] = abnormal_rows

    normal_top = sorted(
        [s for s in (sp_list or []) if s.get("status") == "normal"],
        key=lambda item: float(item.get("abundance", 0) or 0),
        reverse=True,
    )[:10]
    if normal_top:
        ctx["normal_top_species"] = [
            {
                "species": escape_latex(str(s.get("species", "?"))[:48]),
                "chinese_name": escape_latex(str(s.get("chinese_name", ""))[:18]),
                "abundance": f"{float(s.get('abundance', 0) or 0):.4f}",
                "ref_range": escape_latex(_fmt_ref_range(s)),
            }
            for s in normal_top
        ]

    beneficial_rows = _build_species_table_rows(_pick_species_rows(species_data, sp_list, "beneficial"))
    harmful_rows = _build_species_table_rows(_pick_species_rows(species_data, sp_list, "harmful"))
    if beneficial_rows:
        ctx["beneficial_species"] = beneficial_rows
    if harmful_rows:
        ctx["harmful_species"] = harmful_rows

    # ── 肠型数据 ──
    ent_value = enterotype_data.get("enterotype", "")
    ent_conf = enterotype_data.get("confidence", 0)
    if ent_value:
        from wgs_agent.tools.report_maker import _ENTEROTYPE_DESC

        desc = ""
        et = str(ent_value or "")
        for key, text in _ENTEROTYPE_DESC.items():
            if key in et:
                desc = text.replace("**", "")
                break

        ctx["enterotype"] = {
            "enterotype": escape_latex(str(ent_value)),
            "confidence": f"{ent_conf:.1f}",
            "description": escape_latex(desc),
        }
        ctx["enterotype_patient_interpretation"] = escape_latex(
            f"您的肠型更接近 {ent_value}。肠型反映长期饮食和菌群生态特征，不等同于疾病诊断；"
            "如果置信度较高，说明样本与该类人群特征更接近。"
        )

    basis = enterotype_data.get("classification_basis") or enterotype_data.get("details") or {}
    if isinstance(basis, dict):
        marker_rows = []
        for label, key in (
            ("Bacteroides/Phocaeicola", "Bacteroides_ratio"),
            ("Prevotella/Segatella", "Prevotella_ratio"),
            ("Faecalibacterium", "Faecalibacterium_ratio"),
        ):
            if key in basis:
                marker_rows.append({
                    "marker": escape_latex(label),
                    "ratio": f"{float(basis.get(key, 0) or 0):.2f}",
                })
        if marker_rows:
            ctx["enterotype_marker_basis"] = marker_rows

        top_genus = basis.get("top_genus") or []
        genus_rows = []
        for item in top_genus[:5]:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                genus_name, abundance = item[0], item[1]
            elif isinstance(item, dict):
                genus_name, abundance = item.get("genus", ""), item.get("abundance", 0)
            else:
                continue
            genus_rows.append({
                "genus": escape_latex(str(genus_name)),
                "abundance": f"{float(abundance or 0):.4f}",
            })
        if genus_rows:
            ctx["enterotype_top_genus"] = genus_rows

    et_distribution = enterotype_data.get("distribution") or enterotype_data.get("enterotype_distribution") or []
    if isinstance(et_distribution, dict):
        et_distribution = [{"label": k, "count": v} for k, v in et_distribution.items()]
    if et_distribution:
        ctx["enterotype_distribution"] = [
            {
                "label": escape_latex(str(row.get("label") or row.get("enterotype") or "")),
                "count": row.get("count", "-"),
                "percent": escape_latex(str(row.get("percent", ""))),
            }
            for row in et_distribution
        ]

    relation_text = enterotype_data.get("relation_summary") or enterotype_data.get("matching_summary") or ""
    if relation_text:
        ctx["enterotype_relation_summary"] = escape_latex(str(relation_text))

    silhouette_score = enterotype_data.get("silhouette_score")
    if silhouette_score is not None:
        ctx["enterotype_silhouette"] = f"{float(silhouette_score):.3f}"

    cluster_plot = (
        enterotype_data.get("cluster_plot")
        or enterotype_data.get("cluster_plot_path")
        or enterotype_data.get("image_path")
        or enterotype_data.get("plot_path")
    )
    if cluster_plot:
        ctx["enterotype_cluster_plot"] = latex_image_path(cluster_plot)
        ctx["enterotype_plot_interpretation"] = escape_latex(
            "图中当前样本越靠近某一类参考样本，说明菌群结构越相似；如果位于类群边缘，提示菌群结构可能介于多种肠型之间。"
        )

    # ── 通路数据 ──
    from wgs_agent.tools.report_maker import _PATHWAY_IMPLICATIONS

    path_list = pathway_data.get("pathways", [])
    if path_list:
        pw_rows = []
        for p in path_list[:15]:
            name = str(p.get("name", ""))[:40]
            abund = p.get("abundance", 0)
            imp = ""
            for kw, text in _PATHWAY_IMPLICATIONS.items():
                if kw in name.upper():
                    imp = text[:60]
                    break
            pw_rows.append({
                "name": escape_latex(name),
                "abundance": f"{abund:.4f}",
                "implication": escape_latex(imp),
            })
        ctx["pathway_data"] = pw_rows
        ctx["pathway_count"] = len(path_list)
        ctx["pathway_patient_interpretation"] = escape_latex(
            "代谢通路反映菌群可能参与的功能活动。短链脂肪酸、维生素和氨基酸相关通路较活跃时，通常提示菌群功能储备较好；"
            "若关键通路偏弱，建议结合膳食纤维摄入和胃肠症状进一步评估。"
        )

    # ── 代谢物数据 ──
    from wgs_agent.tools.report_maker import _met_ref

    met_list = metabolite_data.get("metabolites", [])
    if met_list:
        met_rows = []
        for m in met_list[:20]:
            name = str(m.get("name", "?"))[:30]
            abund = m.get("abundance", 0)
            ref = _met_ref(name)
            met_rows.append({
                "name": escape_latex(name),
                "abundance": f"{abund:.4f}",
                "ref_range": escape_latex(ref),
            })
        ctx["metabolite_data"] = met_rows
        ctx["metabolite_count"] = len(met_list)
        ctx["metabolite_patient_interpretation"] = escape_latex(
            "代谢物结果用于观察菌群功能的下游表现。丁酸、丙酸等短链脂肪酸与肠屏障和炎症调节相关；"
            "单个代谢物异常不代表疾病，需要结合饮食、症状和其他检测结果解读。"
        )

    # ── 药物数据 ──
    drugs = drug_data.get("drugs", [])
    high_drugs = drug_data.get("high_risk_drugs", [d for d in drugs if d.get("is_high_risk")])
    ctx["drug_advice"] = [
        escape_latex("优先选择低交互评分的药物（<10,000），以减少对肠道微生态的干扰。"),
        escape_latex("若高交互药物不可避免，建议同时使用益生菌或益生元支持菌群恢复。"),
        escape_latex("使用高评分抗生素后，关注抗生素相关性腹泻及艰难梭菌感染风险。"),
    ]
    if drugs:
        ctx["drug_data"] = True
        ctx["drug_count"] = len(drugs)
        ctx["high_risk_count"] = len(high_drugs)
        ctx["drug_patient_interpretation"] = escape_latex(
            f"本次药物分析中有 {len(high_drugs)} 项属于较高菌群交互风险。"
            "这表示这些药物更可能扰动肠道菌群，并不代表不能使用；实际用药仍应以医生处方为准。"
        )

        if high_drugs:
            hd_rows = []
            for d in high_drugs[:10]:
                hd_rows.append({
                    "drug": escape_latex(str(d.get("drug", "?"))[:50]),
                    "score": f"{d.get('score', 0):.0f}",
                })
            ctx["high_risk_drugs"] = hd_rows

        all_drugs = drugs[:20]
        if all_drugs:
            ad_rows = []
            for d in all_drugs:
                risk = "高风险" if d.get("is_high_risk") else "低风险"
                ad_rows.append({
                    "drug": escape_latex(str(d.get("drug", "?"))[:45]),
                    "score": f"{d.get('score', 0):.0f}",
                    "risk_level": risk,
                })
            ctx["all_drugs"] = ad_rows

    # ── 疾病数据 ──
    diseases = disease_data.get("diseases", [])
    ctx["disease_risk_note"] = escape_latex(
        "基于 gutMDisorder/Disbiome 公开数据库匹配，风险评分 = 方向一致比例(60%) + 异常程度(40%)。"
    )
    ctx["disease_disclaimer"] = escape_latex(
        "匹配度高不意味着必然患有该疾病，仅提示菌群微生态在统计学上的高相似性。"
    )
    if diseases:
        high_risk = [d for d in diseases if d.get("risk_level") == "high" or d.get("risk_score", 0) >= 75]
        mid_risk = [d for d in diseases if (d.get("risk_level") == "medium" or 25 <= d.get("risk_score", 0) < 75) and d not in high_risk]
        low_risk = [d for d in diseases if d not in high_risk and d not in mid_risk]

        if high_risk:
            hr_rows = []
            for d in high_risk[:5]:
                sp_names = ", ".join(
                    str(s.get("species", ""))[:15] for s in d.get("key_species", [])[:3]
                )
                hr_rows.append({
                    "disease": escape_latex(str(d.get("disease", "?"))[:25]),
                    "risk_score": d.get("risk_score", 0),
                    "matched_species": d.get("matched_species", 0),
                    "agree_count": d.get("agree_count", 0),
                    "key_species": escape_latex(sp_names[:50]),
                })
            ctx["high_risk_diseases"] = hr_rows
        max_risk = max((float(d.get("risk_score", 0) or 0) for d in diseases), default=0)
        ctx["disease_patient_interpretation"] = escape_latex(
            f"本次最高疾病关联评分为 {max_risk:.0f}/100。该评分表示菌群特征与公开数据库中某些疾病相关特征的相似程度，"
            "不能直接用于诊断；如已有相关症状或家族史，建议带报告咨询临床医生。"
        )

        if mid_risk:
            mr_rows = []
            for d in mid_risk[:5]:
                mr_rows.append({
                    "disease": escape_latex(str(d.get("disease", "?"))[:30]),
                    "risk_score": d.get("risk_score", 0),
                    "matched_species": d.get("matched_species", 0),
                    "agree_count": d.get("agree_count", 0),
                })
            ctx["mid_risk_diseases"] = mr_rows

        if low_risk:
            lr_rows = []
            for d in low_risk[:5]:
                lr_rows.append({
                    "disease": escape_latex(str(d.get("disease", "?"))[:50]),
                    "risk_score": d.get("risk_score", 0),
                    "matched_species": d.get("matched_species", 0),
                    "agree_count": d.get("agree_count", 0),
                })
            ctx["low_risk_diseases"] = lr_rows
    else:
        ctx["disease_empty_message"] = escape_latex("当前未匹配到明确的疾病-物种关联数据。")
        ctx["disease_patient_interpretation"] = escape_latex(
            "未匹配到明确疾病关联是相对积极的结果，但仍不能替代常规体检或医生评估。"
        )

    # ── 综合评分 ──
    disease_penalty = sum(
        12 if d.get("risk_score", 0) >= 75 else
        8 if d.get("risk_score", 0) >= 50 else
        4 if d.get("risk_score", 0) >= 25 else 0
        for d in diseases[:3]
    )
    drug_risk_pct = round(len(high_drugs) / max(len(drugs), 1) * 100, 1) if drugs else 0
    overall = max(0, min(100, round(
        species_score * 0.50 + min(float(ent_conf), 50) * 0.15 +
        max(0, 100 - drug_risk_pct) * 0.15 + max(0, 100 - disease_penalty) * 0.10 + 5
    )))
    if overall >= 80: rating = "优秀：肠道菌群整体健康状况良好"
    elif overall >= 60: rating = "良好：大部分指标正常，部分需关注"
    elif overall >= 40: rating = "需关注：存在一定肠道微生态失衡风险"
    else: rating = "需干预：肠道菌群失调较明显，建议咨询医生"

    ctx["overall_score"] = overall
    ctx["rating"] = escape_latex(rating)
    ctx["dim_species"] = species_score
    ctx["dim_stability"] = max(0, 100 - (n_high + n_low) * 3)
    ctx["dim_disease"] = max(0, 100 - disease_penalty)
    ctx["dim_drug"] = max(0, 100 - drug_risk_pct)
    ctx["overall_patient_interpretation"] = escape_latex(
        f"综合评分为 {overall}/100，整体判断为“{rating}”。该评分用于帮助定位需要关注的方向，"
        "不是临床诊断结论；优先改善饮食结构、规律作息，并根据异常项目决定是否复查。"
    )

    # LLM 建议
    if llm_advice:
        ctx["llm_advice"] = escape_latex(llm_advice)

    # ── FMT 配型 ──
    ctx["fmt_explanation"] = escape_latex(
        "FMT 配型说明: 使用受体—供体—移植后样本三元组对比模型。物种丰度经 CLR、训练集标准化和共享投影后，"
        "按嵌入距离排序候选供体。相对匹配分不是临床成功概率；供体仍须完成感染、病史、代谢和临床适配筛查。"
    )
    if fmt_matching_data and fmt_matching_data.get("status") == "ok":
        ctx["fmt_ok"] = True
        ctx["fmt_message"] = escape_latex(str(fmt_matching_data.get("message", "")))
        tsne_plot = fmt_matching_data.get("tsne_plot_path") or fmt_matching_data.get("plot_path")
        if tsne_plot:
            ctx["fmt_tsne_plot"] = latex_image_path(str(tsne_plot))
            ctx["fmt_plot_interpretation"] = escape_latex(
                f"FMT 图使用 {fmt_matching_data.get('plot_method', '嵌入降维')} 展示候选供体与查询样本。"
                "图上接近仅表示模型嵌入相似，不能替代临床供体筛查。"
            )
        audit = fmt_matching_data.get("feature_audit", {})
        if audit:
            ctx["fmt_quality_note"] = escape_latex(
                f"特征名称覆盖率 {float(audit.get('feature_name_coverage', 0)):.1%}；"
                f"模型特征丰度覆盖率 {float(audit.get('abundance_coverage', 0)):.1%}；"
                f"模型版本 {fmt_matching_data.get('model_version', '未知')}。"
            )
        matches = fmt_matching_data.get("top_k_matches", [])
        if matches:
            fmt_rows = []
            for i, m in enumerate(matches, 1):
                score = m.get("score", 0)
                distance = m.get("distance")
                response_rate = m.get("historical_response_rate")
                fmt_rows.append({
                    "rank": str(i),
                    "donor_id": escape_latex(str(m.get("donor_id", "?"))),
                    "score": f"{score:.4f}",
                    "distance": f"{distance:.3f}" if isinstance(distance, (int, float)) else "—",
                    "cases": str(m.get("known_outcome_count", 0)),
                    "response_rate": f"{response_rate:.1%}" if isinstance(response_rate, (int, float)) else "—",
                })
            ctx["fmt_matches"] = fmt_rows
            ctx["fmt_top_k"] = len(matches)
            # 最佳匹配评语
            best = matches[0]
            distance = best.get("distance")
            distance_text = f"{distance:.4f}" if isinstance(distance, (int, float)) else "未提供"
            comment = (
                f"模型在 {fmt_matching_data.get('candidate_count', len(matches))} 个候选供体中将 "
                f"{escape_latex(str(best['donor_id']))} 排在第 1 位；嵌入距离为 {distance_text}。"
                "该结果表示队列内相对排序，不是临床成功概率。"
            )
            ctx["fmt_best_comment"] = comment
            ctx["fmt_patient_interpretation"] = escape_latex(
                "FMT 匹配结果用于筛选候选供体，不代表可以直接进行移植。患者应重点关注相似度最高的候选供体，并等待医学筛查确认。"
            )
    elif fmt_matching_data and fmt_matching_data.get("status") == "degraded":
        ctx["fmt_degraded"] = True
        ctx["fmt_message"] = escape_latex(str(fmt_matching_data.get("message", "")))
        tsne_plot = fmt_matching_data.get("tsne_plot_path") or fmt_matching_data.get("plot_path")
        if tsne_plot:
            ctx["fmt_tsne_plot"] = latex_image_path(str(tsne_plot))
        ctx["fmt_patient_interpretation"] = escape_latex(
            "本次 FMT 配型处于降级状态，说明模型或参考数据未能完整运行；当前结果只能作为流程状态提示，不能用于供体选择。"
        )
    elif fmt_matching_data:
        ctx["fmt_unavailable"] = True
        ctx["fmt_message"] = escape_latex(
            str(fmt_matching_data.get("message") or "配型数据库不可用（可能缺少训练数据或模型环境）。")
        )
        tsne_plot = fmt_matching_data.get("tsne_plot_path") or fmt_matching_data.get("plot_path")
        if tsne_plot:
            ctx["fmt_tsne_plot"] = latex_image_path(str(tsne_plot))
        ctx["fmt_patient_interpretation"] = escape_latex(
            "本次未获得可用 FMT 配型结果，通常与训练数据、模型环境或依赖缺失有关；请在环境修复后重新生成报告。"
        )

    # ── 参考文献 ──
    refs: list[str] = []
    for p in knowledge_data.get("pubmed_results", [])[:8]:
        authors = p.get("authors") or p.get("author") or ""
        title = p.get("title", "")
        journal = p.get("journal", "")
        year = p.get("year", "")
        volume = p.get("volume", "")
        issue = p.get("issue", "")
        pages = p.get("pages", "")
        doi = p.get("doi", "")
        # GB/T 7714 格式: 作者. 题名[J]. 刊名, 出版年, 卷号(期号): 起止页码.
        citation = f"{authors}. {title}[J]. {journal}, {year}"
        if volume:
            citation += f", {volume}"
            if issue:
                citation += f"({issue})"
        if pages:
            citation += f": {pages}"
        if doi:
            citation += f". DOI: {doi}"
        refs.append(escape_latex(citation.strip(" .") + "."))
    for claim in knowledge_data.get("matched_docs", [])[:12]:
        if not isinstance(claim, dict) or not claim.get("claim_id"):
            continue
        confidence = claim.get("confidence")
        confidence_text = (
            f"{confidence:.2f}" if isinstance(confidence, (int, float)) else "未知"
        )
        citation = (
            f"[{claim['claim_id']}] {claim.get('subject', '')} "
            f"--{claim.get('predicate', '')}--> {claim.get('object', '')}. "
            f"证据: {claim.get('evidence_text', '')[:350]} "
            f"来源: {claim.get('filename') or claim.get('source_id', '')}; "
            f"document:{claim.get('document_id', '未知')}; 置信度: {confidence_text}."
        )
        refs.append(escape_latex(citation))
    if refs:
        ctx["references"] = refs
    else:
        ctx["references_empty_message"] = escape_latex("本次分析未检索到外部文献数据。")

    return ctx


# ── 渲染 LaTeX 模板 ──────────────────────────────────────────────────

def render_report_tex(context: dict[str, Any]) -> str:
    """渲染模板, 返回完整的 .tex 文本"""
    env = _get_jinja_env()
    template = env.get_template("report_template.tex")

    # 注入字体配置
    ctx = dict(context)
    ctx.setdefault("cjk_main_font", _CJK_FONT_MAIN)
    ctx.setdefault("cjk_sans_font", _CJK_FONT_SANS)
    ctx.setdefault("font_path", _CJK_FONT_PATH)

    return template.render(**ctx)


# ── 编译 PDF ─────────────────────────────────────────────────────────

def compile_pdf(tex_content: str, output_name: str, output_dir: str | None = None) -> str:
    """
    把 .tex 内容写入临时文件并用 xelatex 编译两次(保证目录/引用正确),
    返回最终 PDF 的绝对路径。如果编译失败, 会打印日志路径供排查。
    """
    if not shutil.which(_LATEX_ENGINE) and not os.path.isfile(_LATEX_ENGINE):
        raise RuntimeError(
            f"未找到 xelatex 命令, 请确认本机已安装 TeX Live,"
            f" 路径: {_LATEX_ENGINE}"
        )

    out_dir = output_dir or _DEFAULT_OUTPUT_DIR
    os.makedirs(out_dir, exist_ok=True)

    build_dir = os.path.join(out_dir, "_build")
    os.makedirs(build_dir, exist_ok=True)

    tex_path = os.path.join(build_dir, f"{output_name}.tex")
    with open(tex_path, "w", encoding="utf-8") as f:
        f.write(tex_content)

    # 编译两次以生成正确的目录
    for i in range(2):
        result = subprocess.run(
            [_LATEX_ENGINE, "-interaction=nonstopmode", "-output-directory", build_dir, tex_path],
            capture_output=True, text=True, timeout=180,
        )
        # 检查是否生成了 PDF（xelatex 可能因为非致命警告返回非零退出码）
        src_pdf = os.path.join(build_dir, f"{output_name}.pdf")
        if os.path.isfile(src_pdf) and os.path.getsize(src_pdf) > 0:
            continue
        if result.returncode != 0 and i == 1:
            log_path = os.path.join(build_dir, f"{output_name}.log")
            stderr_tail = result.stdout[-3000:] if result.stdout else result.stderr[-3000:]
            print(f"[错误] LaTeX编译失败, 详细日志见: {log_path}")
            print(stderr_tail)
            raise RuntimeError("PDF编译失败, 请检查上方日志或 TeX 安装是否完整。")

    src_pdf = os.path.join(build_dir, f"{output_name}.pdf")
    dst_pdf = os.path.join(out_dir, f"{output_name}.pdf")
    if os.path.isfile(src_pdf):
        shutil.copyfile(src_pdf, dst_pdf)
    else:
        raise RuntimeError(f"编译未生成 PDF 文件: {src_pdf}")

    # 清理 aux/log/out/toc 等辅助文件（保留 .tex 供调试）
    for ext in (".aux", ".log", ".out", ".toc"):
        aux_file = os.path.join(build_dir, f"{output_name}{ext}")
        if os.path.isfile(aux_file):
            os.unlink(aux_file)

    return dst_pdf


# ── 一步接口：数据 → PDF ────────────────────────────────────────────

def build_pdf(
    sample_id: str,
    species_data: dict[str, Any],
    compare_data: dict[str, Any],
    enterotype_data: dict[str, Any],
    pathway_data: dict[str, Any],
    metabolite_data: dict[str, Any],
    drug_data: dict[str, Any],
    disease_data: dict[str, Any],
    knowledge_data: dict[str, Any],
    llm_advice: str = "",
    fmt_matching_data: dict[str, Any] | None = None,
    output_dir: str | None = None,
    output_name: str | None = None,
) -> str:
    """
    一步完成: 数据 → 模板上下文 → LaTeX 渲染 → xelatex 编译 → PDF

    返回最终 PDF 的绝对路径。
    """
    # 1. 构建模板上下文
    context = build_context(
        sample_id=sample_id,
        species_data=species_data,
        compare_data=compare_data,
        enterotype_data=enterotype_data,
        pathway_data=pathway_data,
        metabolite_data=metabolite_data,
        drug_data=drug_data,
        disease_data=disease_data,
        knowledge_data=knowledge_data,
        llm_advice=llm_advice,
        fmt_matching_data=fmt_matching_data,
    )

    # 2. 渲染 LaTeX
    tex_content = render_report_tex(context)

    # 3. 编译 PDF
    out_name = output_name or f"{sample_id}_health_report"
    return compile_pdf(tex_content, out_name, output_dir)
