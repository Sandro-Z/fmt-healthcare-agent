from datetime import date

from pydantic import BaseModel, Field, model_validator


class EvaluationSample(BaseModel):
    sample_id: str
    subject_id: str
    center_id: str
    collection_date: date
    split: str
    labels: dict[str, str | int | float | bool] = Field(default_factory=dict)


class EvaluationDatasetManifest(BaseModel):
    name: str
    version: str
    task: str
    samples: list[EvaluationSample]
    feature_version: str
    knowledge_version: str
    label_definition: str

    @model_validator(mode="after")
    def prevent_subject_leakage(self) -> "EvaluationDatasetManifest":
        subject_splits: dict[str, set[str]] = {}
        for sample in self.samples:
            subject_splits.setdefault(sample.subject_id, set()).add(sample.split)
        leaked = sorted(subject for subject, splits in subject_splits.items() if len(splits) > 1)
        if leaked:
            raise ValueError(f"subjects occur in multiple splits: {leaked[:10]}")
        return self

