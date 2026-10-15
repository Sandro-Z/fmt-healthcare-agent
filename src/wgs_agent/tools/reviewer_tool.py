"""SelfReviewTool — 让 LLM 在每步分析后自我审查输出质量"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from wgs_agent.core.tools.base import BaseTool, ToolResult


class ReviewParams(BaseModel):
    tool_name: str = Field(..., description="被审查的工具名称")
    output_summary: str = Field(..., description="工具输出的前 500 字符摘要")


class SelfReviewTool(BaseTool):
    name = "self_review"
    description = (
        "审查上一步工具输出的合理性。返回 pass/retry/alert。"
        "应在每次工具调用后使用此工具检查输出质量，"
        "如果返回 retry 或 alert，请根据建议采取行动。"
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "tool_name": {
                "type": "string",
                "description": "被审查的工具名称，如 load_species_data",
            },
            "output_summary": {
                "type": "string",
                "description": "工具输出的前 500 字符（用于规则检查）",
            },
        },
        "required": ["tool_name", "output_summary"],
    }
    params_model = ReviewParams

    async def invoke(self, params: dict[str, object]) -> ToolResult:
        tool = str(params.get("tool_name", ""))
        output = str(params.get("output_summary", ""))

        issues: list[str] = []
        severity: str = "pass"

        # ── 规则 1: 物种数据完整性 ──
        if any(kw in tool for kw in ("load_species", "compare_reference")):
            has_species = bool(re.search(r"(物种数|检测物种|n_total)\D*(\d+)", output))
            n_total = 0
            m = re.search(r"n_total\D*(\d+)", output) or re.search(r"检测\D*(\d+)", output) or re.search(r"物种数\D*(\d+)", output)
            if m:
                n_total = int(m.group(1))

            if not has_species or n_total == 0:
                issues.append("物种数为 0 — 可能样本 ID 错误或 MetaPhlAn 数据缺失")
                severity = "alert"

            # 检查丰度范围
            abundances = re.findall(r"(\d+\.\d+)\s*%", output)
            if abundances:
                abnormal = [a for a in abundances if float(a) > 100 or float(a) < 0]
                if abnormal:
                    issues.append(f"丰度值异常: {', '.join(abnormal[:3])}% (应在 0-100% 范围)")
                    severity = "retry" if severity == "pass" else severity

        # ── 规则 2: 肠型分析合理性 ──
        if "enterotype" in tool:
            has_type = bool(re.search(r"肠型[：:]\s*(Bacteroides|Prevotella|Ruminococcus|未知)", output))
            if not has_type:
                issues.append("未检测到有效肠型分类")
                severity = "retry" if severity == "pass" else severity

        # ── 规则 3: 疾病评分范围 ──
        if "disease" in tool or "analyze_diseases" in tool:
            scores = re.findall(r"(?:风险)?评分[：:\s]*(\d+)", output)
            scores_alt = re.findall(r"risk_score\D*(\d+)", output)
            all_scores = [int(s) for s in (scores + scores_alt) if 0 <= int(s) <= 100]

            if all_scores:
                high = [s for s in all_scores if s > 100]
                if high:
                    issues.append(f"疾病评分超出 0-100 范围: {high[:3]}")
                    severity = "alert"

        # ── 规则 4: 药物分析完整性 ──
        if "drug" in tool:
            has_drugs = bool(re.search(r"(药物|分析药物数|n_total)\D*(\d+)", output))
            if not has_drugs:
                issues.append("药物分析无结果")
                severity = "alert" if severity == "pass" else severity

        # ── 规则 5: 代谢通路/代谢物 — 允许为空但警告 ──
        if "pathway" in tool or "metabolite" in tool:
            if "无" in output or "0 条" in output or "0 种" in output:
                issues.append("代谢数据为空 — 可能 HUMAnN 尚未运行")
            elif not re.search(r"(通路|代谢物|pathway|metabolite)", output, re.IGNORECASE):
                issues.append("代谢数据输出格式异常")
                severity = "retry" if severity == "pass" else severity

        # ── 规则 6: 知识库/PubMed 结果质量 ──
        if any(kw in tool for kw in ("knowledge", "pubmed", "literature")):
            if "未找到" in output or "0 结果" in output:
                issues.append("文献检索返回空")
                severity = "retry" if severity == "pass" else severity

        # ── 汇总输出 ──
        if issues and severity != "pass":
            action_map = {"retry": "建议重试", "alert": "需要人工审核"}
            summary = (
                f"[self_review] 审查 {tool}: {severity.upper()}\n"
                + "\n".join(f"  - {i}" for i in issues)
                + f"\n建议: {action_map.get(severity, '')}"
            )
            return ToolResult(content=summary, is_error=(severity == "alert"))

        return ToolResult(content=f"[self_review] 审查 {tool}: PASS — 输出合理，继续执行")