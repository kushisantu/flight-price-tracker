"""Paid-fare range from the DOT model.

The numbers are a passenger-weighted 10th to 90th percentile for the latest
quarter the model was tested on. They are not a forecast of a future listing.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from app.catalog import get_place
from app.services.db1b import SOURCE

MODEL_DIR = Path(__file__).resolve().parents[1] / "fare_model"
EMPTY_NOTE = "No DOT ticket sample covers this route. The flight board still uses the sample fare model."


def _empty(version: str | None, note: str = EMPTY_NOTE) -> dict:
    return {
        "available": False,
        "low": None,
        "mid": None,
        "high": None,
        "year": None,
        "quarter": None,
        "passengers": 0,
        "source": SOURCE,
        "model_version": version,
        "note": note,
    }


@lru_cache(maxsize=1)
def _load_bundle(stamp: float) -> dict:
    del stamp
    metadata = json.loads((MODEL_DIR / "metadata.json").read_text(encoding="utf-8"))
    import lightgbm as lgb

    boosters = {
        name: lgb.Booster(model_file=str(MODEL_DIR / filename))
        for name, filename in (("p10", "quantile_10.txt"), ("p50", "quantile_50.txt"), ("p90", "quantile_90.txt"))
    }
    categories = metadata["categories"]
    return {
        "metadata": metadata,
        "boosters": boosters,
        "indexes": {name: {code: index for index, code in enumerate(levels)} for name, levels in categories.items()},
    }


def _bundle() -> dict | None:
    meta_path = MODEL_DIR / "metadata.json"
    if not meta_path.exists():
        return None
    return _load_bundle(meta_path.stat().st_mtime)


def _predict(bundle: dict, origin: str, dest: str, airline: str, distance: float, year: int, quarter: int):
    indexes = bundle["indexes"]
    try:
        row = np.array(
            [[
                indexes["origin"][origin],
                indexes["dest"][dest],
                indexes["airline"][airline],
                distance,
                year,
                quarter,
            ]],
            dtype=np.float64,
        )
    except KeyError:
        return None
    boosters = bundle["boosters"]
    return (
        float(boosters["p10"].predict(row)[0]),
        float(boosters["p50"].predict(row)[0]),
        float(boosters["p90"].predict(row)[0]),
    )


def paid_fare_band(origin: str, destination: str) -> dict:
    origin_place = get_place(origin)
    dest_place = get_place(destination)
    bundle = _bundle()
    if bundle is None:
        return _empty(None, "The paid-fare model is not installed. The flight board still uses the sample fare model.")

    metadata = bundle["metadata"]
    version = metadata["version"]
    year = int(metadata["predict_year"])
    quarter = int(metadata["predict_quarter"])
    routes = metadata["routes"]

    low_total = mid_total = high_total = weight = 0.0
    for origin_code in origin_place["airports"]:
        for dest_code in dest_place["airports"]:
            route = routes.get(f"{origin_code}-{dest_code}")
            if not route:
                continue
            for airline in route["airlines"]:
                predicted = _predict(
                    bundle,
                    origin_code,
                    dest_code,
                    airline["code"],
                    float(airline["distance"]),
                    year,
                    quarter,
                )
                if predicted is None:
                    continue
                passengers = float(airline["passengers"])
                if passengers <= 0:
                    continue
                low, mid, high = predicted
                low_total += low * passengers
                mid_total += mid * passengers
                high_total += high * passengers
                weight += passengers

    if weight <= 0:
        return _empty(version)

    low = int(round(low_total / weight))
    mid = int(round(mid_total / weight))
    high = int(round(high_total / weight))
    if high <= low:
        high = low + 1
    if mid < low:
        mid = low
    if mid > high:
        mid = high
    return {
        "available": True,
        "low": low,
        "mid": mid,
        "high": high,
        "year": year,
        "quarter": quarter,
        "passengers": int(round(weight)),
        "source": SOURCE,
        "model_version": version,
        "note": (
            f"Real US tickets for this route usually paid ${low:,}–${high:,}. "
            f"Model {version} on {SOURCE}, {year} Q{quarter}. "
            "The range is the passenger-weighted 10th to 90th percentile across airlines. "
            "It is not a forecast of a future listing."
        ),
    }
