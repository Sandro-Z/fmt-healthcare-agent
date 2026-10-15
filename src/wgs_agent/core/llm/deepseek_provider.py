from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

import httpx
from openai import AsyncOpenAI

from wgs_agent.core.bus.events import LlmModelSelectedEvent, LlmTokenEvent, LlmUsageEvent
from wgs_agent.core.events.bus import EventBus
from wgs_agent.core.llm.types import LlmResponse, ToolCallBlock, UsageStats

_MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    "deepseek-chat": 128_000,
    "deepseek-reasoner": 128_000,
    "deepseek-v3": 128_000,
    "deepseek-v4": 128_000,
    "deepseek": 128_000,
}

_MAX_STREAM_RETRIES = 3
_RETRY_BACKOFF_S = (1.0, 2.0, 4.0)

log = logging.getLogger(__name__)


def _context_window(model: str) -> int:
    for key, val in _MODEL_CONTEXT_WINDOWS.items():
        if model.startswith(key):
            return val
    return 65536


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _to_openai_messages(
    messages: list[dict[str, object]],
) -> list[dict[str, object]]:
    """将 Anthropic 格式的 messages 转换为 OpenAI 兼容格式"""
    result: list[dict[str, object]] = []
    for msg in messages:
        role = msg["role"]
        content = msg["content"]

        if role == "user":
            if isinstance(content, list):
                # user content blocks → 提取文本或 tool_result
                text_parts: list[str] = []
                for block in content:
                    if isinstance(block, dict):
                        block_type = block.get("type")
                        if block_type == "tool_result":
                            # tool_result → OpenAI "tool" role
                            result.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": str(block.get("tool_use_id", "")),
                                    "content": str(block.get("content", "")),
                                }
                            )
                        elif block_type == "text":
                            text_parts.append(str(block.get("text", "")))
                if text_parts:
                    result.append({"role": "user", "content": "\n".join(text_parts)})
            elif isinstance(content, str):
                result.append({"role": "user", "content": content})
            else:
                result.append({"role": "user", "content": str(content)})

        elif role == "assistant":
            text_parts: list[str] = []
            tool_calls: list[dict[str, object]] = []
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        block_type = block.get("type")
                        if block_type == "text":
                            text_parts.append(str(block.get("text", "")))
                        elif block_type == "tool_use":
                            tool_input = block.get("input", {})
                            tool_calls.append(
                                {
                                    "id": str(block.get("id", "")),
                                    "type": "function",
                                    "function": {
                                        "name": str(block.get("name", "")),
                                        "arguments": json.dumps(tool_input, ensure_ascii=False),
                                    },
                                }
                            )
                        # thinking blocks are skipped in OpenAI format
            elif isinstance(content, str):
                text_parts.append(content)

            assistant_msg: dict[str, object] = {
                "role": "assistant",
                "content": "\n".join(text_parts) if text_parts else None,
            }
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            result.append(assistant_msg)

    return result


def _to_openai_tools(
    tool_schemas: list[dict[str, object]],
) -> list[dict[str, object]]:
    """将 Anthropic 格式的 tool schemas 转换为 OpenAI 兼容格式"""
    result: list[dict[str, object]] = []
    for schema in tool_schemas:
        result.append(
            {
                "type": "function",
                "function": {
                    "name": schema.get("name", ""),
                    "description": schema.get("description", ""),
                    "parameters": schema.get("input_schema", {"type": "object", "properties": {}}),
                },
            }
        )
    return result


class DeepSeekProvider:
    """使用 OpenAI 兼容 SDK 连接 DeepSeek API 的 LLM Provider"""

    def __init__(self, model: str, client: Any = None) -> None:
        if client is None:
            api_key = os.environ.get("DEEPSEEK_API_KEY")
            if not api_key:
                raise SystemExit("DEEPSEEK_API_KEY not set")
            base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
            self._client: Any = AsyncOpenAI(api_key=api_key, base_url=base_url)
        else:
            self._client = client
        self._model = model

    async def chat(
        self,
        messages: list[dict[str, object]],
        tool_schemas: list[dict[str, object]],
        bus: EventBus,
        run_id: str,
        *,
        step: int = 0,
        system: str | None = None,
    ) -> LlmResponse:
        await bus.publish(
            LlmModelSelectedEvent(
                run_id=run_id, model=self._model, strategy="static", ts=_now()
            )
        )

        openai_messages = _to_openai_messages(messages)
        openai_tools = _to_openai_tools(tool_schemas)

        kwargs: dict[str, object] = {
            "model": self._model,
            "messages": openai_messages,
            "max_tokens": 8192,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if system:
            kwargs["messages"] = [{"role": "system", "content": system}] + openai_messages  # type: ignore[list-item]
        if openai_tools:
            kwargs["tools"] = openai_tools

        text_parts: list[str] = []
        tool_calls_map: dict[int, dict[str, object]] = {}
        final_usage: UsageStats | None = None
        finish_reason: str = "stop"

        for attempt in range(1, _MAX_STREAM_RETRIES + 1):
            text_parts = []
            tool_calls_map = {}
            final_usage = None
            try:
                stream = await self._client.chat.completions.create(**kwargs)  # type: ignore[arg-type]
                async for chunk in stream:
                    choices = getattr(chunk, "choices", None)
                    if choices and len(choices) > 0:
                        delta = getattr(choices[0], "delta", None)
                        if delta:
                            # text token
                            content = getattr(delta, "content", None)
                            if content and attempt == 1:
                                await bus.publish(
                                    LlmTokenEvent(run_id=run_id, token=content, ts=_now())
                                )
                                text_parts.append(content)

                            # tool call delta
                            tool_calls_delta = getattr(delta, "tool_calls", None)
                            if tool_calls_delta:
                                for tc_delta in tool_calls_delta:
                                    idx = getattr(tc_delta, "index", 0)
                                    if idx not in tool_calls_map:
                                        tool_calls_map[idx] = {
                                            "id": "",
                                            "name": "",
                                            "arguments": "",
                                        }
                                    tc_id = getattr(tc_delta, "id", None)
                                    if tc_id:
                                        tool_calls_map[idx]["id"] = tc_id
                                    func = getattr(tc_delta, "function", None)
                                    if func:
                                        name = getattr(func, "name", None)
                                        if name:
                                            tool_calls_map[idx]["name"] = name
                                        args = getattr(func, "arguments", None)
                                        if args:
                                            tool_calls_map[idx]["arguments"] += args

                            finish = getattr(choices[0], "finish_reason", None)
                            if finish:
                                finish_reason = finish

                    # usage stats (OpenAI 流式最后 chunk 携带 usage)
                    usage_chunk = getattr(chunk, "usage", None)
                    if usage_chunk:
                        prompt_tokens = getattr(usage_chunk, "prompt_tokens", 0) or 0
                        completion_tokens = getattr(usage_chunk, "completion_tokens", 0) or 0
                        context_pct = prompt_tokens / _context_window(self._model)
                        final_usage = UsageStats(
                            input_tokens=prompt_tokens,
                            output_tokens=completion_tokens,
                            context_pct=context_pct,
                        )

                break  # success
            except (httpx.RemoteProtocolError, httpx.ReadError, httpx.ConnectError) as exc:
                if attempt == _MAX_STREAM_RETRIES:
                    log.error(
                        "stream failed after %d attempts run_id=%s step=%d: %s",
                        _MAX_STREAM_RETRIES, run_id, step, exc,
                    )
                    raise
                delay = _RETRY_BACKOFF_S[attempt - 1]
                log.warning(
                    "stream dropped (attempt %d/%d) run_id=%s step=%d: %s — retrying in %.0fs",
                    attempt, _MAX_STREAM_RETRIES, run_id, step, exc, delay,
                )
                await asyncio.sleep(delay)

        # 如果没有获得 usage（某些 provider 可能不返回流式 usage），提供默认值
        if final_usage is None:
            final_usage = UsageStats(input_tokens=0, output_tokens=0, context_pct=0.0)

        await bus.publish(
            LlmUsageEvent(
                run_id=run_id,
                input_tokens=final_usage.input_tokens,
                output_tokens=final_usage.output_tokens,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
                context_pct=final_usage.context_pct,
                ts=_now(),
            )
        )

        # 将收集的 tool_calls 转换为 ToolCallBlock 列表
        tool_calls: list[ToolCallBlock] = []
        for idx in sorted(tool_calls_map.keys()):
            tc_data = tool_calls_map[idx]
            try:
                tool_input = json.loads(tc_data["arguments"]) if tc_data["arguments"] else {}
            except json.JSONDecodeError:
                tool_input = {}
            tool_calls.append(
                ToolCallBlock(
                    id=tc_data["id"],
                    name=tc_data["name"],
                    input=tool_input,
                )
            )

        # 将 finish_reason 映射为 Anthropic 风格的 stop_reason
        stop_reason_map: dict[str, str] = {
            "stop": "end_turn",
            "tool_calls": "tool_use",
            "length": "max_tokens",
            "content_filter": "end_turn",
        }
        stop_reason = stop_reason_map.get(finish_reason, "end_turn")

        return LlmResponse(
            stop_reason=stop_reason,
            tool_calls=tool_calls,
            text="".join(text_parts),
            usage=final_usage,
        )