from __future__ import annotations

import os
from collections.abc import Iterator

import httpx
from openai import OpenAI

DEFAULT_BASE_URL = "http://127.0.0.1:11434/v1"


class LocalChatError(RuntimeError):
    pass


def base_url() -> str:
    return os.environ.get("WGS_LOCAL_LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _api_key() -> str:
    return os.environ.get("WGS_LOCAL_LLM_API_KEY", "local-no-key-required")


def list_models(timeout_s: float = 8.0) -> list[str]:
    try:
        response = httpx.get(f"{base_url()}/models", timeout=timeout_s)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise LocalChatError(f"无法连接本地模型服务 {base_url()}。请确认当前服务器上的模型服务已启动。") from exc
    models = [str(item.get("id")) for item in payload.get("data", []) if isinstance(item, dict) and item.get("id")]
    if not models:
        raise LocalChatError("模型服务已响应，但 /models 未返回可用模型。")
    return models


def stream_chat(*, model: str, messages: list[dict[str, str]], temperature: float = 0.2) -> Iterator[str]:
    client = OpenAI(api_key=_api_key(), base_url=base_url(), timeout=120.0)
    try:
        stream = client.chat.completions.create(model=model, messages=messages, temperature=temperature, stream=True)
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    except Exception as exc:
        raise LocalChatError(f"本地模型调用失败：{exc}") from exc
