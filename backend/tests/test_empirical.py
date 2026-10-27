from datetime import date, timedelta

import pytest

from app.services.db1b import connect, ensure_schema
from app.services.empirical import (
    HOLDOUT,
    build_quantile_tables,
    choose_slice,
    lookup_prediction,
)
from app.services.flights import from_payload


def _prepare(tmp_path, rows: list[tuple]):
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
        rows,
    )
    connection.commit()
    return connection


def test_choose_slice_prefers_the_route_then_broader_real_slices():
    assert choose_slice(50, 10, 10) == "route"
    assert choose_slice(49, 50, 10) == "distance_band"
    assert choose_slice(10, 10, 50) == "state_pair"
    assert choose_slice(10, 10, 10) is None


def test_holdout_tickets_do_not_change_training_quantiles(tmp_path):
    connection = _prepare(tmp_path, [
        (2024, 3, "JFK", "LAX", "AA", 2475, 60, 100, 0, 1, "NY", "CA"),
        (HOLDOUT[0], HOLDOUT[1], "JFK", "LAX", "AA", 2475, 60, 900, 0, 1, "NY", "CA"),
        (HOLDOUT[0], HOLDOUT[1], "MIA", "BOS", "DL", 1258, 80, 50, 0, 1, "FL", "MA"),
    ])
    try:
        build_quantile_tables(connection)
        from app.services.empirical import assert_holdout_excluded
        assert_holdout_excluded(connection)
        predicted = lookup_prediction(connection, "JFK", "LAX")
        assert predicted is not None
        assert predicted["slice"] == "route"
        assert predicted["confidence"] == "normal"
        assert predicted["mid"] == 100
        assert lookup_prediction(connection, "MIA", "BOS") is None
    finally:
        connection.close()


def test_thin_route_uses_state_pair_and_says_low_confidence(tmp_path):
    connection = _prepare(tmp_path, [
        (2024, 3, "ABI", "DFW", "AA", 100, 10, 80, 0, 1, "TX", "TX"),
        (2024, 4, "AUS", "SAT", "WN", 400, 60, 150, 0, 1, "TX", "TX"),
    ])
    try:
        build_quantile_tables(connection)
        predicted = lookup_prediction(connection, "ABI", "DFW")
        assert predicted is not None
        assert predicted["slice"] == "state_pair"
        assert predicted["confidence"] == "low"
        assert predicted["mid"] == 150
        assert "state pair" in predicted["label"]
    finally:
        connection.close()


def test_route_with_no_real_slice_is_uncovered(tmp_path):
    connection = _prepare(tmp_path, [
        (2024, 3, "ABI", "DFW", "AA", 100, 10, 80, 0, 1, "", ""),
    ])
    try:
        build_quantile_tables(connection)
        assert lookup_prediction(connection, "ABI", "DFW") is None
    finally:
        connection.close()


def test_sample_board_does_not_invent_itineraries(monkeypatch):
    monkeypatch.setattr("app.services.flights.known_airport", lambda code: code == "ABI")
    depart = date.today() + timedelta(days=40)
    with pytest.raises(ValueError, match="sample fare board does not include this airport"):
        from_payload({
            "origin": "ABI",
            "destination": "DFW",
            "depart_date": depart.isoformat(),
            "return_date": (depart + timedelta(days=3)).isoformat(),
            "trip_type": "round",
            "passengers": 1,
            "cabin": "economy",
        })
