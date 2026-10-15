from datetime import date

import pytest
from pydantic import ValidationError

from wgs_fmt_platform.evaluation import EvaluationDatasetManifest, EvaluationSample


def test_subject_cannot_cross_splits() -> None:
    samples = [
        EvaluationSample(
            sample_id="A",
            subject_id="P1",
            center_id="C1",
            collection_date=date(2025, 1, 1),
            split="train",
        ),
        EvaluationSample(
            sample_id="B",
            subject_id="P1",
            center_id="C1",
            collection_date=date(2025, 2, 1),
            split="test",
        ),
    ]
    with pytest.raises(ValidationError):
        EvaluationDatasetManifest(
            name="leaky",
            version="v1",
            task="risk",
            samples=samples,
            feature_version="f1",
            knowledge_version="k1",
            label_definition="reviewed label",
        )

