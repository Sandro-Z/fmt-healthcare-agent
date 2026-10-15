from pathlib import Path

from wgs_fmt_platform.contracts import (
    AnalysisRequest,
    AnalysisResult,
    EvidenceBundle,
    FeatureObservation,
    Provenance,
    RunStatus,
    SampleManifest,
)
from wgs_fmt_platform.reporting import ReportService


def test_report_has_versions_and_passes_fact_check() -> None:
    request = AnalysisRequest(
        sample=SampleManifest(sample_id="S001", read1=Path("reads.fastq.gz")),
        database_version="db-v2",
        knowledge_version="kg-v3",
        model_version="model-v4",
    )
    analysis = AnalysisResult(
        request=request,
        status=RunStatus.succeeded,
        features=[
            FeatureObservation(
                feature_id="NCBITaxon:1",
                feature_name="Microbe A",
                feature_type="microbe",
                value=1.2,
                unit="percent",
                status="high",
                provenance=Provenance(source="pipeline", source_version="db-v2"),
            )
        ],
    )
    bundle = EvidenceBundle(analysis=analysis, knowledge_version="kg-v3")
    report = ReportService().render(bundle)
    assert "数据库版本：db-v2" in report.markdown
    assert "Microbe A: 1.2 percent" in report.markdown

