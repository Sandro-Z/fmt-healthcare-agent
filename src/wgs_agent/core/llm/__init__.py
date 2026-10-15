from wgs_agent.core.llm.base import LLMProvider
from wgs_agent.core.llm.types import LlmResponse, ToolCallBlock, UsageStats


def make_provider(provider_name: str, model: str) -> LLMProvider:
    """根据 provider 名称创建对应的 LLM Provider 实例"""
    if provider_name == "deepseek":
        from wgs_agent.core.llm.deepseek_provider import DeepSeekProvider

        return DeepSeekProvider(model)  # type: ignore[return-value]
    elif provider_name == "anthropic":
        from wgs_agent.core.llm.provider import AnthropicProvider

        return AnthropicProvider(model)  # type: ignore[return-value]
    else:
        raise SystemExit(
            f"Unknown LLM provider: {provider_name!r}. Supported: anthropic, deepseek"
        )


__all__ = [
    "AnthropicProvider",
    "LLMProvider",
    "LlmResponse",
    "ToolCallBlock",
    "UsageStats",
    "make_provider",
    ]


def __getattr__(name: str):
    """Keep the optional Anthropic SDK lazy for non-LLM analysis/reporting paths."""
    if name == "AnthropicProvider":
        from wgs_agent.core.llm.provider import AnthropicProvider

        return AnthropicProvider
    raise AttributeError(name)
