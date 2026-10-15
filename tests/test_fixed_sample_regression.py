from pathlib import Path

from wgs_fmt_platform.contracts import AnalysisResult, EvidenceBundle
from wgs_fmt_platform.reporting import ReportService


FIXTURES = Path(__file__).parent / "fixtures"


def test_fixed_sample_report_snapshot() -> None:
    analysis = AnalysisResult.model_validate_json(
        (FIXTURES / "fixed_sample_analysis.json").read_text(encoding="utf-8")
    )
    bundle = EvidenceBundle(analysis=analysis, knowledge_version="kg-fixed-v1")
    actual = ReportService().render(bundle).markdown
    expected = (FIXTURES / "fixed_sample_report.md").read_text(encoding="utf-8")
    assert actual == expected.rstrip() + "\n"
