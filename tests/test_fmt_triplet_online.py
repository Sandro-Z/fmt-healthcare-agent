from pathlib import Path

from wgs_agent.pipeline.report_fmt_matching import run_fmt_pipeline
from wgs_agent.tools.report_maker import build_full_report


def test_triplet_pipeline_returns_ranked_donors(tmp_path: Path):
    result = run_fmt_pipeline(
        sample_id="ERR1297681",
        genus_file="",
        output_dir=str(tmp_path),
        top_k=3,
        device_str="cpu",
    )
    assert result["status"] == "ok"
    assert result["model_name"] == "fmt-triplet-contrastive"
    assert result["model_version"] == "1.0.0"
    assert result["candidate_count"] == 51
    assert len(result["top_k_matches"]) == 3
    assert [row["rank"] for row in result["top_k_matches"]] == [1, 2, 3]
    assert all(row["distance"] >= 0 for row in result["top_k_matches"])
    assert result["feature_audit"]["feature_name_coverage"] == 1.0
    assert Path(result["tsne_plot_path"]).is_file()


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
        species_data={}, compare_data={}, enterotype_data={}, pathway_data={},
        metabolite_data={}, drug_data={}, disease_data={}, knowledge_data={},
        llm_advice="", fmt_matching_data=fmt,
    )
    assert "嵌入距离" in report
    assert "历史响应率" in report
    assert "不是临床成功概率" in report
