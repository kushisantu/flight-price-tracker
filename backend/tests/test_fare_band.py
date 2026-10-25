from pathlib import Path

import pytest

from app.services.fare_band import MODEL_DIR, paid_fare_band

model_ready = pytest.mark.skipif(
    not (MODEL_DIR / "metadata.json").exists(),
    reason="Train the DOT fare model before checking the paid-fare range.",
)


@model_ready
def test_us_route_has_a_paid_range():
    band = paid_fare_band("LAX", "JFK")
    assert band["available"] is True
    assert band["low"] < band["mid"] < band["high"]
    assert band["source"] == "US DOT DB1B Market"
    assert band["year"] == 2025
    assert band["quarter"] == 2
    assert band["passengers"] > 0
    assert "not a forecast" in band["note"]
    assert Path(MODEL_DIR / "quantile_50.txt").exists()


@model_ready
def test_international_route_is_outside_the_sample():
    band = paid_fare_band("NYC", "LON")
    assert band["available"] is False
    assert band["low"] is None
    assert "No DOT ticket sample" in band["note"]
