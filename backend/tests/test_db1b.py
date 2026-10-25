from app.services.db1b import normalize_fare, us_airports


def test_keeps_domestic_catalog_fare_without_dividing():
    airports = us_airports()
    parsed = normalize_fare(
        {
            "year": "2025",
            "quarter": "2",
            "origin": "JFK",
            "dest": "LAX",
            "tk": "AA",
            "op": "AA",
            "bulk": "0",
            "passengers": "2",
            "fare": "350",
            "distance": "2475",
            "coupons": "1",
        },
        airports,
    )
    assert parsed is not None
    year, quarter, origin, dest, airline, distance, passengers, fare, stops = parsed
    assert (year, quarter, origin, dest, airline) == (2025, 2, "JFK", "LAX", "AA")
    assert passengers == 2
    assert fare == 350.0
    assert distance == 2475
    assert stops == 0


def test_drops_international_bulk_and_bad_fares():
    airports = us_airports()
    assert "LHR" not in airports
    assert normalize_fare(
        {
            "year": "2025",
            "quarter": "2",
            "origin": "JFK",
            "dest": "LHR",
            "tk": "AA",
            "op": "AA",
            "bulk": "0",
            "passengers": "1",
            "fare": "500",
            "distance": "5500",
            "coupons": "1",
        },
        airports,
    ) is None
    assert normalize_fare(
        {
            "year": "2025",
            "quarter": "2",
            "origin": "JFK",
            "dest": "LAX",
            "tk": "AA",
            "op": "AA",
            "bulk": "1",
            "passengers": "1",
            "fare": "500",
            "distance": "2475",
            "coupons": "1",
        },
        airports,
    ) is None
    assert normalize_fare(
        {
            "year": "2025",
            "quarter": "2",
            "origin": "JFK",
            "dest": "LAX",
            "tk": "AA",
            "op": "AA",
            "bulk": "0",
            "passengers": "1",
            "fare": "5",
            "distance": "2475",
            "coupons": "2",
        },
        airports,
    ) is None
