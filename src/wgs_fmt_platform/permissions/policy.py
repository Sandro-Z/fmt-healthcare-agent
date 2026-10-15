from enum import StrEnum

from pydantic import BaseModel


class ActionDecision(StrEnum):
    allow = "allow"
    require_approval = "require_approval"
    deny = "deny"


class PolicyResult(BaseModel):
    action: str
    decision: ActionDecision
    reason: str


class PermissionPolicy:
    """Central policy shared by API, CLI, Web, and future TUI clients."""

    rules: dict[str, tuple[ActionDecision, str]] = {
        "analysis.read": (ActionDecision.allow, "read-only analysis access"),
        "knowledge.search": (ActionDecision.allow, "read-only evidence retrieval"),
        "report.generate": (ActionDecision.allow, "versioned report artifact generation"),
        "pipeline.run": (
            ActionDecision.require_approval,
            "may consume substantial compute and write artifacts",
        ),
        "database.initialize": (
            ActionDecision.require_approval,
            "creates a new reference database",
        ),
        "database.update": (
            ActionDecision.require_approval,
            "publishes a new database snapshot",
        ),
        "model.register": (
            ActionDecision.require_approval,
            "changes the model registry",
        ),
        "model.promote": (
            ActionDecision.require_approval,
            "changes production traffic allocation",
        ),
        "model.rollback": (
            ActionDecision.require_approval,
            "changes the active production model",
        ),
    }

    def evaluate(self, action: str) -> PolicyResult:
        decision, reason = self.rules.get(
            action,
            (ActionDecision.deny, "unknown actions are denied by default"),
        )
        return PolicyResult(action=action, decision=decision, reason=reason)

