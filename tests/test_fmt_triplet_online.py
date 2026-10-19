from pathlib import Path
import json

import numpy as np
import pandas as pd

from wgs_agent.pipeline import report_fmt_matching as matching
from wgs_agent.pipeline.report_fmt_matching import run_fmt_pipeline
from wgs_agent.tools.report_maker import build_full_report


def test_triplet_pipeline_returns_ranked_donors(tmp_path: Path, monkeypatch):
    # Keep the online contract test independent of discarded research data/models.
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    features = ["s__A", "s__B", "s__C"]
    (model_dir / "feature_schema.json").write_text(json.dumps({"features": features}))
    np.savez(
        model_dir / "fmt_triplet_contrastive_model.npz",
        projection=np.eye(3, 2),
        scaler_mean=np.zeros(3),
        scaler_scale=np.ones(3),
        classifier_coef=np.zeros((1, 6)),
        classifier_intercept=np.zeros(1),
    )
    baseline = tmp_path / "baseline.csv"
    pd.DataFrame(
        [[30, 30, 40], [30, 30, 40], [10, 30, 60], [70, 10, 20], [20, 60, 20]],
        index=["QUERY", "D1", "D2", "D3", "D4"],
        columns=features,
    ).to_csv(baseline)
    metadata = tmp_path / "match.xlsx"
    pd.DataFrame(
        {
            "sample_id": ["QUERY", "D1", "D2", "D3", "D4"],
            "group": ["recipient", "donor", "donor", "donor", "donor"],
            "donor": ["D1", "", "", "", ""],
            "label": ["Res", "", "", "", ""],
        }
    ).to_excel(metadata, index=False)
    monkeypatch.setattr(matching, "TRIPLET_MODEL_DIR", model_dir)
    monkeypatch.setattr(matching, "TRIPLET_BASELINE_SPECIES", baseline)
    monkeypatch.setattr(matching, "TRIPLET_MATCH_FILE", metadata)
    result = run_fmt_pipeline(
        sample_id="QUERY",
        genus_file="",
        output_dir=str(tmp_path),
        top_k=3,
        device_str="cpu",
    )
    assert result["status"] == "ok"
    assert result["model_name"] == "fmt-triplet-contrastive"
    assert result["model_version"] == "1.0.0"
    assert result["candidate_count"] == 4
    assert len(result["top_k_matches"]) == 3
    assert [row["rank"] for row in result["top_k_matches"]] == [1, 2, 3]
    assert all(row["distance"] >= 0 for row in result["top_k_matches"])
    assert result["top_k_matches"][0]["donor_id"] == "D1"
    assert result["top_k_matches"][0]["distance"] == 0
    assert result["feature_audit"]["feature_name_coverage"] == 1.0
    assert Path(result["tsne_plot_path"]).is_file()


def test_fresh_runtime_reports_missing_model(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(matching, "TRIPLET_MODEL_DIR", tmp_path / "missing-model")
    monkeypatch.setattr(matching, "_FMT_MATCHING_DIR", str(tmp_path / "missing-legacy"))
    result = run_fmt_pipeline("NEW_SAMPLE", "", str(tmp_path / "results"))
    assert result["status"] == "unavailable"
    assert result["top_k_matches"] == []
    assert not (tmp_path / "results").exists()


def test_markdown_report_contains_triplet_fields():
    fmt = {
        "status": "ok",
        "message": "完成候选供体排序",
        "candidate_count": 51,
        "model_version": "1.0.0",
        "feature_audit": {"feature_name_coverage": 1.0, "abundance_coverage": 0.72},
        "top_k_matches": [
            {
                "donor_id": "D001",
                "score": 0.82,
                "distance": 2.3,
                "known_outcome_count": 4,
                "historical_response_rate": 0.75,
            }
        ],
    }
    report = build_full_report(
        sample_id="S001",
        species_data={},
        compare_data={},
        enterotype_data={},
        pathway_data={},
        metabolite_data={},
        drug_data={},
        disease_data={},
        knowledge_data={},
        llm_advice="",
        fmt_matching_data=fmt,
    )
    assert "嵌入距离" in report
    assert "历史响应率" in report
    assert "不是临床成功概率" in report
