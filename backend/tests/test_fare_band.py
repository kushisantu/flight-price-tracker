from app.services.db1b import connect, ensure_schema
from app.services.empirical import build_quantile_tables
from app.services.fare_band import paid_fare_band


def test_paid_fare_band_labels_low_confidence_and_uncovered(tmp_path, monkeypatch):
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
            (2024, 3, "LAX", "JFK", "AA", 2475, 80, 300, 0, 1, "CA", "NY"),
            (2024, 3, "ABI", "DFW", "AA", 100, 10, 80, 0, 1, "TX", "TX"),
            (2024, 4, "AUS", "SAT", "WN", 400, 60, 150, 0, 1, "TX", "TX"),
        ],
    )
    connection.executemany(
        """
        INSERT INTO airports (code, name, city, country, lat, lon, timezone, passengers)
        VALUES (?, ?, ?, ?, NULL, NULL, '', ?)
        """,
        [
            ("LAX", "Los Angeles International", "Los Angeles", "United States", 80),
            ("JFK", "John F. Kennedy International", "New York", "United States", 80),
            ("ABI", "Name unavailable", "ABI", "", 10),
            ("DFW", "Dallas/Fort Worth International", "Dallas", "United States", 10),
        ],
    )
    connection.commit()
    build_quantile_tables(connection)
    connection.close()
    monkeypatch.setattr("app.services.db1b.DB_PATH", path)
    monkeypatch.setattr("app.services.fare_band.DB_PATH", path)

    thick = paid_fare_band("LAX", "JFK")
    assert thick["available"] is True
    assert thick["confidence"] == "normal"
    assert thick["slice"] == "route"
    assert thick["low"] <= thick["mid"] <= thick["high"]
    assert "not a forecast" in thick["note"]
    assert "empirical" in thick["note"]

    thin = paid_fare_band("ABI", "DFW")
    assert thin["available"] is True
    assert thin["confidence"] == "low"
    assert thin["slice"] == "state_pair"
    assert "Low confidence" in thin["note"]

    missing = paid_fare_band("LAX", "HNL")
    assert missing["available"] is False
    assert "No DOT ticket sample" in missing["note"]
