"""Train paid-fare quantiles on DB1B rows, with baselines on a later quarter.

Train quarters are every loaded quarter except the newest. The newest quarter
is only used for metrics and for the airline mix shown in the app.
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import lightgbm as lgb
import numpy as np

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.catalog import AIRLINES  # noqa: E402
from app.services.db1b import DB_PATH, SOURCE, connect, ensure_schema  # noqa: E402
from app.services.fare_band import MODEL_DIR  # noqa: E402
from app.services.simulator import fare_on  # noqa: E402

MIDPOINT = {1: (2, 15), 2: (5, 15), 3: (8, 15), 4: (11, 15)}
ROUNDS = 100


def _periods(connection):
    rows = connection.execute(
        "SELECT DISTINCT year, quarter FROM market_fares ORDER BY year, quarter"
    ).fetchall()
    if len(rows) < 2:
        raise SystemExit("Need at least two quarters so the latest one can be held out.")
    return [(int(row["year"]), int(row["quarter"])) for row in rows]


def _distinct(connection, column: str, test_year: int, test_quarter: int) -> list[str]:
    rows = connection.execute(
        f"""
        SELECT DISTINCT {column} AS value
        FROM market_fares
        WHERE NOT (year = ? AND quarter = ?)
        ORDER BY value
        """,
        (test_year, test_quarter),
    ).fetchall()
    return [row["value"] for row in rows]


def _arrays(connection, levels: dict[str, list[str]]):
    count = int(connection.execute("SELECT COUNT(*) AS n FROM market_fares").fetchone()["n"])
    if count == 0:
        raise SystemExit(f"No fares in {DB_PATH}. Run scripts/load_db1b.py first.")
    indexes = {name: {code: position for position, code in enumerate(values)} for name, values in levels.items()}
    year = np.empty(count, dtype=np.int16)
    quarter = np.empty(count, dtype=np.int8)
    origin = np.empty(count, dtype=np.int16)
    dest = np.empty(count, dtype=np.int16)
    airline = np.empty(count, dtype=np.int16)
    distance = np.empty(count, dtype=np.float32)
    passengers = np.empty(count, dtype=np.float32)
    fare = np.empty(count, dtype=np.float32)
    stops = np.empty(count, dtype=np.int8)
    cursor = connection.execute(
        """
        SELECT year, quarter, origin, dest, airline, distance, passengers, fare, stops
        FROM market_fares
        """
    )
    for index, row in enumerate(cursor):
        year[index] = row["year"]
        quarter[index] = row["quarter"]
        origin[index] = indexes["origin"].get(row["origin"], -1)
        dest[index] = indexes["dest"].get(row["dest"], -1)
        airline[index] = indexes["airline"].get(row["airline"], -1)
        distance[index] = row["distance"]
        passengers[index] = row["passengers"]
        fare[index] = row["fare"]
        stops[index] = row["stops"]
    return {
        "year": year,
        "quarter": quarter,
        "origin": origin,
        "dest": dest,
        "airline": airline,
        "distance": distance,
        "passengers": passengers,
        "fare": fare,
        "stops": stops,
    }


def _weighted_mae(actual, predicted, weight) -> float:
    return float(np.average(np.abs(actual - predicted), weights=weight))


def _route_average(frame, train, test) -> float:
    pair = frame["origin"].astype(np.int32) * 256 + frame["dest"].astype(np.int32)
    fare = frame["fare"]
    weight = frame["passengers"]
    global_mean = float(np.average(fare[train], weights=weight[train]))
    summed = np.bincount(pair[train], weights=fare[train] * weight[train], minlength=256 * 256)
    totals = np.bincount(pair[train], weights=weight[train], minlength=256 * 256)
    means = np.full(256 * 256, global_mean, dtype=np.float64)
    np.divide(summed, totals, out=means, where=totals > 0)
    return _weighted_mae(fare[test], means[pair[test]], weight[test])


def _linear_mae(frame, train, test, airline_count: int) -> float:
    width = 4 + max(airline_count - 1, 0)
    gram = np.zeros((width, width), dtype=np.float64)
    target = np.zeros(width, dtype=np.float64)
    indexes = np.flatnonzero(train)

    def design(chosen):
        matrix = np.ones((chosen.size, width), dtype=np.float64)
        matrix[:, 1] = frame["distance"][chosen] / 1000.0
        matrix[:, 2] = frame["year"][chosen]
        matrix[:, 3] = frame["quarter"][chosen]
        codes = frame["airline"][chosen]
        for code in range(1, airline_count):
            matrix[:, 3 + code] = codes == code
        return matrix

    for start in range(0, indexes.size, 250_000):
        chosen = indexes[start:start + 250_000]
        matrix = design(chosen)
        scale = np.sqrt(frame["passengers"][chosen])[:, None]
        weighted = matrix * scale
        gram += weighted.T @ weighted
        target += weighted.T @ (frame["fare"][chosen] * scale[:, 0])
    coefficients = np.linalg.solve(gram, target)

    actual = []
    predicted = []
    weights = []
    test_indexes = np.flatnonzero(test)
    for start in range(0, test_indexes.size, 250_000):
        chosen = test_indexes[start:start + 250_000]
        actual.append(frame["fare"][chosen])
        predicted.append(design(chosen) @ coefficients)
        weights.append(frame["passengers"][chosen])
    return _weighted_mae(np.concatenate(actual), np.concatenate(predicted), np.concatenate(weights))


@lru_cache(maxsize=None)
def _formula(origin: str, dest: str, airline: str, stops: int, year: int, quarter: int) -> int | None:
    if airline not in AIRLINES:
        return None
    month, day = MIDPOINT[quarter]
    depart = date(year, month, day)
    observed = depart - timedelta(days=45)
    return fare_on(origin, dest, airline, 1 if stops else 0, "economy", depart, observed, 1)


def _formula_mae(frame, test, levels) -> tuple[float | None, int]:
    error = 0.0
    weight = 0.0
    rows = 0
    origins = levels["origin"]
    dests = levels["dest"]
    airlines = levels["airline"]
    for index in np.flatnonzero(test):
        price = _formula(
            origins[int(frame["origin"][index])],
            dests[int(frame["dest"][index])],
            airlines[int(frame["airline"][index])],
            int(frame["stops"][index]),
            int(frame["year"][index]),
            int(frame["quarter"][index]),
        )
        if price is None:
            continue
        passengers = float(frame["passengers"][index])
        error += abs(price - float(frame["fare"][index])) * passengers
        weight += passengers
        rows += 1
    if weight <= 0:
        return None, 0
    return error / weight, rows


def _matrix(frame, mask) -> np.ndarray:
    chosen = np.flatnonzero(mask)
    matrix = np.empty((chosen.size, 6), dtype=np.float32)
    matrix[:, 0] = frame["origin"][chosen]
    matrix[:, 1] = frame["dest"][chosen]
    matrix[:, 2] = frame["airline"][chosen]
    matrix[:, 3] = frame["distance"][chosen]
    matrix[:, 4] = frame["year"][chosen]
    matrix[:, 5] = frame["quarter"][chosen]
    return matrix


def _fit_quantile(train_x, train_y, train_w, alpha: float) -> lgb.Booster:
    dataset = lgb.Dataset(
        train_x,
        label=train_y,
        weight=train_w,
        categorical_feature=[0, 1, 2],
        free_raw_data=False,
    )
    return lgb.train(
        {
            "objective": "quantile",
            "alpha": alpha,
            "learning_rate": 0.1,
            "num_leaves": 31,
            "min_data_in_leaf": 80,
            "verbosity": -1,
            "seed": 1,
            "num_threads": 4,
        },
        dataset,
        num_boost_round=ROUNDS,
    )


def _routes(connection, test_year: int, test_quarter: int, airlines: set[str]) -> dict:
    rows = connection.execute(
        """
        SELECT origin, dest, airline,
               SUM(passengers) AS passengers,
               SUM(distance * passengers) / SUM(passengers) AS distance
        FROM market_fares
        WHERE year = ? AND quarter = ?
        GROUP BY origin, dest, airline
        """,
        (test_year, test_quarter),
    ).fetchall()
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        if row["airline"] not in airlines:
            continue
        grouped.setdefault(f"{row['origin']}-{row['dest']}", []).append({
            "code": row["airline"],
            "passengers": int(row["passengers"]),
            "distance": round(float(row["distance"]), 1),
        })
    return {key: {"airlines": items} for key, items in grouped.items() if items}


def main() -> None:
    connection = connect(DB_PATH)
    try:
        ensure_schema(connection)
        periods = _periods(connection)
        test_year, test_quarter = periods[-1]
        levels = {
            "origin": _distinct(connection, "origin", test_year, test_quarter),
            "dest": _distinct(connection, "dest", test_year, test_quarter),
            "airline": _distinct(connection, "airline", test_year, test_quarter),
        }
        frame = _arrays(connection, levels)
        routes = _routes(connection, test_year, test_quarter, set(levels["airline"]))
    finally:
        connection.close()

    period = frame["year"].astype(np.int32) * 4 + frame["quarter"].astype(np.int32)
    latest = int(period.max())
    known = (frame["origin"] >= 0) & (frame["dest"] >= 0) & (frame["airline"] >= 0)
    train = (period < latest) & known
    test = (period == latest) & known
    print(f"train rows {int(train.sum()):,}  test rows {int(test.sum()):,}", flush=True)

    route_mae = _route_average(frame, train, test)
    linear_mae = _linear_mae(frame, train, test, len(levels["airline"]))
    formula_mae, formula_rows = _formula_mae(frame, test, levels)
    print(
        f"baseline MAE route={route_mae:.1f} linear={linear_mae:.1f} formula={formula_mae}",
        flush=True,
    )

    train_x = _matrix(frame, train)
    test_x = _matrix(frame, test)
    train_y = frame["fare"][train]
    test_y = frame["fare"][test]
    train_w = frame["passengers"][train]
    test_w = frame["passengers"][test]
    model_p10 = _fit_quantile(train_x, train_y, train_w, 0.1)
    model_p50 = _fit_quantile(train_x, train_y, train_w, 0.5)
    model_p90 = _fit_quantile(train_x, train_y, train_w, 0.9)
    pred_p10 = model_p10.predict(test_x)
    pred_p50 = model_p50.predict(test_x)
    pred_p90 = model_p90.predict(test_x)
    coverage = float(np.average((test_y >= pred_p10) & (test_y <= pred_p90), weights=test_w))
    width = float(np.median(pred_p90 - pred_p10))
    median_mae = _weighted_mae(test_y, pred_p50, test_w)
    print(f"lgbm MAE={median_mae:.1f} coverage={coverage:.3f} median width={width:.1f}", flush=True)
    if width <= 1:
        raise SystemExit("The 10–90 band collapsed to a point. Refusing to save it.")
    if not (float(np.mean(pred_p10)) < float(np.mean(pred_p50)) < float(np.mean(pred_p90))):
        raise SystemExit("Quantile models are out of order.")

    train_periods = [f"{year}Q{quarter}" for year, quarter in periods[:-1]]
    version = f"db1b-{train_periods[0].lower()}-{test_year}q{test_quarter}"
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model_p10.save_model(str(MODEL_DIR / "quantile_10.txt"))
    model_p50.save_model(str(MODEL_DIR / "quantile_50.txt"))
    model_p90.save_model(str(MODEL_DIR / "quantile_90.txt"))
    metadata = {
        "version": version,
        "source": SOURCE,
        "predict_year": test_year,
        "predict_quarter": test_quarter,
        "train_periods": train_periods,
        "test_period": f"{test_year}Q{test_quarter}",
        "features": ["origin", "dest", "airline", "distance", "year", "quarter"],
        "categories": levels,
        "metrics": {
            "route_average_mae": round(route_mae, 2),
            "linear_mae": round(linear_mae, 2),
            "formula_mae": None if formula_mae is None else round(formula_mae, 2),
            "formula_rows": formula_rows,
            "lgbm_p50_mae": round(median_mae, 2),
            "interval_coverage": round(coverage, 4),
            "median_band_width": round(width, 2),
            "test_rows": int(test.sum()),
            "train_rows": int(train.sum()),
        },
        "routes": routes,
    }
    (MODEL_DIR / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    print(f"saved {version} to {MODEL_DIR}", flush=True)


if __name__ == "__main__":
    main()
