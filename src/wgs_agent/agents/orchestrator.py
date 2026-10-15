"""WGS.FMT Orchestrator — 基于 AgentRunner + AgentLoop 的宏基因组分析编排器

将 KamaClaude 的 LLM 驱动推理能力应用于 WGS 分析流程：
- AgentLoop 中的 LLM 自主决策工具调用顺序
- 根据中间结果动态调整（如高风险触发深度检索）
- SelfReviewTool 提供每步输出质量审查
- EventBus 推送实时进度
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from wgs_agent.core.config import WgsConfig, get_config
from wgs_agent.core.events.bus import EventBus
from wgs_agent.core.llm import make_provider
from wgs_agent.core.runner import AgentRunner


class WgsOrchestrator:
    """WGS.FMT 分析编排器（AgentRunner 薄包装）

    用法:
        config = get_config()
        orchestrator = WgsOrchestrator(config)
        result = await orchestrator.run("MSYH.TTC")
    """

    def __init__(
        self,
        config: WgsConfig | None = None,
        *,
        bus: EventBus | None = None,
        runs_dir: Path | None = None,
    ):
        self._config = config or get_config()
        self._bus = bus or EventBus()
        self._runs_dir = runs_dir or Path.home() / ".wgs_agent" / "runs"

    async def run(self, sample_id: str) -> dict[str, Any]:
        """委托给 AgentRunner 执行基于 LLM 推理的完整分析流程

        AgentLoop 会引导 LLM 按专家 prompt 自动决策：
        - Plan: 根据目标决定调用哪些工具
        - Act: 执行工具调用
        - Observe: 分析结果，用 self_review 审查，决定下一步
        - 循环直到输出最终报告
        """
        provider = make_provider(
            self._config.llm.provider,
            self._config.llm.default_model,
        )

        runner = AgentRunner(
            config=self._config,
            bus=self._bus,
            provider=provider,
            runs_dir=self._runs_dir,
        )

        goal = (
            f"对肠道菌群样本 {sample_id} 执行完整的宏基因组学分析，"
            f"包括物种丰度、健康参考对比、肠型分类、代谢通路、代谢物含量、"
            f"药物交互和疾病关联分析。"
            f"每个工具调用后使用 self_review 审查输出质量。"
            f"最后生成完整的 Markdown 健康评估报告。"
        )

        outcome = await runner.run_and_capture(goal)

        return {
            "status": outcome.status,
            "result": outcome.result,
            "reason": outcome.reason,
            "sample_id": sample_id,
        }