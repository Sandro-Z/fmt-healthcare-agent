from wgs_fmt_platform.contracts import (
    EvidenceBundle,
    ReportStatement,
    StructuredReport,
    VersionRef,
    VersionSet,
)


class StructuredReportBuilder:
    def __init__(self, feature_schema_version: str, template_version: str) -> None:
        self.feature_schema_version = feature_schema_version
        self.template_version = template_version

    def build(self, bundle: EvidenceBundle) -> StructuredReport:
        analysis = bundle.analysis
        request = analysis.request
        statements: list[ReportStatement] = []

        for feature in analysis.features[:50]:
            statements.append(
                ReportStatement(
                    section="特征摘要",
                    text=(
                        f"{feature.feature_name}: {feature.value:g} "
                        f"{feature.unit}，状态为 {feature.status}。"
                    ),
                    feature_ids=[feature.feature_id],
                )
            )

        for claim in bundle.claims[:30]:
            filename = claim.qualifiers.get("filename", "")
            source = filename or claim.evidence.source_id
            evidence = f" 证据原句：{claim.evidence.sentence}" if claim.evidence.sentence else ""
            statements.append(
                ReportStatement(
                    section="知识证据",
                    text=(
                        f"[{claim.claim_id}] {claim.subject.name} {claim.predicate} "
                        f"{claim.object.name}。来源：{source}；{claim.evidence.source_id}。{evidence}"
                    ),
                    claim_ids=[claim.claim_id],
                )
            )

        for prediction in analysis.predictions:
            statements.append(
                ReportStatement(
                    section="模型结果",
                    text=(
                        f"任务 {prediction.task} 的模型输出为 {prediction.value}，"
                        f"置信度 {prediction.confidence if prediction.confidence is not None else '未校准'}。"
                    ),
                    prediction_tasks=[prediction.task],
                )
            )

        statements.append(
            ReportStatement(
                section="声明",
                text="本报告用于科研与健康管理参考，不构成临床诊断。",
                is_disclaimer=True,
            )
        )
        versions = VersionSet(
            database=VersionRef(kind="database", name=request.database_id, version=request.database_version),
            knowledge=VersionRef(kind="knowledge", name="claim-gateway", version=bundle.knowledge_version),
            features=VersionRef(kind="features", name="wgs-features", version=self.feature_schema_version),
            model=VersionRef(kind="model", name="analysis-model", version=request.model_version),
            report_template=VersionRef(
                kind="report_template", name="health-report", version=self.template_version
            ),
        )
        return StructuredReport(
            sample_id=request.sample.sample_id,
            title="WGS.FMT 分析报告",
            versions=versions,
            statements=statements,
        )
