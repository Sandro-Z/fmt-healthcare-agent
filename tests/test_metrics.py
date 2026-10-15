import pytest

from wgs_fmt_platform.evaluation import binary_metrics, mrr, ndcg_at_k, recall_at_k


def test_ranking_metrics() -> None:
    ranked = ["D1", "D2", "D3"]
    relevant = {"D2", "D4"}
    assert recall_at_k(ranked, relevant, 2) == 0.5
    assert mrr([ranked], [relevant]) == 0.5
    assert ndcg_at_k(ranked, relevant, 3) == pytest.approx(0.3868528072)


def test_binary_metrics_include_calibration() -> None:
    result = binary_metrics([0, 0, 1, 1], [0.1, 0.4, 0.8, 0.9])
    assert result["accuracy"] == 1.0
    assert result["brier"] == pytest.approx(0.055)
    assert 0 <= result["ece"] <= 1
