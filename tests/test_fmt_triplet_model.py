import importlib.util
import sys
from pathlib import Path

import numpy as np


MODULE_PATH = Path(__file__).parent.parent / "scripts" / "train_fmt_triplet_model.py"
SPEC = importlib.util.spec_from_file_location("fmt_triplet", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_clr_rows_are_centered():
    transformed = MODULE.clr(np.array([[1.0, 2.0, 3.0], [0.0, 2.0, 4.0]]))
    assert np.allclose(transformed.mean(axis=1), 0.0)


def test_ranking_metrics():
    result = MODULE.ranking_metrics([1, 2, 5, 20])
    assert result["recall_at_1"] == 0.25
    assert result["recall_at_5"] == 0.75
    assert result["mrr"] > 0
