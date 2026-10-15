"""领域工具注册"""

from __future__ import annotations

from typing import Any

def register_domain_tools(
    registry: Any,
    permission_manager: Any | None = None,
) -> None:
    # Keep legacy scientific dependencies optional until the full tool registry is requested.
    from wgs_agent.tools.domain_tools import DOMAIN_TOOLS, DOMAIN_TOOL_POLICIES

    for tool_cls in DOMAIN_TOOLS:
        tool_instance = tool_cls()
        registry.register(tool_cls.name, tool_instance)

    if permission_manager is not None:
        for tool_name, policy_dict in DOMAIN_TOOL_POLICIES.items():
            from wgs_agent.core.permissions.policy import PermissionDecision, ToolPolicy
            default_str = policy_dict.get("default", "ask")
            try:
                default = PermissionDecision(default_str)
            except ValueError:
                default = PermissionDecision.ASK
            permission_manager._policies[tool_name] = ToolPolicy(
                default=default,
            )
