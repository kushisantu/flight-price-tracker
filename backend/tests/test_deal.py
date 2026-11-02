from datetime import date, timedelta

import numpy as np
import pytest

from app.services.db1b import connect, ensure_schema
from app.services.deal import deal_score
from app.services.flights import search
from app.services.phase2 import ALPHAS, deal_label, fare_percentile


def test_percentile_interpolates_between_quantiles():
    quantiles = np.array([100, 150, 200, 300, 400, 500, 600], dtype=float)
    assert fare_percentile(300, quantiles) == pytest.approx(50)
    assert fare_percentile(250, quantiles) == pytest.approx(37.5)
    assert fare_percentile(50, quantiles) == pytest.approx(2.5)
    assert fare_percentile(1200, quantiles) == pytest.approx(100)


def test_deal_labels_follow_the_lower_tail():
    assert deal_label(10) == "Great"
    assert deal_label(25) == "Good"
    assert deal_label(75) == "Typical"
    assert deal_label(75.1) == "High"


def test_training_profile_ignores_the_holdout(tmp_path, monkeypatch):
    path = tmp_path / "fares.sqlite"
    connection = connect(path)
    ensure_schema(connection)
    connection.executemany(
        """
        INSERT INTO market_fares (
            year, quarter, origin, dest, airline, distance, passengers, fare, stops,
            coupons, origin_state, dest_state
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (2024, 3, "LAX", "JFK", "AA", 2475, 10, 300, 0, 1, "CA", "NY"),
            (2025, 2, "LAX", "JFK", "AA", 2475, 1000, 50, 0, 1, "CA", "NY"),
            (2024, 4, "LAX", "JFK", "DL", 2475, 40, 280, 0, 1, "CA", "NY"),
        ],
    )
    connection.commit()
    connection.close()
    monkeypatch.setattr("app.services.db1b.DB_PATH", path)
    monkeypatch.setattr("app.services.fare_band.DB_PATH", path)
    monkeypatch.setattr("app.services.deal.DB_PATH", path)

    missing = deal_score("LAX", "HNL", "AA", 4, 200, "sample")
    assert missing["available"] is False
    assert "No DOT ticket sample" in missing["note"]

    other = deal_score("LAX", "JFK", "UA", 4, 200, "sample")
    assert other["available"] is False
    assert "this airline" in other["note"]

    scored = deal_score("LAX", "JFK", "AA", 4, 200, "sample")
    if scored["note"] == "The paid-fare model is not installed.":
        pytest.skip("Phase 2 model files are not on disk.")
    assert scored["available"] is True
    assert scored["passengers"] == 10
    assert scored["confidence"] == "low"
    assert scored["fare_kind"] == "sample"
    assert "simulated sample fare" in scored["note"]
    assert scored["label"] in {"Great", "Good", "Typical", "High"}
    assert 0 <= scored["percentile"] <= 100
    assert list(scored["quantiles"]) == [str(int(alpha * 100)) for alpha in ALPHAS]


def test_sample_itinerary_keeps_the_outbound_fare_separate():
    depart = date.today() + timedelta(days=40)
    result = search({
        "origin": "JFK",
        "destination": "LAX",
        "depart_date": depart.isoformat(),
        "return_date": (depart + timedelta(days=7)).isoformat(),
        "trip_type": "round",
        "passengers": 1,
        "cabin": "economy",
    })
    flight = result["flights"][0]
    assert flight["price_kind"] == "sample"
    assert flight["directional_price"] < flight["price"]
    one_way = search({
        "origin": "JFK",
        "destination": "LAX",
        "depart_date": depart.isoformat(),
        "return_date": None,
        "trip_type": "oneway",
        "passengers": 1,
        "cabin": "economy",
    })
    assert one_way["flights"][0]["directional_price"] == one_way["flights"][0]["price"]
