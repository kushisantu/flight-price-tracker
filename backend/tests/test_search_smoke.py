from datetime import date, timedelta

from app.services.flights import TripQuery, build_insight, price_history, quote_parts, search


def _payload():
    depart = date.today() + timedelta(days=40)
    ret = depart + timedelta(days=7)
    return {
        "origin": "NYC",
        "destination": "LON",
        "depart_date": depart.isoformat(),
        "return_date": ret.isoformat(),
        "trip_type": "round",
        "passengers": 1,
        "cabin": "economy",
    }


def test_quote_history_and_insight():
    query = TripQuery(
        origin="NYC",
        destination="LON",
        depart=date.today() + timedelta(days=40),
        ret=date.today() + timedelta(days=47),
    )
    price, airline, stops = quote_parts(query)
    assert price > 0
    assert airline
    assert stops in (0, 1)
    history = price_history(query)
    assert len(history) >= 40
    assert history[0]["date"] < history[-1]["date"]
    assert all(point["price"] > 0 for point in history)
    insight = build_insight(query, history, [])
    for key in ("level", "title", "summary", "advice", "trend", "current", "average"):
        assert key in insight


def test_search_contract():
    result = search(_payload())
    assert result["provider"] == "sample"
    assert result["flights"]
    assert result["history"]
    assert result["date_strip"]
    assert result["insight"]["advice"]
    flight = result["flights"][0]
    for key in ("price", "airline_code", "stops", "legs"):
        assert key in flight
    assert flight["price"] > 0
