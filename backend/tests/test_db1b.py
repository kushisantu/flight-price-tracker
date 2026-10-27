from app.services.db1b import normalize_fare


def test_keeps_every_airport_and_does_not_divide_the_fare():
    parsed = normalize_fare(
        {
            "year": "2025",
            "quarter": "2",
            "origin": "ABI",
            "dest": "DFW",
            "tk": "AA",
            "op": "AA",
            "bulk": "0",
            "passengers": "2",
            "fare": "350",
            "distance": "283",
            "coupons": "1",
            "origin_state": "TX",
            "dest_state": "TX",
        }
    )
    assert parsed is not None
    assert parsed[2:5] == ("ABI", "DFW", "AA")
    assert parsed[6] == 2
    assert parsed[7] == 350.0
    assert parsed[8] == 0
    assert parsed[9] == 1
    assert parsed[10:] == ("TX", "TX")


def test_keeps_international_markets_present_in_the_file():
    parsed = normalize_fare(
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
            "distance": "3450",
            "coupons": "1",
            "origin_state": "NY",
            "dest_state": "",
        }
    )
    assert parsed is not None
    assert parsed[2:4] == ("JFK", "LHR")


def test_drops_bulk_same_airport_and_bad_fares():
    base = {
        "year": "2025",
        "quarter": "2",
        "origin": "JFK",
        "dest": "LAX",
        "tk": "AA",
        "op": "AA",
        "bulk": "0",
        "passengers": "1",
        "fare": "500",
        "distance": "2475",
        "coupons": "1",
        "origin_state": "NY",
        "dest_state": "CA",
    }
    assert normalize_fare({**base, "bulk": "1"}) is None
    assert normalize_fare({**base, "dest": "JFK"}) is None
    assert normalize_fare({**base, "fare": "5"}) is None
