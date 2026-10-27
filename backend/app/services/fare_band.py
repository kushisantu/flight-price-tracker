"""Paid-fare range from the empirical DOT table.

Numbers come from 2024 Q3 through 2025 Q1. They are not a forecast, and they
are not the sample fare board.
"""

from __future__ import annotations

from pathlib import Path

from app.catalog import AIRPORTS, CITIES
from app.services.db1b import DB_PATH, SOURCE, connect, known_airport
from app.services.empirical import VERSION, lookup_prediction, prediction_note
from app.services.phase2 import VERSION as MODEL_VERSION
from app.services.phase2 import model_note

MODEL_DIR = Path(__file__).resolve().parents[1] / "fare_model"
EMPTY_NOTE = "No DOT ticket sample covers this route. The flight board still uses the sample fare model."


def _empty(note: str = EMPTY_NOTE) -> dict:
    return {
        "available": False,
        "low": None,
        "mid": None,
        "high": None,
        "confidence": None,
        "slice": None,
        "passengers": 0,
        "source": SOURCE,
        "model_version": VERSION,
        "note": note,
    }


def airport_codes(code: str) -> list[str]:
    key = (code or "").strip().upper()
    if key in CITIES:
        return list(CITIES[key]["airports"])
    if key in AIRPORTS or known_airport(key):
        return [key]
    raise ValueError(f"No airport or city matches {key}.")


def _model_ready(connection) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'model_route_bands'"
    ).fetchone()
    if row is None:
        return False
    count = connection.execute("SELECT COUNT(*) AS n FROM model_route_bands").fetchone()["n"]
    return int(count) > 0


def _from_model(connection, origins: list[str], destinations: list[str]) -> dict:
    chosen = []
    for origin_code in origins:
        for dest_code in destinations:
            if origin_code == dest_code:
                continue
            row = connection.execute(
                """
                SELECT passengers, low, mid, high, confidence
                FROM model_route_bands
                WHERE origin = ? AND dest = ?
                """,
                (origin_code, dest_code),
            ).fetchone()
            if row is not None and int(row["passengers"]) > 0:
                chosen.append(row)
    if not chosen:
        payload = _empty()
        payload["model_version"] = MODEL_VERSION
        payload["estimate"] = "model"
        return payload
    weight = sum(int(row["passengers"]) for row in chosen)
    low = int(round(sum(int(row["low"]) * int(row["passengers"]) for row in chosen) / weight))
    mid = int(round(sum(int(row["mid"]) * int(row["passengers"]) for row in chosen) / weight))
    high = int(round(sum(int(row["high"]) * int(row["passengers"]) for row in chosen) / weight))
    if mid < low:
        mid = low
    if high < mid:
        high = mid
    confidence = "low" if any(row["confidence"] == "low" for row in chosen) else "normal"
    return {
        "available": True,
        "low": low,
        "mid": mid,
        "high": high,
        "confidence": confidence,
        "slice": "model",
        "passengers": int(weight),
        "source": SOURCE,
        "model_version": MODEL_VERSION,
        "estimate": "model",
        "note": model_note(low, high, confidence),
    }


def paid_fare_band(origin: str, destination: str) -> dict:
    origins = airport_codes(origin)
    destinations = airport_codes(destination)
    if not DB_PATH.exists():
        return _empty("The paid-fare table is not installed. The flight board still uses the sample fare model.")
    connection = connect()
    try:
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'route_quantiles'"
        ).fetchone()
        if _model_ready(connection):
            return _from_model(connection, origins, destinations)
        if table is None:
            return _empty("The paid-fare table is not installed. The flight board still uses the sample fare model.")
        chosen = []
        for origin_code in origins:
            for dest_code in destinations:
                if origin_code == dest_code:
                    continue
                predicted = lookup_prediction(connection, origin_code, dest_code)
                if predicted is not None:
                    chosen.append(predicted)
    finally:
        connection.close()
    if not chosen:
        return _empty()

    weight = sum(item["route_passengers"] for item in chosen)
    if weight <= 0:
        return _empty()
    low = int(round(sum(item["low"] * item["route_passengers"] for item in chosen) / weight))
    mid = int(round(sum(item["mid"] * item["route_passengers"] for item in chosen) / weight))
    high = int(round(sum(item["high"] * item["route_passengers"] for item in chosen) / weight))
    if mid < low:
        mid = low
    if high < mid:
        high = mid
    slices = {item["slice"] for item in chosen}
    slice_name = next(iter(slices)) if len(slices) == 1 else "mixed"
    confidence = "low" if any(item["confidence"] == "low" for item in chosen) else "normal"
    if slice_name == "mixed":
        label = "a mix of this airport pair and a broader DOT slice"
    else:
        label = chosen[0]["label"] if len(chosen) == 1 else "these airport pairs"
        if slice_name != "route":
            label = chosen[0]["label"]
    return {
        "available": True,
        "low": low,
        "mid": mid,
        "high": high,
        "confidence": confidence,
        "slice": slice_name,
        "passengers": int(weight),
        "source": SOURCE,
        "model_version": VERSION,
        "note": prediction_note(low, high, confidence, label),
    }
