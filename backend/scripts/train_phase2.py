"""Fit seven LightGBM quantile models on 2024 Q3–Q4 and calibrate on 2025 Q1.

The whitelist-era boosters in app/fare_model stay where they are. New files go
in app/fare_model/phase2. 2025 Q2 is not read.
"""

from __future__ import annotations

import json
import os

import lightgbm as lgb
import mlflow
import numpy as np

from app.config import BACKEND_DIR
from app.services.db1b import DB_PATH, SOURCE, connect
from app.services.phase2 import (
    ALPHAS,
    CALIBRATION,
    CATEGORICAL,
    COVERAGE_LEVEL,
    FEATURES,
    FINAL_TRAIN,
    PHASE2_DIR,
    P50_INDEX,
    SEED,
    SHAP_ROWS,
    VERSION,
    aggregate_route_quantiles,
    carrier_share_feature,
    conformity_scores,
    conformal_offset,
    design_matrix,
    repair_quantiles,
    widen_band,
)

MAX_ROUNDS = 120
EARLY_STOP = 25
GRID = (
    {"name": "leaves31", "learning_rate": 0.1, "num_leaves": 31, "min_data_in_leaf": 80},
    {"name": "leaves63", "learning_rate": 0.05, "num_leaves": 63, "min_data_in_leaf": 120},
)


def _params(alpha: float, config: dict) -> dict:
    threads = max(4, min(8, os.cpu_count() or 4))
    return {
        "objective": "quantile",
        "alpha": alpha,
        "metric": "quantile",
        "learning_rate": config["learning_rate"],
        "num_leaves": config["num_leaves"],
        "min_data_in_leaf": config["min_data_in_leaf"],
        "verbosity": -1,
        "seed": SEED,
        "bagging_seed": SEED,
        "feature_fraction_seed": SEED,
        "data_random_seed": SEED,
        "num_threads": threads,
        "force_col_wise": True,
        "deterministic": False,
    }


def _categories(connection) -> dict[str, list[str]]:
    found = {}
    for column in ("origin", "dest", "airline"):
        rows = connection.execute(
            f"""
            SELECT DISTINCT {column} AS value
            FROM market_fares
            WHERE year = 2024 AND quarter IN (3, 4)
            ORDER BY value
            """
        ).fetchall()
        found[column] = [row["value"] for row in rows]
    return found


def _load(connection, categories: dict[str, list[str]]) -> dict[str, np.ndarray]:
    indexes = {
        name: {code: position for position, code in enumerate(values)}
        for name, values in categories.items()
    }
    count = int(
        connection.execute(
            """
            SELECT COUNT(*) AS n FROM market_fares
            WHERE (year = 2024 AND quarter IN (3, 4))
               OR (year = 2025 AND quarter = 1)
            """
        ).fetchone()["n"]
    )
    if count == 0:
        raise SystemExit("No 2024 Q3–2025 Q1 fares in the database.")
    print(f"loading {count:,} pre-holdout rows", flush=True)
    frame = {
        "year": np.empty(count, dtype=np.int16),
        "quarter": np.empty(count, dtype=np.int8),
        "origin": np.empty(count, dtype=np.int16),
        "dest": np.empty(count, dtype=np.int16),
        "airline": np.empty(count, dtype=np.int16),
        "distance": np.empty(count, dtype=np.float32),
        "passengers": np.empty(count, dtype=np.float32),
        "fare": np.empty(count, dtype=np.float32),
        "stops": np.empty(count, dtype=np.int16),
        "coupons": np.empty(count, dtype=np.int16),
    }
    cursor = connection.execute(
        """
        SELECT year, quarter, origin, dest, airline, distance, passengers, fare, stops, coupons
        FROM market_fares
        WHERE (year = 2024 AND quarter IN (3, 4))
           OR (year = 2025 AND quarter = 1)
        """
    )
    index = 0
    while True:
        rows = cursor.fetchmany(200_000)
        if not rows:
            break
        for row in rows:
            frame["year"][index] = row["year"]
            frame["quarter"][index] = row["quarter"]
            frame["origin"][index] = indexes["origin"].get(row["origin"], -1)
            frame["dest"][index] = indexes["dest"].get(row["dest"], -1)
            frame["airline"][index] = indexes["airline"].get(row["airline"], -1)
            frame["distance"][index] = row["distance"]
            frame["passengers"][index] = row["passengers"]
            frame["fare"][index] = row["fare"]
            frame["stops"][index] = row["stops"]
            frame["coupons"][index] = row["coupons"]
            index += 1
        if index % 2_000_000 < 200_000:
            print(f"  loaded {index:,}", flush=True)
    if index != count:
        raise SystemExit(f"Expected {count:,} rows and read {index:,}.")
    frame["known"] = (frame["origin"] >= 0) & (frame["dest"] >= 0) & (frame["airline"] >= 0)
    return frame


def _mask(frame, year: int, quarter: int) -> np.ndarray:
    return frame["known"] & (frame["year"] == year) & (frame["quarter"] == quarter)


def _matrix(frame, rows: np.ndarray, share: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    chosen = np.flatnonzero(rows)
    matrix = design_matrix(
        frame["origin"][chosen],
        frame["dest"][chosen],
        frame["airline"][chosen],
        frame["distance"][chosen],
        frame["quarter"][chosen],
        frame["coupons"][chosen],
        frame["stops"][chosen],
        share[chosen],
    )
    return matrix, frame["fare"][chosen], frame["passengers"][chosen]


def _fit(train, valid, alpha: float, config: dict, rounds: int, early: bool) -> lgb.Booster:
    train_x, train_y, train_w = train
    dataset = lgb.Dataset(
        train_x,
        label=train_y,
        weight=train_w,
        categorical_feature=list(CATEGORICAL),
        free_raw_data=True,
    )
    callbacks = [lgb.log_evaluation(25)]
    valid_sets = None
    if early:
        valid_x, valid_y, valid_w = valid
        valid_sets = [
            lgb.Dataset(
                valid_x,
                label=valid_y,
                weight=valid_w,
                reference=dataset,
                categorical_feature=list(CATEGORICAL),
                free_raw_data=True,
            )
        ]
        callbacks.append(lgb.early_stopping(EARLY_STOP, verbose=False))
    return lgb.train(
        _params(alpha, config),
        dataset,
        num_boost_round=rounds,
        valid_sets=valid_sets,
        callbacks=callbacks,
    )


def _mae(model: lgb.Booster, valid) -> float:
    valid_x, valid_y, valid_w = valid
    iteration = model.best_iteration if model.best_iteration and model.best_iteration > 0 else None
    predicted = model.predict(valid_x, num_iteration=iteration)
    return float(np.average(np.abs(predicted - valid_y), weights=valid_w))


def _share(frame, mask: np.ndarray, categories: dict[str, list[str]]) -> np.ndarray:
    return carrier_share_feature(
        frame["origin"],
        frame["dest"],
        frame["airline"],
        frame["passengers"],
        mask & frame["known"],
        len(categories["origin"]),
        len(categories["dest"]),
        len(categories["airline"]),
    )


def _save_route_bands(connection, frame, categories, models, share, offset: float) -> int:
    train = ((frame["year"] == 2024) & np.isin(frame["quarter"], [3, 4]) & frame["known"])
    chosen = np.flatnonzero(train)
    origin = frame["origin"][chosen].astype(np.int64)
    dest = frame["dest"][chosen].astype(np.int64)
    airline = frame["airline"][chosen].astype(np.int64)
    quarter_bit = (frame["quarter"][chosen].astype(np.int64) == 4).astype(np.int64)
    n_dest = len(categories["dest"])
    n_airline = len(categories["airline"])
    key = ((origin * n_dest + dest) * n_airline + airline) * 2 + quarter_bit
    _unique, inverse = np.unique(key, return_inverse=True)
    weight = frame["passengers"][chosen].astype(np.float64)
    totals = np.bincount(inverse, weights=weight)
    distance = np.bincount(inverse, weights=frame["distance"][chosen] * weight) / totals
    coupons = np.bincount(inverse, weights=frame["coupons"][chosen].astype(np.float64) * weight) / totals
    stops = np.bincount(inverse, weights=frame["stops"][chosen].astype(np.float64) * weight) / totals
    decode = _unique
    group_airline = (decode // 2) % n_airline
    group_dest = (decode // 2 // n_airline) % n_dest
    group_origin = decode // 2 // n_airline // n_dest
    group_quarter = np.where((decode % 2) == 1, 4, 3).astype(np.float32)
    group_share = np.bincount(inverse, weights=share[chosen].astype(np.float64)) / np.maximum(np.bincount(inverse), 1)
    matrix = design_matrix(
        group_origin,
        group_dest,
        group_airline,
        distance,
        group_quarter,
        np.rint(coupons).astype(np.int16),
        np.rint(stops).astype(np.int16),
        group_share,
    )
    print(f"scoring {len(matrix):,} airline-quarter slices", flush=True)
    columns = [model.predict(matrix) for model in models]
    predicted = repair_quantiles(np.column_stack(columns))
    route_key = group_origin * n_dest + group_dest
    # Remap route keys to a compact range for bincount.
    compact, route_ids = np.unique(route_key, return_inverse=True)
    means, route_passengers = aggregate_route_quantiles(predicted, totals, route_ids)
    low, mid, high = widen_band(means, offset)
    origins = categories["origin"]
    dests = categories["dest"]
    connection.execute("DROP TABLE IF EXISTS model_route_bands")
    connection.execute(
        """
        CREATE TABLE model_route_bands (
            origin TEXT NOT NULL,
            dest TEXT NOT NULL,
            passengers INTEGER NOT NULL,
            low INTEGER NOT NULL,
            mid INTEGER NOT NULL,
            high INTEGER NOT NULL,
            confidence TEXT NOT NULL,
            PRIMARY KEY (origin, dest)
        )
        """
    )
    rows = []
    for index, packed in enumerate(compact):
        passengers = int(round(float(route_passengers[index])))
        if passengers <= 0:
            continue
        origin_code = origins[int(packed) // n_dest]
        dest_code = dests[int(packed) % n_dest]
        low_i = int(round(float(low[index])))
        mid_i = int(round(float(mid[index])))
        high_i = int(round(float(high[index])))
        if mid_i < low_i:
            mid_i = low_i
        if high_i < mid_i:
            high_i = mid_i
        confidence = "low" if passengers < 50 else "normal"
        rows.append((origin_code, dest_code, passengers, low_i, mid_i, high_i, confidence))
    connection.executemany(
        """
        INSERT INTO model_route_bands (origin, dest, passengers, low, mid, high, confidence)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    connection.commit()
    return len(rows)


def _shap_summary(model: lgb.Booster, frame, share, train_mask: np.ndarray) -> dict:
    chosen = np.flatnonzero(train_mask)
    rng = np.random.default_rng(SEED)
    take = min(SHAP_ROWS, chosen.size)
    picked = rng.choice(chosen, size=take, replace=False)
    mask = np.zeros(train_mask.shape, dtype=bool)
    mask[picked] = True
    matrix, _fare, _weight = _matrix(frame, mask, share)
    contribution = model.predict(matrix, pred_contrib=True)
    mean_abs = np.abs(contribution[:, : len(FEATURES)]).mean(axis=0)
    return {
        "rows": int(take),
        "seed": SEED,
        "mean_abs": {name: round(float(value), 4) for name, value in zip(FEATURES, mean_abs)},
    }


def main() -> None:
    np.random.seed(SEED)
    if not DB_PATH.exists():
        raise SystemExit("Load DB1B first: python -m scripts.load_db1b")
    connection = connect()
    connection.execute("PRAGMA busy_timeout = 300000")
    try:
        categories = _categories(connection)
        frame = _load(connection, categories)
        if np.any((frame["year"] == 2025) & (frame["quarter"] == 2)):
            raise SystemExit("Holdout rows were loaded. Refusing to train.")
        fold1_train = _mask(frame, 2024, 3)
        fold1_score = _mask(frame, 2024, 4)
        fold2_train = _mask(frame, 2024, 3) | _mask(frame, 2024, 4)
        fold2_score = _mask(frame, *CALIBRATION)
        print(
            f"fold rows train {int(fold1_train.sum()):,} / {int(fold2_train.sum()):,}  "
            f"score {int(fold1_score.sum()):,} / {int(fold2_score.sum()):,}",
            flush=True,
        )
        os.environ["MLFLOW_ALLOW_FILE_STORE"] = "true"
        mlflow.set_tracking_uri((BACKEND_DIR / "mlruns").as_uri())
        mlflow.set_experiment("dot-fare-phase2")
        tuning = []
        for config in GRID:
            fold_scores = []
            for name, train_mask, score_mask in (
                ("2024Q3-to-2024Q4", fold1_train, fold1_score),
                ("2024Q3Q4-to-2025Q1", fold2_train, fold2_score),
            ):
                print(f"tune {config['name']} {name}", flush=True)
                share = _share(frame, train_mask, categories)
                train = _matrix(frame, train_mask, share)
                valid = _matrix(frame, score_mask, share)
                with mlflow.start_run(run_name=f"tune-{config['name']}-{name}"):
                    mlflow.log_params({**config, "fold": name, "alpha": 0.5, "max_rounds": MAX_ROUNDS, "seed": SEED})
                    model = _fit(train, valid, 0.5, config, MAX_ROUNDS, early=True)
                    score = _mae(model, valid)
                    rounds = int(model.best_iteration or MAX_ROUNDS)
                    mlflow.log_metrics({"p50_mae": score, "best_iteration": rounds})
                print(f"  MAE {score:.2f}  rounds {rounds}", flush=True)
                fold_scores.append({"fold": name, "mae": score, "rounds": rounds, **config})
                del train, valid, model, share
            tuning.extend(fold_scores)
        by_config: dict[str, list[dict]] = {}
        for row in tuning:
            by_config.setdefault(row["name"], []).append(row)
        winner_name = min(by_config, key=lambda name: float(np.mean([item["mae"] for item in by_config[name]])))
        winner_rows = by_config[winner_name]
        winner = {key: winner_rows[0][key] for key in ("name", "learning_rate", "num_leaves", "min_data_in_leaf")}
        rounds = max(20, int(round(float(np.mean([item["rounds"] for item in winner_rows])))))
        print(f"selected {winner_name} for {rounds} rounds", flush=True)

        final_share = _share(frame, fold2_train, categories)
        train = _matrix(frame, fold2_train, final_share)
        models = []
        with mlflow.start_run(run_name="final-quantiles"):
            mlflow.log_params({**winner, "rounds": rounds, "seed": SEED, "train": "2024Q3-2024Q4"})
            for alpha in ALPHAS:
                print(f"final alpha {alpha}", flush=True)
                models.append(_fit(train, None, alpha, winner, rounds, early=False))
            calib_x, calib_y, calib_w = _matrix(frame, fold2_score, final_share)
            raw = np.column_stack([model.predict(calib_x) for model in models])
            repaired = repair_quantiles(raw)
            offset = conformal_offset(
                conformity_scores(calib_y, repaired[:, 1], repaired[:, 5]),
                calib_w,
                COVERAGE_LEVEL,
            )
            mlflow.log_metric("conformal_offset", offset)
            print(f"conformal offset {offset:.2f}", flush=True)
            shap_summary = _shap_summary(models[P50_INDEX], frame, final_share, fold2_train)
            mlflow.log_metrics({f"shap_{name}": value for name, value in shap_summary["mean_abs"].items()})
            del calib_x, calib_y, calib_w, raw, repaired, train

            PHASE2_DIR.mkdir(parents=True, exist_ok=True)
            for alpha, model in zip(ALPHAS, models):
                model.save_model(str(PHASE2_DIR / f"quantile_{int(round(alpha * 100)):02d}.txt"))
            (PHASE2_DIR / "shap_summary.json").write_text(json.dumps(shap_summary, indent=2), encoding="utf-8")
            metadata = {
            "version": VERSION,
            "source": SOURCE,
            "seed": SEED,
            "features": list(FEATURES),
            "alphas": list(ALPHAS),
            "categories": categories,
            "params": winner,
            "rounds": rounds,
            "conformal_offset": offset,
            "coverage_level": COVERAGE_LEVEL,
            "tuning": tuning,
            "train_periods": [f"{year}Q{quarter}" for year, quarter in FINAL_TRAIN],
            "calibration_period": f"{CALIBRATION[0]}Q{CALIBRATION[1]}",
            "holdout": "2025Q2",
            "directional_market": True,
            "shap_rows": shap_summary["rows"],
        }
            (PHASE2_DIR / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
            mlflow.log_artifact(str(PHASE2_DIR / "metadata.json"))
            mlflow.log_artifact(str(PHASE2_DIR / "shap_summary.json"))
            saved = _save_route_bands(connection, frame, categories, models, final_share, offset)
            mlflow.log_metric("route_bands", saved)
            print(f"saved {VERSION}  route bands {saved:,}  offset {offset:.2f}", flush=True)
    finally:
        connection.close()


if __name__ == "__main__":
    main()
