import numpy as np

from app.services.db1b import connect, ensure_schema
from app.services.fare_band import paid_fare_band
from app.services.phase2 import (
    aggregate_route_quantiles,
    carrier_share_feature,
    conformal_offset,
    design_matrix,
    is_final_training,
    repair_quantiles,
    widen_band,
)


def test_repair_quantiles_are_non_crossing():
    raw = np.array([[100.0, 10.0, 50.0, 80.0, 5.0, 90.0, 70.0]])
    fixed = repair_quantiles(raw)
    assert list(fixed[0]) == sorted(fixed[0])
    assert fixed[0, 0] <= fixed[0, 3] <= fixed[0, -1]


def test_widen_band_keeps_the_median_inside():
    repaired = np.array([[10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0]])
    low, mid, high = widen_band(repaired, 100.0)
    assert low[0] <= mid[0] <= high[0]
    assert mid[0] == 40.0


def test_carrier_share_ignores_holdout_passengers():
    origin = np.array([0, 0, 0])
    dest = np.array([0, 0, 0])
    airline = np.array([0, 1, 0])
    passengers = np.array([10.0, 30.0, 1000.0])
    mask = np.array([True, True, False])
    share = carrier_share_feature(origin, dest, airline, passengers, mask, 1, 1, 2)
    assert share[0] == np.float32(10 / 40)
    assert share[1] == np.float32(30 / 40)
    assert share[2] == np.float32(10 / 40)


def test_holdout_and_calibration_are_not_training_periods():
    assert is_final_training(2024, 3)
    assert is_final_training(2024, 4)
    assert not is_final_training(2025, 1)
    assert not is_final_training(2025, 2)


def test_conformal_offset_uses_passenger_weights():
    scores = np.array([0.0, 10.0, 20.0])
    weights = np.array([1.0, 1.0, 1.0])
    assert conformal_offset(scores, weights, 0.8) == 20.0


def test_nonstop_follows_coupon_count():
    matrix = design_matrix(
        np.array([0]),
        np.array([1]),
        np.array([2]),
        np.array([100.0]),
        np.array([3]),
        np.array([1]),
        np.array([0]),
        np.array([0.5]),
    )
    assert matrix[0, 7] == 1
    connecting = design_matrix(
        np.array([0]),
        np.array([1]),
        np.array([2]),
        np.array([100.0]),
        np.array([3]),
        np.array([2]),
        np.array([1]),
        np.array([0.5]),
    )
    assert connecting[0, 7] == 0


def test_aggregate_route_quantiles_stay_ordered():
    quantiles = np.array(
        [
            [9.0, 8.0, 7.0, 6.0, 5.0, 4.0, 3.0],
            [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0],
        ]
    )
    means, totals = aggregate_route_quantiles(quantiles, np.array([1.0, 1.0]), np.array([0, 0]))
    assert totals[0] == 2
    assert list(means[0]) == sorted(means[0])


def test_model_band_marks_thin_routes_and_leaves_missing_routes_uncovered(tmp_path, monkeypatch):
    path = tmp_path / "fares.sqlite"
    connection = connect(path)
    ensure_schema(connection)
    connection.execute(
        """
        CREATE TABLE model_route_bands (
            origin TEXT NOT NULL,
            dest TEXT NOT NULL,
            passengers INTEGER NOT NULL,
            low INTEGER NOT NULL,
            mid INTEGER NOT NULL,
            high INTEGER NOT NULL,
            confidence TEXT NOT NULL,
            PRIMARY KEY (origin, dest)
        )
        """
    )
    connection.executemany(
        """
        INSERT INTO model_route_bands (origin, dest, passengers, low, mid, high, confidence)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("LAX", "JFK", 80, 100, 200, 400, "normal"),
            ("ABI", "DFW", 10, 50, 80, 120, "low"),
        ],
    )
    connection.execute(
        """
        INSERT INTO airports (code, name, city, country, lat, lon, timezone, passengers)
        VALUES ('ABI', 'Name unavailable', 'ABI', '', NULL, NULL, '', 10)
        """
    )
    connection.commit()
    connection.close()
    monkeypatch.setattr("app.services.db1b.DB_PATH", path)
    monkeypatch.setattr("app.services.fare_band.DB_PATH", path)

    thick = paid_fare_band("LAX", "JFK")
    assert thick["available"] is True
    assert thick["slice"] == "model"
    assert thick["confidence"] == "normal"
    assert thick["low"] <= thick["mid"] <= thick["high"]
    assert "not a booking-date forecast" in thick["note"]

    thin = paid_fare_band("ABI", "DFW")
    assert thin["available"] is True
    assert thin["confidence"] == "low"
    assert thin["note"].startswith("Low confidence.")

    missing = paid_fare_band("LAX", "HNL")
    assert missing["available"] is False
    assert "No DOT ticket sample" in missing["note"]
