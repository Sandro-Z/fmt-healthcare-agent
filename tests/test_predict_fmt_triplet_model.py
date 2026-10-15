import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd


MODULE_PATH = Path(__file__).parent.parent / "scripts" / "predict_fmt_triplet_model.py"
SPEC = importlib.util.spec_from_file_location("fmt_predict", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def fake_predictor():
    predictor = MODULE.FMTTripletPredictor.__new__(MODULE.FMTTripletPredictor)
    predictor.features = ["s__A", "s__B", "s__C"]
    predictor.projection = np.eye(3, 2)
    predictor.scaler_mean = np.zeros(3)
    predictor.scaler_scale = np.ones(3)
    predictor.classifier_coef = np.zeros((1, 6))
    predictor.classifier_intercept = np.zeros(1)
    return predictor


def test_alignment_reorders_fills_and_collapses():
    frame = pd.DataFrame(
        [[10.0, 30.0, 60.0]], index=["X"],
        columns=["k__Bacteria|s__B", "s__A", "s__EXTRA"],
    )
    batch = fake_predictor().align(frame, "percent")
    assert batch.standardized.shape == (1, 3)
    assert batch.embedding.shape == (1, 2)
    assert batch.audit.loc[0, "present_required_count"] == 2
    assert np.isclose(batch.audit.loc[0, "abundance_coverage"], 0.4)


def test_response_shapes_and_probability():
    predictor = fake_predictor()
    frame = pd.DataFrame([[30.0, 30.0, 40.0]], index=["X"], columns=predictor.features)
    result, audit = predictor.response(frame, frame, frame, "percent", "percent", "percent")
    assert result.shape[0] == 1
    assert result.loc[0, "response_probability"] == 0.5
    assert len(audit) == 3
