"""Seeded fare simulator.

Observable factors set a stable base fare. A hidden market path, shared by
every airline on a route and departure date, moves that base up and down.
The same seed always rebuilds the same path.
"""

from __future__ import annotations

import hashlib
import math
import random
from datetime import date, timedelta
from functools import lru_cache

DEFAULT_SEED = 1
ANCHOR_DAYS = 400


def _mix_seed(*parts: str, experiment_seed: int) -> int:
    raw = "|".join((str(experiment_seed), *parts))
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return int(digest[:8], 16)


def route_volatility(origin: str, dest: str) -> float:
    """Daily demand noise for a route, about 1.2% to 4.5%."""
    unit = _mix_seed(origin, dest, "vol", experiment_seed=0) / 0xFFFFFFFF
    return 0.012 + unit * (0.045 - 0.012)


def volatility_scale(days_out: int) -> float:
    """Noise grows as the departure date gets close."""
    return 1.0 + 1.8 * math.exp(-max(days_out, 0) / 12)


def horizon_factor(days_out: int) -> float:
    """Mild last-minute tilt. Demand can still pull the fare down."""
    days = max(0, days_out)
    if days >= 45:
        return 1.0
    if days >= 14:
        return 1.0 + (45 - days) / (45 - 14) * 0.08
    return 1.08 + (14 - days) / 14 * 0.17


def _observable_base(
    origin_code: str,
    dest_code: str,
    airline_code: str,
    stops: int,
    cabin: str,
    depart: date,
    passengers: int,
) -> float:
    from app.catalog import AIRLINES, AIRPORTS
    from app.services.flights import CABINS, DOW, _market, _season, distance_km

    origin = AIRPORTS[origin_code]
    dest = AIRPORTS[dest_code]
    km = distance_km(origin, dest)
    raw = 42 + km * 0.052
    raw *= _market(origin, dest, km)
    raw *= AIRLINES[airline_code]["factor"]
    raw *= 1.16 if stops == 0 else 1.0
    raw *= CABINS.get(cabin, 1.0)
    raw *= _season(depart)
    raw *= DOW[depart.weekday()]
    if passengers >= 4:
        raw *= 1.03
    return raw


def price_limits(base: float) -> tuple[int, int]:
    floor = max(49, int(round(0.4 * base)))
    cap = max(floor, int(round(3.5 * base)))
    return floor, cap


@lru_cache(maxsize=4096)
def _market_indexes(origin: str, dest: str, depart_iso: str, seed: int) -> tuple[float, ...]:
    depart = date.fromisoformat(depart_iso)
    anchor = depart - timedelta(days=ANCHOR_DAYS)
    rng = random.Random(_mix_seed(origin, dest, depart_iso, experiment_seed=seed))
    sigma0 = route_volatility(origin, dest)
    demand = 1.0
    pressure = 0.0
    sale = 0.0
    indexes: list[float] = []
    day = anchor
    while day <= depart:
        days_out = (depart - day).days
        sigma = sigma0 * volatility_scale(days_out)
        target = 1.0 + 0.08 * math.sin(day.toordinal() / 28)
        demand += 0.05 * (target - demand) + rng.gauss(0, sigma)
        demand = min(1.8, max(0.65, demand))
        jump_chance = 0.015 if days_out > 14 else 0.04
        if rng.random() < jump_chance:
            demand = min(1.8, demand * rng.uniform(1.08, 1.22))
        sale *= 0.82
        if rng.random() < 0.02:
            sale = max(sale, rng.uniform(0.08, 0.18))
        pressure += 0.03 * (demand - 1.0) - 0.02 * pressure
        pressure = min(0.35, max(-0.05, pressure))
        indexes.append(demand * (1 + pressure) * (1 - sale))
        day += timedelta(days=1)
    return tuple(indexes)


def _index_on(origin: str, dest: str, depart: date, observed: date, seed: int) -> float:
    series = _market_indexes(origin, dest, depart.isoformat(), seed)
    anchor = depart - timedelta(days=ANCHOR_DAYS)
    offset = (observed - anchor).days
    offset = min(len(series) - 1, max(0, offset))
    return series[offset]


def fare_on(
    origin_code: str,
    dest_code: str,
    airline_code: str,
    stops: int,
    cabin: str,
    depart: date,
    observed: date,
    passengers: int = 1,
    seed: int = DEFAULT_SEED,
) -> int:
    base = _observable_base(origin_code, dest_code, airline_code, stops, cabin, depart, passengers)
    days_out = (depart - observed).days
    raw = base * horizon_factor(days_out) * _index_on(origin_code, dest_code, depart, observed, seed)
    floor, cap = price_limits(base)
    return min(cap, max(floor, int(round(raw))))


def trajectory(
    origin_code: str,
    dest_code: str,
    airline_code: str,
    stops: int,
    cabin: str,
    depart: date,
    start: date,
    end: date,
    passengers: int = 1,
    seed: int = DEFAULT_SEED,
) -> list[dict]:
    """One priced day per date from start through end, for offline experiments."""
    rows = []
    day = start
    while day <= end:
        rows.append({
            "date": day.isoformat(),
            "price": fare_on(
                origin_code,
                dest_code,
                airline_code,
                stops,
                cabin,
                depart,
                day,
                passengers,
                seed,
            ),
        })
        day += timedelta(days=1)
    return rows
