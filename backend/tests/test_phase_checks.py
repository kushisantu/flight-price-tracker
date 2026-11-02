import json

from app.services.db1b import HOLDOUT
from app.services.phase2 import (
    CALIBRATION,
    FEATURES,
    FINAL_TRAIN,
    PHASE2_DIR,
    design_matrix,
)
import numpy as np


def test_feature_order_matches_the_design_matrix():
    matrix = design_matrix(
        np.array([1]), np.array([2]), np.array([3]),
        np.array([400.0], dtype=np.float32),
        np.array([4], dtype=np.float32),
        np.array([1], dtype=np.float32),
        np.array([0], dtype=np.float32),
        np.array([0.5], dtype=np.float32),
    )
    assert matrix.shape[1] == len(FEATURES)
    assert list(FEATURES) == ["origin", "dest", "airline", "distance", "quarter", "coupons", "stops", "nonstop", "carrier_share"]
    assert matrix[0, FEATURES.index("nonstop")] == 1


def test_holdout_and_calibration_stay_out_of_the_final_fit():
    assert HOLDOUT not in FINAL_TRAIN
    assert CALIBRATION not in FINAL_TRAIN


def test_saved_holdout_beats_the_empirical_table():
    path = PHASE2_DIR.parent / "phase2_metrics.json"
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    comparison = data["comparison"]
    assert comparison["model_mae"] < comparison["empirical_mae"]
    assert 0.75 <= comparison["conformal_10_90_coverage"] <= 0.90
