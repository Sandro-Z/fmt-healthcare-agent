"""FMT 配型预测工具 — 为样本匹配 Top-K 候选供体"""

from __future__ import annotations

import json
import os
from typing import Any

from pydantic import BaseModel, Field

from wgs_agent.core.tools.base import BaseTool, ToolResult
from wgs_fmt_platform.paths import runtime_path

JSON_KEY = "---JSON---"


def _make_result(text: str, data: dict[str, Any]) -> ToolResult:
    return ToolResult(content=f"{text}\n{JSON_KEY}\n{json.dumps(data, ensure_ascii=False, default=str)}")


class FmtMatchingParams(BaseModel):
    sample_id: str = Field(..., description="样本 ID（受体）")
    genus_file: str = Field("", description="属水平丰度文件路径，留空则使用默认路径")
    top_k: int = Field(10, description="返回 Top-K 候选供体数量")
    force_retrain: bool = Field(False, description="是否强制重新训练模型")


class FmtMatchingTool(BaseTool):
    name = "fmt_matching"
    description = "FMT 配型预测：基于对比学习模型为样本匹配 Top-K 候选供体，返回匹配评分和 t-SNE 图。"
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "sample_id": {"type": "string", "description": "样本 ID（受体）"},
            "genus_file": {"type": "string", "description": "属水平丰度文件路径，可选"},
            "top_k": {"type": "integer", "description": "返回 Top-K 候选供体数量，默认 10"},
            "force_retrain": {"type": "boolean", "description": "是否强制重新训练模型，默认 false"},
        },
        "required": ["sample_id"],
    }
    params_model = FmtMatchingParams

    async def invoke(self, params: dict[str, object]) -> ToolResult:
        try:
            sid = str(params["sample_id"])
            genus_file = str(params.get("genus_file", ""))
            top_k = int(params.get("top_k", 10))
            force_retrain = bool(params.get("force_retrain", False))

            # 如果未指定 genus_file，使用默认路径
            if not genus_file:
                from wgs_agent.pipeline.report_common import METAPHLAN_GENUS_FILE
                genus_file = METAPHLAN_GENUS_FILE

            if not os.path.exists(genus_file):
                return ToolResult(
                    content=f"属水平丰度文件不存在: {genus_file}",
                    is_error=True,
                    error_type="runtime_error",
                )

            # 输出目录
            out_dir = str(runtime_path("WGS_RESULTS_DIR", "results"))

            # 如果强制重训，删除模型缓存
            if force_retrain:
                from wgs_agent.pipeline.report_fmt_matching import MODEL_CACHE
                if os.path.exists(MODEL_CACHE):
                    os.remove(MODEL_CACHE)
                    print("[FMT] 已删除模型缓存，将重新训练")

            # 调用配型 pipeline
            from wgs_agent.pipeline.report_fmt_matching import run_fmt_pipeline

            result = run_fmt_pipeline(
                sample_id=sid,
                genus_file=genus_file,
                output_dir=out_dir,
                top_k=top_k,
                device_str="cpu",
            )

            status = result.get("status", "unavailable")
            message = result.get("message", "")
            top_matches = result.get("top_k_matches", [])
            tsne_path = result.get("tsne_plot_path")

            if status == "ok":
                # 构建可读摘要
                match_lines = []
                for i, m in enumerate(top_matches, 1):
                    match_lines.append(
                        f"  #{i} {m['donor_id']}: score={m['score']:.4f}, "
                        f"distance={m.get('distance', 0):.4f} "
                        f"[历史响应率={m.get('historical_response_rate', 'NA')}]"
                    )

                text = (
                    f"FMT 配型完成 — 样本 {sid}\n"
                    f"状态: 成功 | {message}\n"
                    f"Top {len(top_matches)} 候选供体:\n"
                    + "\n".join(match_lines[:10])
                    + (f"\nt-SNE 图: {tsne_path}" if tsne_path else "")
                )

                return _make_result(
                    text,
                    {
                        "sample_id": sid,
                        "status": status,
                        "message": message,
                        "top_k_matches": top_matches,
                        "tsne_plot_path": tsne_path,
                        "n_matches": len(top_matches),
                        "model_name": result.get("model_name"),
                        "model_version": result.get("model_version"),
                        "method": result.get("method"),
                        "feature_audit": result.get("feature_audit", {}),
                        "candidate_count": result.get("candidate_count", 0),
                        "query_source": result.get("query_source"),
                        "plot_method": result.get("plot_method"),
                        "warnings": result.get("warnings", []),
                    },
                )

            elif status == "degraded":
                text = f"FMT 配型降级 — 样本 {sid}\n状态: 降级 | {message}"
                return _make_result(
                    text,
                    {
                        "sample_id": sid,
                        "status": status,
                        "message": message,
                        "top_k_matches": [],
                        "tsne_plot_path": None,
                        "n_matches": 0,
                    },
                )

            else:  # unavailable
                text = f"FMT 配型不可用 — 样本 {sid}\n状态: 不可用 | {message}"
                return ToolResult(
                    content=text,
                    is_error=False,
                )

        except Exception as exc:
            import traceback
            return ToolResult(
                content=f"FMT 配型分析失败: {exc}\n{traceback.format_exc()}",
                is_error=True,
                error_type="runtime_error",
            )
