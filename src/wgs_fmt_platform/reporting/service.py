from wgs_fmt_platform.contracts import EvidenceBundle, ReportArtifact
from wgs_fmt_platform.reporting.fact_check import ReportFactChecker
from wgs_fmt_platform.reporting.renderer import MarkdownRenderer
from wgs_fmt_platform.reporting.structured import StructuredReportBuilder


class ReportService:
    """Structured generation -> fact check -> deterministic rendering."""

    def __init__(
        self,
        feature_schema_version: str = "feature-schema-v1",
        template_version: str = "report-template-v1",
    ) -> None:
        self.builder = StructuredReportBuilder(feature_schema_version, template_version)
        self.checker = ReportFactChecker()
        self.renderer = MarkdownRenderer()
        self.template_version = template_version

    def render(self, bundle: EvidenceBundle) -> ReportArtifact:
        report = self.builder.build(bundle)
        check = self.checker.check(report, bundle)
        if not check.passed:
            details = "; ".join(f"{item.code}: {item.message}" for item in check.issues)
            raise ValueError(f"report fact check failed: {details}")
        return ReportArtifact(
            sample_id=report.sample_id,
            template_version=self.template_version,
            evidence_bundle_id=bundle.bundle_id,
            markdown=self.renderer.render(report),
        )

