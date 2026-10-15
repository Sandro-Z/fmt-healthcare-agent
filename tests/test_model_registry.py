from pathlib import Path

from wgs_fmt_platform.models.registry import FileModelRegistry, ModelManifest


def _manifest(version: str) -> ModelManifest:
    return ModelManifest(
        name="fmt-ranker",
        task="fmt_donor_ranking",
        version=version,
        artifact_uri=f"file:///models/{version}.bin",
        feature_version="features-v1",
        training_dataset_version="dataset-v1",
        metrics={"ndcg@10": 0.8},
    )


def test_promote_canary_and_rollback(tmp_path: Path) -> None:
    registry = FileModelRegistry(tmp_path)
    registry.register(_manifest("v1"))
    registry.register(_manifest("v2"))
    registry.promote("fmt-ranker", "v1", "production")
    canary = registry.promote(
        "fmt-ranker", "v2", "production", traffic_percent=10, reason="shadow evaluation"
    )
    assert canary.active.model_version == "v1"
    assert canary.candidate and canary.candidate.model_version == "v2"
    promoted = registry.promote("fmt-ranker", "v2", "production", reason="metrics passed")
    assert promoted.active.model_version == "v2"
    rolled_back = registry.rollback("fmt-ranker", "production")
    assert rolled_back.active.model_version == "v1"

