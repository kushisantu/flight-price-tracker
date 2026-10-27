"""Passenger-weighted fare ranges from earlier DOT quarters.

2025 Q2 is held out. A route with fewer than 50 training passengers uses a
wider slice of real tickets and is marked low confidence. Nothing is filled
in when no real slice is large enough.
"""

from __future__ import annotations

import sqlite3

import numpy as np

from app.services.db1b import HOLDOUT, SOURCE, is_holdout

SEED = 1
MIN_PASSENGERS = 50
BAND_MILES = 250
VERSION = "empirical-2024q3-2025q1"
TRAIN_LABEL = "2024 Q3–2025 Q1"

np.random.seed(SEED)


def distance_band(distance: float) -> int:
    return int(distance // BAND_MILES) * BAND_MILES


def state_key(origin_state: str, dest_state: str) -> str | None:
    left = (origin_state or "").strip().upper()
    right = (dest_state or "").strip().upper()
    if not left or not right:
        return None
    return f"{left}|{right}"


def weighted_quantiles(fares: np.ndarray, weights: np.ndarray, probs=(0.1, 0.5, 0.9)) -> tuple[float, float, float]:
    order = np.argsort(fares, kind="mergesort")
    ordered = fares[order]
    cumulative = np.cumsum(weights[order])
    total = float(cumulative[-1])
    picked = []
    for prob in probs:
        index = int(np.searchsorted(cumulative, prob * total, side="left"))
        index = min(index, len(ordered) - 1)
        picked.append(float(ordered[index]))
    low, mid, high = picked
    if mid < low:
        mid = low
    if high < mid:
        high = mid
    return low, mid, high


def choose_slice(route_passengers: int, band_passengers: int, state_passengers: int) -> str | None:
    if route_passengers >= MIN_PASSENGERS:
        return "route"
    if band_passengers >= MIN_PASSENGERS:
        return "distance_band"
    if state_passengers >= MIN_PASSENGERS:
        return "state_pair"
    return None


def _ensure_quantile_tables(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        DROP TABLE IF EXISTS route_quantiles;
        DROP TABLE IF EXISTS slice_quantiles;
        CREATE TABLE route_quantiles (
            origin TEXT NOT NULL,
            dest TEXT NOT NULL,
            passengers INTEGER NOT NULL,
            distance REAL NOT NULL,
            origin_state TEXT NOT NULL,
            dest_state TEXT NOT NULL,
            distance_band INTEGER NOT NULL,
            mean_fare REAL NOT NULL,
            low REAL,
            mid REAL,
            high REAL,
            PRIMARY KEY (origin, dest)
        );
        CREATE TABLE slice_quantiles (
            kind TEXT NOT NULL,
            key TEXT NOT NULL,
            passengers INTEGER NOT NULL,
            low REAL NOT NULL,
            mid REAL NOT NULL,
            high REAL NOT NULL,
            PRIMARY KEY (kind, key)
        );
        """
    )


def _flush_fare_map(fare_weights: dict[int, float]) -> tuple[float, float, float, float, float]:
    fares = np.fromiter(fare_weights.keys(), dtype=np.float64)
    weights = np.fromiter(fare_weights.values(), dtype=np.float64)
    low, mid, high = weighted_quantiles(fares, weights)
    mean = float(np.average(fares, weights=weights))
    total = float(weights.sum())
    return low, mid, high, mean, total


def build_quantile_tables(connection: sqlite3.Connection) -> dict:
    """Aggregate training quarters only. Holdout rows never enter the tables."""
    _ensure_quantile_tables(connection)
    cursor = connection.execute(
        """
        SELECT origin, dest, CAST(ROUND(fare) AS INTEGER) AS fare_dollar,
               SUM(passengers) AS passengers,
               SUM(distance * passengers) AS distance_weight,
               MAX(origin_state) AS origin_state,
               MAX(dest_state) AS dest_state
        FROM market_fares
        WHERE NOT (year = ? AND quarter = ?)
        GROUP BY origin, dest, fare_dollar
        ORDER BY origin, dest, fare_dollar
        """,
        HOLDOUT,
    )
    route_rows = []
    band_maps: dict[int, dict[int, float]] = {}
    state_maps: dict[str, dict[int, float]] = {}
    current = None
    fare_weights: dict[int, float] = {}
    passengers = 0
    distance_weight = 0.0
    origin_state = ""
    dest_state = ""

    def flush() -> None:
        nonlocal fare_weights, passengers, distance_weight
        if current is None or passengers <= 0:
            fare_weights = {}
            passengers = 0
            distance_weight = 0.0
            return
        distance = distance_weight / passengers
        band = distance_band(distance)
        low = mid = high = None
        mean = float(np.average(
            np.fromiter(fare_weights.keys(), dtype=np.float64),
            weights=np.fromiter(fare_weights.values(), dtype=np.float64),
        ))
        if passengers >= MIN_PASSENGERS:
            low, mid, high, mean, _total = _flush_fare_map(fare_weights)
        route_rows.append((
            current[0],
            current[1],
            int(passengers),
            round(distance, 1),
            origin_state,
            dest_state,
            band,
            round(mean, 2),
            None if low is None else round(low, 2),
            None if mid is None else round(mid, 2),
            None if high is None else round(high, 2),
        ))
        fare_weights = {}
        passengers = 0
        distance_weight = 0.0

    for row in cursor:
        key = (row["origin"], row["dest"])
        if key != current:
            flush()
            current = key
            origin_state = row["origin_state"] or ""
            dest_state = row["dest_state"] or ""
        fare = int(row["fare_dollar"])
        weight = float(row["passengers"])
        fare_weights[fare] = fare_weights.get(fare, 0.0) + weight
        passengers += weight
        distance_weight += float(row["distance_weight"])
        band = distance_band(float(row["distance_weight"]) / weight)
        band_slot = band_maps.setdefault(band, {})
        band_slot[fare] = band_slot.get(fare, 0.0) + weight
        pair = state_key(row["origin_state"], row["dest_state"])
        if pair:
            state_slot = state_maps.setdefault(pair, {})
            state_slot[fare] = state_slot.get(fare, 0.0) + weight
    flush()

    connection.executemany(
        """
        INSERT INTO route_quantiles (
            origin, dest, passengers, distance, origin_state, dest_state, distance_band,
            mean_fare, low, mid, high
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        route_rows,
    )
    slice_rows = []
    for band, fare_map in band_maps.items():
        low, mid, high, _mean, total = _flush_fare_map(fare_map)
        if total < MIN_PASSENGERS:
            continue
        slice_rows.append(("distance", str(band), int(round(total)), round(low, 2), round(mid, 2), round(high, 2)))
    for key, fare_map in state_maps.items():
        low, mid, high, _mean, total = _flush_fare_map(fare_map)
        if total < MIN_PASSENGERS:
            continue
        slice_rows.append(("state", key, int(round(total)), round(low, 2), round(mid, 2), round(high, 2)))
    connection.executemany(
        """
        INSERT INTO slice_quantiles (kind, key, passengers, low, mid, high)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        slice_rows,
    )
    connection.execute(
        "INSERT OR REPLACE INTO dot_meta (key, value) VALUES ('quantile_version', ?)",
        (VERSION,),
    )
    connection.commit()
    return {
        "routes": len(route_rows),
        "slices": len(slice_rows),
        "version": VERSION,
    }


def lookup_prediction(connection: sqlite3.Connection, origin: str, dest: str) -> dict | None:
    route = connection.execute(
        "SELECT * FROM route_quantiles WHERE origin = ? AND dest = ?",
        (origin, dest),
    ).fetchone()
    if route is None:
        return None
    band = connection.execute(
        "SELECT * FROM slice_quantiles WHERE kind = 'distance' AND key = ?",
        (str(route["distance_band"]),),
    ).fetchone()
    pair = state_key(route["origin_state"], route["dest_state"])
    state = None
    if pair:
        state = connection.execute(
            "SELECT * FROM slice_quantiles WHERE kind = 'state' AND key = ?",
            (pair,),
        ).fetchone()
    routes = {(origin, dest): route}
    slices = {}
    if band is not None:
        slices[("distance", str(route["distance_band"]))] = band
    if state is not None and pair:
        slices[("state", pair)] = state
    return predict_cached(routes, slices, origin, dest)


def prediction_note(low: int, high: int, confidence: str, label: str) -> str:
    base = (
        f"Real tickets usually paid ${low:,}–${high:,}. "
        f"{SOURCE}, {VERSION}. Passenger-weighted 10th to 90th percentile from {TRAIN_LABEL}. "
        "This is an empirical table, not a refit model, and it is not a forecast."
    )
    if confidence == "low":
        return (
            f"Low confidence. This route has fewer than {MIN_PASSENGERS} passengers in the training quarters, "
            f"so the range uses {label} of real tickets, not this airport pair alone. "
            + base
        )
    return f"The range is {label}. " + base


def load_indexes(connection: sqlite3.Connection) -> tuple[dict, dict]:
    routes = {
        (row["origin"], row["dest"]): row
        for row in connection.execute("SELECT * FROM route_quantiles")
    }
    slices = {
        (row["kind"], row["key"]): row
        for row in connection.execute("SELECT * FROM slice_quantiles")
    }
    return routes, slices


def predict_cached(routes: dict, slices: dict, origin: str, dest: str) -> dict | None:
    route = routes.get((origin, dest))
    if route is None or int(route["passengers"]) <= 0:
        return None
    band = slices.get(("distance", str(route["distance_band"])))
    pair = state_key(route["origin_state"], route["dest_state"])
    state = slices.get(("state", pair)) if pair else None
    chosen = choose_slice(
        int(route["passengers"]),
        int(band["passengers"]) if band else 0,
        int(state["passengers"]) if state else 0,
    )
    if chosen is None:
        return None
    if chosen == "route":
        low, mid, high = route["low"], route["mid"], route["high"]
        slice_passengers = int(route["passengers"])
        label = "this airport pair"
    elif chosen == "distance_band":
        low, mid, high = band["low"], band["mid"], band["high"]
        slice_passengers = int(band["passengers"])
        label = f"the {route['distance_band']}-mile distance band"
    else:
        low, mid, high = state["low"], state["mid"], state["high"]
        slice_passengers = int(state["passengers"])
        label = f"the {route['origin_state']}–{route['dest_state']} state pair"
    return {
        "slice": chosen,
        "label": label,
        "confidence": "normal" if chosen == "route" else "low",
        "low": float(low),
        "mid": float(mid),
        "high": float(high),
        "route_passengers": int(route["passengers"]),
        "slice_passengers": slice_passengers,
        "mean_fare": float(route["mean_fare"]),
        "distance": float(route["distance"]),
    }


def assert_holdout_excluded(connection: sqlite3.Connection) -> None:
    """Training aggregates must not contain the holdout quarter."""
    row = connection.execute(
        """
        SELECT COUNT(*) AS n FROM market_fares
        WHERE year = ? AND quarter = ?
        """,
        HOLDOUT,
    ).fetchone()
    if int(row["n"]) == 0:
        return
    leaked = connection.execute(
        """
        SELECT COUNT(*) AS n
        FROM route_quantiles AS route
        WHERE NOT EXISTS (
            SELECT 1 FROM market_fares AS fare
            WHERE fare.origin = route.origin
              AND fare.dest = route.dest
              AND NOT (fare.year = ? AND fare.quarter = ?)
        )
        """,
        HOLDOUT,
    ).fetchone()
    if int(leaked["n"]):
        raise RuntimeError("A route quantile was built without training-quarter tickets.")
