"""LightGBM paid-fare quantiles for Phase 2.

The final model trains on 2024 Q3 and 2024 Q4 only. 2025 Q1 is used to choose
the conformal adjustment. 2025 Q2 is the holdout and is never a training row.
DB1B market rows are directional; there is no round-trip flag to invent.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from app.services.db1b import SOURCE

PHASE2_DIR = Path(__file__).resolve().parents[1] / "fare_model" / "phase2"

SEED = 1
MIN_PASSENGERS = 50
VERSION = "lgbm-2024q3-2024q4"
ALPHAS = (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95)
FEATURES = (
    "origin",
    "dest",
    "airline",
    "distance",
    "quarter",
    "coupons",
    "stops",
    "nonstop",
    "carrier_share",
)
CATEGORICAL = (0, 1, 2)
P10_INDEX = 1
P50_INDEX = 3
P90_INDEX = 5
FINAL_TRAIN = ((2024, 3), (2024, 4))
CALIBRATION = (2025, 1)
COVERAGE_LEVEL = 0.80
SHAP_ROWS = 2000

np.random.seed(SEED)


def is_final_training(year: int, quarter: int) -> bool:
    return (int(year), int(quarter)) in FINAL_TRAIN


def repair_quantiles(values: np.ndarray) -> np.ndarray:
    """Sort quantile columns so a lower percentile cannot sit above a higher one."""
    return np.sort(np.asarray(values, dtype=np.float64), axis=-1)


def weighted_quantile(values: np.ndarray, weights: np.ndarray, probability: float) -> float:
    order = np.argsort(values, kind="mergesort")
    cumulative = np.cumsum(weights[order].astype(np.float64))
    total = float(cumulative[-1])
    if total <= 0:
        raise ValueError("Quantile weights must be positive.")
    index = int(np.searchsorted(cumulative, probability * total, side="left"))
    index = min(index, len(order) - 1)
    return float(values[order][index])


def conformity_scores(actual: np.ndarray, low: np.ndarray, high: np.ndarray) -> np.ndarray:
    return np.maximum(low - actual, actual - high)


def conformal_offset(scores: np.ndarray, weights: np.ndarray, level: float = COVERAGE_LEVEL) -> float:
    return weighted_quantile(scores, weights, level)


def widen_band(repaired: np.ndarray, offset: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Apply the conformal shift to the 10th and 90th percentiles and keep the median inside."""
    low = repaired[..., P10_INDEX] - offset
    mid = repaired[..., P50_INDEX]
    high = repaired[..., P90_INDEX] + offset
    low = np.minimum(low, mid)
    high = np.maximum(high, mid)
    return low, mid, high


def carrier_share_feature(
    origin: np.ndarray,
    dest: np.ndarray,
    airline: np.ndarray,
    passengers: np.ndarray,
    mask: np.ndarray,
    n_origin: int,
    n_dest: int,
    n_airline: int,
) -> np.ndarray:
    """Airline share of route passengers, counted only on rows where mask is true.

    Later rows still receive that training share. They do not add to it.
    """
    origin = origin.astype(np.int64, copy=False)
    dest = dest.astype(np.int64, copy=False)
    airline = airline.astype(np.int64, copy=False)
    weight = passengers.astype(np.float64, copy=False)
    span = n_dest * n_airline
    key = origin * span + dest * n_airline + airline
    route_key = origin * n_dest + dest
    train_weight = weight[mask]
    pair_counts = np.bincount(key[mask], weights=train_weight, minlength=n_origin * span)
    route_counts = np.bincount(route_key[mask], weights=train_weight, minlength=n_origin * n_dest)
    route = route_counts[route_key]
    share = np.zeros(len(key), dtype=np.float32)
    np.divide(pair_counts[key], route, out=share, where=route > 0)
    return share


def design_matrix(
    origin: np.ndarray,
    dest: np.ndarray,
    airline: np.ndarray,
    distance: np.ndarray,
    quarter: np.ndarray,
    coupons: np.ndarray,
    stops: np.ndarray,
    share: np.ndarray,
) -> np.ndarray:
    matrix = np.empty((len(distance), len(FEATURES)), dtype=np.float32)
    matrix[:, 0] = origin
    matrix[:, 1] = dest
    matrix[:, 2] = airline
    matrix[:, 3] = distance
    matrix[:, 4] = quarter
    matrix[:, 5] = coupons
    matrix[:, 6] = stops
    matrix[:, 7] = (coupons == 1).astype(np.float32)
    matrix[:, 8] = share
    return matrix


def aggregate_route_quantiles(
    quantiles: np.ndarray,
    passengers: np.ndarray,
    route_ids: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Passenger-weighted mean of each route, repaired so the columns stay ordered."""
    repaired = repair_quantiles(quantiles)
    if len(route_ids) == 0:
        return np.zeros((0, repaired.shape[1])), np.zeros(0)
    n_routes = int(route_ids.max()) + 1
    weight = np.asarray(passengers, dtype=np.float64)
    totals = np.bincount(route_ids, weights=weight, minlength=n_routes)
    stacked = np.column_stack(
        [
            np.bincount(route_ids, weights=repaired[:, column] * weight, minlength=n_routes)
            for column in range(repaired.shape[1])
        ]
    )
    means = np.zeros_like(stacked)
    np.divide(stacked, totals[:, None], out=means, where=totals[:, None] > 0)
    return repair_quantiles(means), totals


def volume_tier(passengers: int) -> str:
    if passengers <= 0:
        return "no_training_route"
    if passengers < MIN_PASSENGERS:
        return "under_50"
    if passengers < 500:
        return "50_499"
    if passengers < 5000:
        return "500_4999"
    return "5000_plus"


def fare_percentile(fare: float, quantiles: np.ndarray, alphas: tuple[float, ...] = ALPHAS) -> float:
    """Where this fare sits in the predicted distribution, from 0 to 100.

    The score is linear between neighboring quantiles. Below the lowest quantile
    it fades toward 0, and above the highest it fades toward 100.
    """
    levels = [float(value) for value in quantiles]
    percents = [alpha * 100 for alpha in alphas]
    if fare <= levels[0]:
        if levels[0] <= 0:
            return 0.0
        return percents[0] * max(fare, 0.0) / levels[0]
    if fare >= levels[-1]:
        span = levels[-1]
        if span <= 0:
            return 100.0
        extra = (100 - percents[-1]) * min(1.0, (fare - levels[-1]) / span)
        return min(100.0, percents[-1] + extra)
    for index in range(len(levels) - 1):
        if fare <= levels[index + 1]:
            width = levels[index + 1] - levels[index]
            if width <= 0:
                return percents[index + 1]
            fraction = (fare - levels[index]) / width
            return percents[index] + fraction * (percents[index + 1] - percents[index])
    return percents[-1]


def deal_label(percentile: float) -> str:
    if percentile <= 10:
        return "Great"
    if percentile <= 25:
        return "Good"
    if percentile <= 75:
        return "Typical"
    return "High"


def model_note(low: int, high: int, confidence: str) -> str:
    base = (
        f"LightGBM quantile model for this airport pair, {SOURCE}, {VERSION}. "
        "Trained on 2024 Q3 through 2024 Q4 tickets. "
        "The 10th to 90th percentile is shifted by a conformal adjustment fit on 2025 Q1. "
        f"Displayed range ${low:,}–${high:,}. "
        "Each row is a directional market. This is not a booking-date forecast."
    )
    if confidence == "low":
        return (
            f"Low confidence. This route has fewer than {MIN_PASSENGERS} passengers in the training quarters. "
            + base
        )
    return base
