from wgs_fmt_platform.permissions import ActionDecision, PermissionPolicy


def test_unknown_permission_is_denied() -> None:
    result = PermissionPolicy().evaluate("unknown.action")
    assert result.decision == ActionDecision.deny


def test_pipeline_requires_approval() -> None:
    result = PermissionPolicy().evaluate("pipeline.run")
    assert result.decision == ActionDecision.require_approval

