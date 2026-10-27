"""Score the empirical table and the baselines on the 2025 Q2 holdout."""

from __future__ import annotations

import json
from datetime import date, timedelta
from functools import lru_cache

import numpy as np

from app.catalog import AIRLINES, AIRPORTS
from app.services.db1b import HOLDOUT, connect
from app.services.empirical import SEED, VERSION, load_indexes, predict_cached
from app.services.fare_band import MODEL_DIR
from app.services.simulator import fare_on

MIDPOINT = {1: (2, 15), 2: (5, 15), 3: (8, 15), 4: (11, 15)}


def _airlines(connection) -> list[str]:
    rows = connection.execute(
        """
        SELECT airline FROM market_fares
        WHERE NOT (year = ? AND quarter = ?)
        GROUP BY airline
        ORDER BY airline
        """,
        HOLDOUT,
    ).fetchall()
    return [row["airline"] for row in rows]


def _fit_linear(connection, airlines: list[str]) -> np.ndarray:
    width = 4 + max(len(airlines) - 1, 0)
    gram = np.zeros((width, width), dtype=np.float64)
    target = np.zeros(width, dtype=np.float64)
    index = {code: position for position, code in enumerate(airlines)}

    def design(rows) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        count = len(rows)
        matrix = np.ones((count, width), dtype=np.float64)
        fare = np.empty(count, dtype=np.float64)
        weight = np.empty(count, dtype=np.float64)
        for cursor, row in enumerate(rows):
            matrix[cursor, 1] = row["distance"] / 1000.0
            matrix[cursor, 2] = row["year"] - 2024
            matrix[cursor, 3] = row["quarter"]
            code = index.get(row["airline"])
            if code:
                matrix[cursor, 3 + code] = 1.0
            fare[cursor] = row["fare"]
            weight[cursor] = row["passengers"]
        return matrix, fare, weight

    cursor = connection.execute(
        """
        SELECT airline, distance, year, quarter, fare, passengers
        FROM market_fares
        WHERE NOT (year = ? AND quarter = ?)
        """,
        HOLDOUT,
    )
    batch = []
    seen = 0
    while True:
        row = cursor.fetchone()
        if row is not None:
            batch.append(row)
        if len(batch) >= 200_000 or (row is None and batch):
            matrix, fare, weight = design(batch)
            scale = np.sqrt(weight)[:, None]
            weighted = matrix * scale
            gram += weighted.T @ weighted
            target += weighted.T @ (fare * scale[:, 0])
            seen += len(batch)
            batch = []
            if seen % 1_000_000 < 200_000:
                print(f"  linear fit rows {seen:,}", flush=True)
        if row is None:
            break
    coefficients, *_ = np.linalg.lstsq(gram, target, rcond=None)
    return coefficients, index, width


def _linear_price(coefficients: np.ndarray, index: dict[str, int], width: int, row) -> float:
    features = np.ones(width, dtype=np.float64)
    features[1] = row["distance"] / 1000.0
    features[2] = row["year"] - 2024
    features[3] = row["quarter"]
    code = index.get(row["airline"])
    if code:
        features[3 + code] = 1.0
    return float(features @ coefficients)


@lru_cache(maxsize=None)
def _formula(origin: str, dest: str, airline: str, stops: int) -> int | None:
    if origin not in AIRPORTS or dest not in AIRPORTS or airline not in AIRLINES:
        return None
    year, quarter = HOLDOUT
    month, day = MIDPOINT[quarter]
    depart = date(year, month, day)
    observed = depart - timedelta(days=45)
    return fare_on(origin, dest, airline, 1 if stops else 0, "economy", depart, observed, 1)


def _mae(error: float, weight: float) -> float | None:
    if weight <= 0:
        return None
    return error / weight


def main() -> None:
    np.random.seed(SEED)
    connection = connect()
    try:
        routes, slices = load_indexes(connection)
        if not routes:
            raise SystemExit("Run python -m scripts.train first.")
        print("fitting linear baseline", flush=True)
        coefficients, airline_index, width = _fit_linear(connection, _airlines(connection))
        print("scoring holdout", flush=True)
        population = {"weight": 0.0, "empirical": 0.0, "route": 0.0, "linear": 0.0, "covered": 0.0, "rows": 0}
        comparable = {
            "weight": 0.0,
            "empirical": 0.0,
            "route": 0.0,
            "linear": 0.0,
            "formula": 0.0,
            "covered": 0.0,
            "rows": 0,
        }
        cursor = connection.execute(
            """
            SELECT origin, dest, airline, distance, year, quarter, fare, passengers, stops
            FROM market_fares
            WHERE year = ? AND quarter = ?
            """,
            HOLDOUT,
        )
        scanned = 0
        for row in cursor:
            scanned += 1
            if scanned % 1_000_000 == 0:
                print(f"  holdout rows {scanned:,}", flush=True)
            predicted = predict_cached(routes, slices, row["origin"], row["dest"])
            if predicted is None:
                continue
            weight = float(row["passengers"])
            fare = float(row["fare"])
            empirical_error = abs(predicted["mid"] - fare) * weight
            route_error = abs(predicted["mean_fare"] - fare) * weight
            linear_error = abs(_linear_price(coefficients, airline_index, width, row) - fare) * weight
            covered = weight if predicted["low"] <= fare <= predicted["high"] else 0.0
            for bucket in (population,):
                bucket["weight"] += weight
                bucket["empirical"] += empirical_error
                bucket["route"] += route_error
                bucket["linear"] += linear_error
                bucket["covered"] += covered
                bucket["rows"] += 1
            formula = _formula(row["origin"], row["dest"], row["airline"], int(row["stops"]))
            if formula is None:
                continue
            comparable["weight"] += weight
            comparable["empirical"] += empirical_error
            comparable["route"] += route_error
            comparable["linear"] += linear_error
            comparable["formula"] += abs(formula - fare) * weight
            comparable["covered"] += covered
            comparable["rows"] += 1
    finally:
        connection.close()

    def pack(bucket: dict, include_formula: bool) -> dict:
        packed = {
            "rows": bucket["rows"],
            "empirical_mae": None if _mae(bucket["empirical"], bucket["weight"]) is None else round(_mae(bucket["empirical"], bucket["weight"]), 2),
            "route_average_mae": None if _mae(bucket["route"], bucket["weight"]) is None else round(_mae(bucket["route"], bucket["weight"]), 2),
            "linear_mae": None if _mae(bucket["linear"], bucket["weight"]) is None else round(_mae(bucket["linear"], bucket["weight"]), 2),
            "interval_coverage": None if bucket["weight"] <= 0 else round(bucket["covered"] / bucket["weight"], 4),
        }
        if include_formula:
            packed["formula_mae"] = None if _mae(bucket["formula"], bucket["weight"]) is None else round(_mae(bucket["formula"], bucket["weight"]), 2)
        return packed

    metrics = {
        "version": VERSION,
        "source": "US DOT DB1B Market",
        "holdout": f"{HOLDOUT[0]}Q{HOLDOUT[1]}",
        "train_periods": ["2024Q3", "2024Q4", "2025Q1"],
        "seed": SEED,
        "min_passengers": 50,
        "population": pack(population, False),
        "formula_comparable": pack(comparable, True),
    }
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    path = MODEL_DIR / "phase1_metrics.json"
    path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2), flush=True)
    print(f"wrote {path}", flush=True)


if __name__ == "__main__":
    main()
