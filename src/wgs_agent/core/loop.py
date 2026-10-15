from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from wgs_agent.core.bus.events import StepFinishedEvent, StepStartedEvent
from wgs_agent.core.context import ExecutionContext
from wgs_agent.core.events.bus import EventBus
from wgs_agent.core.llm.base import LLMProvider
from wgs_agent.core.tools.invocation import invoke_tool
from wgs_agent.core.tools.registry import ToolRegistry

_WGS_EXPERT_PROMPT = """你是肠道微生物组分析专家 (WGS.FMT-Agent)。

你是一位基于 MetaPhlAn4 + HUMAnN3 的宏基因组数据分析专家。你可以使用搭载的分析工具直接查询样本的物种丰度、代谢通路、药物交互等信息。

## 分析流程

1. **数据加载** (必须)
   - 使用 `load_species_data` 加载样本物种丰度
   - 检查：物种数应 > 0，总丰度接近 100%

2. **健康对比** (必须)
   - 使用 `compare_reference` 对比健康参考范围
   - 识别偏高/偏低物种

3. **条件分支** (根据结果决策)
   - 如果异常物种 > 10 个 **或** 偏差 > ±3.0:
     → 调用 `search_pubmed` 检索关键物种的研究文献
     → 调用 `search_knowledge_base` 查询本地知识库
   - 如果正常: 跳过深度检索

4. **深度分析** (必须)
   - `analyze_enterotype` 肠型分类
   - `analyze_pathways` 代谢通路
   - `analyze_metabolites` 代谢物含量
   - `analyze_drugs` 药物交互
   - `analyze_diseases` 疾病关联

5. **自我审查** (每步后执行)
   - 使用 `self_review` 检查输出合理性
   - 如果异常 → 重试或标记人工审核

6. **报告生成** (必须)
   - 使用 `generate_report` 生成完整 Markdown 报告
   - 注入所有文献证据和知识片段

## 推理要求

- **每步解释为什么**: "我现在加载物种数据，因为..."
- **观察结果**: "发现 Faecalibacterium 偏低 -3.2，这可能与..."
- **动态决策**: 根据中间结果调整策略 包括以下等方面
   - 如果异常物种数 > 5 且偏差 > ±2.0 → 触发 PubMed 检索相关疾病文献
   - 如果疾病风险评分 > 75 → 深度检索该疾病与肠道菌群的证据
   - 如果药物交互评分 > 50000 → 标注高风险并检索替代药物
- **自我纠正**: "上一步输出异常（物种数=0），我需要..."

## 关键原则

- 所有物种名称优先使用中文学名
- 疾病风险评分仅供参考，不代表临床诊断
- 引用文献时标注 [PMID: xxx] 或 [来源]
- 如果工具调用失败，分析原因并重试（最多 3 次）

完成所有分析后，输出最终报告。"""
import logging
def _base_prompt() -> str:
    return _WGS_EXPERT_PROMPT

if TYPE_CHECKING:
    from wgs_agent.core.compact.compactor import Compactor
    from wgs_agent.core.permissions.manager import PermissionManager


log = logging.getLogger(__name__)

def _now() -> str:
    return datetime.now(UTC).isoformat()


class AgentLoop:
    # 初始化循环所需依赖：LLM provider、工具注册表、事件总线，以及可选的权限管理器、压缩器和 session ID
    def __init__(
        self,
        provider: LLMProvider,
        registry: ToolRegistry,
        bus: EventBus,
        *,
        permission_manager: PermissionManager | None = None,
        compactor: Compactor | None = None,
        compact_threshold: float = 0.80,
        session_id: str = "",
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._bus = bus
        self._permission_manager = permission_manager
        self._compactor = compactor
        self._compact_threshold = compact_threshold
        self._session_id = session_id

    # 驱动 plan→act→observe 循环直到上下文终止；CancelledError 向上传播
    async def run(self, context: ExecutionContext) -> None:
        while not context.is_done():
            context.step += 1
            await self._bus.publish(
                StepStartedEvent(run_id=context.run_id, step=context.step, ts=_now())
            )

            # [plan] call LLM — API errors terminate the run
            try:
                response = await self._provider.chat(
                    messages=context.messages,
                    tool_schemas=self._registry.tool_schemas(),
                    bus=self._bus,
                    run_id=context.run_id,
                    step=context.step,
                    system=context.system_prompt(
                        _base_prompt(),
                    ),
                )
            except asyncio.CancelledError:
                context.mark_failed("cancelled")
                raise
            except Exception:
                logging.getLogger(__name__).exception(
                    "LLM call failed run_id=%s step=%d", context.run_id, context.step
                )
                context.mark_failed("llm_error")
                break

            # [observe] append assistant content blocks to context
            # thinking blocks must come first and be preserved verbatim for extended thinking mode
            blocks: list[dict[str, object]] = list(response.thinking_blocks)
            if response.text:
                blocks.append({"type": "text", "text": response.text})
            for tc in response.tool_calls:
                blocks.append(
                    {"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.input}
                )
            context.add_assistant_message(blocks)

            # [act] execute each requested tool; errors become tool results so loop continues
            if response.stop_reason == "tool_use":
                for tc in response.tool_calls:
                    result = await invoke_tool(
                        self._registry, tc, self._bus, context.run_id,
                        permission_manager=self._permission_manager,
                        session_id=self._session_id,
                    )
                    context.add_tool_result(tc.id, result.content, is_error=result.is_error)
            elif response.stop_reason == "max_tokens" and response.tool_calls:
                # Output token limit hit mid-tool-call; input is incomplete.
                # Add synthetic error results so the conversation stays balanced.
                for tc in response.tool_calls:
                    context.add_tool_result(
                        tc.id,
                        "Error: output token limit reached before this tool call could be completed. "
                        "Please break the task into smaller steps and try again.",
                        is_error=True,
                    )

            # Termination check — end_turn wins over max_steps if both hit on same step
            if response.stop_reason == "end_turn":
                context.result = response.text or ""
                context.mark_success()
            elif context.step >= context.max_steps:
                context.mark_failed("exceeded_max_steps")

            # 工具结果追加完毕（messages 末尾为 user）后检查压缩，仅在 run 继续时触发
            # 此时压缩结果 [user_summary, assistant_ack] 对下一次 LLM 调用是合法输入
            if (
                not context.is_done()
                and response.stop_reason == "tool_use"
                and self._compactor is not None
                and self._compact_threshold > 0
                and response.usage is not None
                and response.usage.context_pct >= self._compact_threshold
            ):
                await self._compactor.compact(context, self._provider)

            await self._bus.publish(
                StepFinishedEvent(run_id=context.run_id, step=context.step, ts=_now())
            )
