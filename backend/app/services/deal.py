"""Percentile of a fare inside the Phase 2 DOT distribution.

The distribution is real ticket quantiles. A fare from the sample board is
still a simulated price, and the response says so.
"""

from __future__ import annotations

import sqlite3
from functools import lru_cache

import numpy as np

from app.services.db1b import DB_PATH, SOURCE, connect
from app.services.fare_band import EMPTY_NOTE, airport_codes
from app.services.phase2 import (
    ALPHAS,
    FEATURES,
    FINAL_TRAIN,
    MIN_PASSENGERS,
    P10_INDEX,
    P90_INDEX,
    PHASE2_DIR,
    VERSION,
    deal_label,
    design_matrix,
    fare_percentile,
    repair_quantiles,
)

SAMPLE_NOTE = (
    "This price is a simulated sample fare. The percentile compares the outbound fare "
    "with real one-way US DOT tickets. It is not a fare those travelers paid."
)
SUPPLIED_NOTE = (
    "This fare was supplied by the caller. The percentile compares it with real one-way "
    "US DOT tickets. The fare itself is not a DOT ticket."
)
AIRLINE_NOTE = (
    "No DOT training tickets for this airline on this route. "
    "The route band is still shown when other airlines were in the sample."
)


def _empty(note: str, fare_kind: str) -> dict:
    return {
        "available": False,
        "origin": None,
        "destination": None,
        "airline": None,
        "quarter": None,
        "fare": None,
        "fare_kind": fare_kind,
        "percentile": None,
        "label": None,
        "quantiles": None,
        "passengers": 0,
        "confidence": None,
        "source": SOURCE,
        "model_version": VERSION,
        "note": note,
    }


def _training_rows(connection, origin: str, dest: str) -> list:
    clause = " OR ".join("(year = ? AND quarter = ?)" for _ in FINAL_TRAIN)
    params: list = [origin, dest]
    for year, quarter in FINAL_TRAIN:
        params.extend((year, quarter))
    return connection.execute(
        f"""
        SELECT airline,
               SUM(passengers) AS passengers,
               SUM(distance * passengers) AS distance_weight,
               SUM(coupons * passengers) AS coupon_weight,
               SUM(stops * passengers) AS stop_weight
        FROM market_fares
        WHERE origin = ? AND dest = ? AND ({clause})
        GROUP BY airline
        """,
        params,
    ).fetchall()


@lru_cache(maxsize=1)
def _boosters():
    import lightgbm as lgb

    metadata_path = PHASE2_DIR / "metadata.json"
    if not metadata_path.exists():
        return None
    import json

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    models = []
    for alpha in ALPHAS:
        path = PHASE2_DIR / f"quantile_{int(round(alpha * 100)):02d}.txt"
        if not path.exists():
            return None
        models.append(lgb.Booster(model_file=str(path)))
    return models, metadata


def _quantiles(origin: str, dest: str, airline: str, quarter: int, row, route_passengers: int) -> np.ndarray | None:
    loaded = _boosters()
    if loaded is None:
        return None
    models, metadata = loaded
    categories = metadata["categories"]
    indexes = {
        name: {code: position for position, code in enumerate(values)}
        for name, values in categories.items()
    }
    origin_code = indexes["origin"].get(origin)
    dest_code = indexes["dest"].get(dest)
    airline_code = indexes["airline"].get(airline)
    if origin_code is None or dest_code is None or airline_code is None:
        return None
    passengers = int(row["passengers"])
    distance = float(row["distance_weight"]) / passengers
    coupons = int(round(float(row["coupon_weight"]) / passengers))
    stops = int(round(float(row["stop_weight"]) / passengers))
    share = passengers / route_passengers
    matrix = design_matrix(
        np.array([origin_code]),
        np.array([dest_code]),
        np.array([airline_code]),
        np.array([distance], dtype=np.float32),
        np.array([quarter], dtype=np.float32),
        np.array([coupons], dtype=np.float32),
        np.array([stops], dtype=np.float32),
        np.array([share], dtype=np.float32),
    )
    if matrix.shape[1] != len(FEATURES):
        raise RuntimeError("Deal-score features do not match the trained model.")
    raw = np.column_stack([model.predict(matrix) for model in models])
    repaired = repair_quantiles(raw)
    offset = float(metadata["conformal_offset"])
    repaired[0, P10_INDEX] -= offset
    repaired[0, P90_INDEX] += offset
    return repair_quantiles(repaired)[0]


def deal_score(
    origin: str,
    destination: str,
    airline: str,
    quarter: int,
    fare: float,
    fare_kind: str = "sample",
) -> dict:
    if quarter not in {1, 2, 3, 4}:
        raise ValueError("Quarter must be 1, 2, 3, or 4.")
    if fare <= 0:
        raise ValueError("Fare must be greater than zero.")
    if fare_kind not in {"sample", "supplied"}:
        raise ValueError("Fare kind must be sample or supplied.")
    carrier = airline.strip().upper()
    if not DB_PATH.exists():
        return _empty("The paid-fare model is not installed.", fare_kind)
    try:
        origins = airport_codes(origin)
        destinations = airport_codes(destination)
    except ValueError:
        raise
    connection = connect()
    try:
        best = None
        route_seen = False
        for origin_code in origins:
            for dest_code in destinations:
                if origin_code == dest_code:
                    continue
                rows = _training_rows(connection, origin_code, dest_code)
                if not rows:
                    continue
                route_seen = True
                route_passengers = sum(int(row["passengers"]) for row in rows)
                chosen = next((row for row in rows if row["airline"] == carrier), None)
                if chosen is None:
                    continue
                if best is None or int(chosen["passengers"]) > int(best[2]["passengers"]):
                    best = (origin_code, dest_code, chosen, route_passengers)
    finally:
        connection.close()
    if best is None:
        note = AIRLINE_NOTE if route_seen else EMPTY_NOTE
        return _empty(note, fare_kind)
    origin_code, dest_code, row, route_passengers = best
    quantiles = _quantiles(origin_code, dest_code, carrier, quarter, row, route_passengers)
    if quantiles is None:
        return _empty("The paid-fare model is not installed.", fare_kind)
    percentile = round(fare_percentile(fare, quantiles), 1)
    passengers = int(row["passengers"])
    confidence = "low" if passengers < MIN_PASSENGERS else "normal"
    note = SAMPLE_NOTE if fare_kind == "sample" else SUPPLIED_NOTE
    if confidence == "low":
        note = (
            f"Low confidence. This airline has fewer than {MIN_PASSENGERS} training passengers on this route. "
            + note
        )
    return {
        "available": True,
        "origin": origin_code,
        "destination": dest_code,
        "airline": carrier,
        "quarter": quarter,
        "fare": round(float(fare), 2),
        "fare_kind": fare_kind,
        "percentile": percentile,
        "label": deal_label(percentile),
        "quantiles": {str(int(alpha * 100)): round(float(value), 2) for alpha, value in zip(ALPHAS, quantiles)},
        "passengers": passengers,
        "confidence": confidence,
        "source": SOURCE,
        "model_version": VERSION,
        "note": note,
    }


@lru_cache(maxsize=8192)
def sample_anchor(origin: str, dest: str, airline: str, quarter: int, stops: int) -> float | None:
    """Model median for a sample base fare, or None when the route is not covered.

    Airline medians use 2024 Q3 and 2024 Q4 only. A route median is used when
    that airline has no training tickets. Nothing is invented for a route with
    no training tickets at all.
    """
    if not DB_PATH.exists() or quarter not in {1, 2, 3, 4}:
        return None
    try:
        connection = connect()
        try:
            rows = _training_rows(connection, origin, dest)
            route_passengers = sum(int(row["passengers"]) for row in rows)
            chosen = next((row for row in rows if row["airline"] == airline), None)
            if chosen is not None and _boosters() is not None:
                quantiles = _quantiles_for_stops(origin, dest, airline, quarter, chosen, route_passengers, stops)
                if quantiles is not None:
                    return float(quantiles[3])
            if route_passengers <= 0:
                return None
            band = connection.execute(
                "SELECT mid FROM model_route_bands WHERE origin = ? AND dest = ? AND passengers > 0",
                (origin, dest),
            ).fetchone()
        finally:
            connection.close()
    except sqlite3.OperationalError:
        return None
    if band is None:
        return None
    return float(band["mid"])


def _quantiles_for_stops(origin, dest, airline, quarter, row, route_passengers, stops: int):
    loaded = _boosters()
    if loaded is None:
        return None
    models, metadata = loaded
    categories = metadata["categories"]
    indexes = {
        name: {code: position for position, code in enumerate(values)}
        for name, values in categories.items()
    }
    origin_code = indexes["origin"].get(origin)
    dest_code = indexes["dest"].get(dest)
    airline_code = indexes["airline"].get(airline)
    if origin_code is None or dest_code is None or airline_code is None:
        return None
    passengers = int(row["passengers"])
    if passengers <= 0 or route_passengers <= 0:
        return None
    distance = float(row["distance_weight"]) / passengers
    coupons = max(1, int(stops) + 1)
    share = passengers / route_passengers
    matrix = design_matrix(
        np.array([origin_code]),
        np.array([dest_code]),
        np.array([airline_code]),
        np.array([distance], dtype=np.float32),
        np.array([quarter], dtype=np.float32),
        np.array([coupons], dtype=np.float32),
        np.array([stops], dtype=np.float32),
        np.array([share], dtype=np.float32),
    )
    raw = np.column_stack([model.predict(matrix) for model in models])
    repaired = repair_quantiles(raw)
    offset = float(metadata["conformal_offset"])
    repaired[0, P10_INDEX] -= offset
    repaired[0, P90_INDEX] += offset
    return repair_quantiles(repaired)[0]
