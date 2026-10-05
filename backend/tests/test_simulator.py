from datetime import date, timedelta

from app.services.simulator import (
    fare_on,
    price_limits,
    route_volatility,
    trajectory,
    volatility_scale,
    _observable_base,
)


def _trip():
    depart = date.today() + timedelta(days=150)
    start = depart - timedelta(days=119)
    return depart, start


def _series(seed: int):
    depart, start = _trip()
    return trajectory("JFK", "LHR", "AA", 0, "economy", depart, start, depart, seed=seed)


def test_same_seed_matches():
    assert _series(1) == _series(1)


def test_different_seeds_differ():
    assert [row["price"] for row in _series(1)] != [row["price"] for row in _series(2)]


def test_prices_stay_inside_bounds():
    depart = date.today() + timedelta(days=80)
    observed_days = [depart - timedelta(days=day) for day in (0, 10, 40, 70)]
    routes = [("JFK", "LHR", "AA"), ("LAX", "SFO", "UA"), ("ORD", "MIA", "DL")]
    for origin, dest, airline in routes:
        for cabin in ("economy", "business"):
            for stops in (0, 1):
                base = _observable_base(origin, dest, airline, stops, cabin, depart, 1)
                floor, cap = price_limits(base)
                for observed in observed_days:
                    price = fare_on(origin, dest, airline, stops, cabin, depart, observed, seed=3)
                    assert floor <= price <= cap


def test_trajectory_rises_and_falls():
    for seed in (1, 2, 7):
        prices = [row["price"] for row in _series(seed)]
        deltas = [right - left for left, right in zip(prices, prices[1:])]
        assert any(delta > 0 for delta in deltas)
        assert any(delta < 0 for delta in deltas)
        assert prices != sorted(prices)
        assert prices != sorted(prices, reverse=True)


def test_routes_have_different_volatility():
    assert route_volatility("JFK", "LHR") != route_volatility("LAX", "SFO")
    assert volatility_scale(3) > volatility_scale(60)
