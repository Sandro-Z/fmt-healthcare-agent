from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class RunStatus(StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    degraded = "degraded"


class VersionRef(BaseModel):
    """Immutable identifier for any versioned platform asset."""

    kind: str
    name: str
    version: str
    digest: str | None = None


class VersionSet(BaseModel):
    database: VersionRef
    knowledge: VersionRef
    features: VersionRef
    model: VersionRef
    report_template: VersionRef


class Provenance(BaseModel):
    source: str
    source_version: str
    created_at: datetime = Field(default_factory=utc_now)
    parameters: dict[str, Any] = Field(default_factory=dict)


class SampleManifest(BaseModel):
    sample_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_.-]+$")
    read1: Path
    read2: Path | None = None
    patient_id: str | None = None
    sample_type: str = "feces"
    metadata: dict[str, Any] = Field(default_factory=dict)


class AnalysisRequest(BaseModel):
    sample: SampleManifest
    database_id: str = "human-gut-db"
    database_version: str = "current"
    knowledge_version: str = "current"
    model_version: str = "baseline-v1"


class FeatureObservation(BaseModel):
    feature_id: str
    feature_name: str
    feature_type: str
    value: float
    unit: str
    status: str = "unknown"
    deviation_score: float | None = None
    provenance: Provenance


class FeatureSet(BaseModel):
    feature_set_id: str = Field(default_factory=lambda: f"features-{uuid4().hex}")
    sample_id: str
    schema_version: str
    observations: list[FeatureObservation] = Field(default_factory=list)
    provenance: Provenance


class ClaimEntity(BaseModel):
    id: str
    name: str
    type: str


class ClaimEvidence(BaseModel):
    source_type: str
    source_id: str
    sentence: str = ""
    evidence_level: str = "unknown"


class KnowledgeClaim(BaseModel):
    claim_id: str
    subject: ClaimEntity
    predicate: str
    object: ClaimEntity
    qualifiers: dict[str, Any] = Field(default_factory=dict)
    evidence: ClaimEvidence
    parser_score: float | None = Field(default=None, ge=0, le=1)
    entity_resolution_score: float | None = Field(default=None, ge=0, le=1)
    review_status: str = "machine_extracted"
    provenance: Provenance


class KnowledgeEvidence(BaseModel):
    evidence_id: str = Field(default_factory=lambda: f"knowledge-{uuid4().hex}")
    claim: KnowledgeClaim
    retrieval_score: float = Field(default=0.0, ge=0)
    rank: int = Field(default=0, ge=0)
    matched_feature_ids: list[str] = Field(default_factory=list)


class ModelPrediction(BaseModel):
    task: str
    value: float | str
    confidence: float | None = Field(default=None, ge=0, le=1)
    model_version: str
    feature_version: str
    explanation: dict[str, Any] = Field(default_factory=dict)


class AnalysisResult(BaseModel):
    analysis_id: str = Field(default_factory=lambda: f"analysis-{uuid4().hex}")
    request: AnalysisRequest
    status: RunStatus = RunStatus.queued
    features: list[FeatureObservation] = Field(default_factory=list)
    predictions: list[ModelPrediction] = Field(default_factory=list)
    artifacts: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None

    def feature_set(self, schema_version: str = "feature-schema-v1") -> FeatureSet:
        return FeatureSet(
            sample_id=self.request.sample.sample_id,
            schema_version=schema_version,
            observations=self.features,
            provenance=Provenance(
                source="analysis",
                source_version=self.request.database_version,
                parameters={"analysis_id": self.analysis_id},
            ),
        )


class EvidenceBundle(BaseModel):
    bundle_id: str = Field(default_factory=lambda: f"evidence-{uuid4().hex}")
    analysis: AnalysisResult
    claims: list[KnowledgeClaim] = Field(default_factory=list)
    knowledge_version: str
    generated_at: datetime = Field(default_factory=utc_now)


class ReportStatement(BaseModel):
    statement_id: str = Field(default_factory=lambda: f"statement-{uuid4().hex}")
    section: str
    text: str
    feature_ids: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    prediction_tasks: list[str] = Field(default_factory=list)
    is_disclaimer: bool = False


class StructuredReport(BaseModel):
    sample_id: str
    title: str
    versions: VersionSet
    statements: list[ReportStatement] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=utc_now)


class ReportArtifact(BaseModel):
    report_id: str = Field(default_factory=lambda: f"report-{uuid4().hex}")
    sample_id: str
    template_version: str
    evidence_bundle_id: str
    markdown: str
    output_paths: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
