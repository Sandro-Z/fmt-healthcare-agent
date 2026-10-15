from wgs_fmt_platform.contracts import AnalysisRequest, ReportArtifact, RunStatus
from wgs_fmt_platform.knowledge import KnowledgeService
from wgs_fmt_platform.metagenome import MetagenomeService
from wgs_fmt_platform.models import ModelProvider
from wgs_fmt_platform.reporting import ReportService


class AnalysisWorkflow:
    def __init__(
        self,
        metagenome: MetagenomeService,
        knowledge: KnowledgeService,
        reporting: ReportService,
        model: ModelProvider | None = None,
    ) -> None:
        self.metagenome = metagenome
        self.knowledge = knowledge
        self.reporting = reporting
        self.model = model

    async def run(self, request: AnalysisRequest) -> ReportArtifact:
        analysis = await self.metagenome.analyze(
            request.sample, database_version=request.database_version
        )
        if analysis.status == RunStatus.failed:
            raise RuntimeError("metagenome analysis failed: " + "; ".join(analysis.warnings))
        analysis.request = request
        evidence = await self.knowledge.build_evidence(
            analysis,
            knowledge_version=request.knowledge_version,
            population=request.sample.metadata,
        )
        if self.model is not None:
            analysis.predictions = await self.model.predict(evidence)
        return self.reporting.render(evidence)

