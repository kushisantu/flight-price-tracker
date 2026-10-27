"""Score the Phase 2 model on 2025 Q2 against the empirical table and the baselines."""

from __future__ import annotations

import json
import os

import lightgbm as lgb
import mlflow
import numpy as np

from app.config import BACKEND_DIR
from app.services.db1b import HOLDOUT, SOURCE, connect
from app.services.empirical import VERSION as EMPIRICAL_VERSION
from app.services.empirical import load_indexes, predict_cached
from app.services.fare_band import MODEL_DIR
from app.services.phase2 import (
    ALPHAS,
    COVERAGE_LEVEL,
    FEATURES,
    PHASE2_DIR,
    SEED,
    VERSION,
    conformity_scores,
    design_matrix,
    repair_quantiles,
    volume_tier,
    widen_band,
)
from scripts.eval import _airlines, _fit_linear, _formula, _linear_price

BATCH = 200_000


def _empty_bucket() -> dict:
    return {
        "rows": 0,
        "weight": 0.0,
        "model": 0.0,
        "empirical": 0.0,
        "route": 0.0,
        "linear": 0.0,
        "formula": 0.0,
        "raw_covered": 0.0,
        "conformal_covered": 0.0,
    }


def _add(bucket: dict, weight: float, **errors: float) -> None:
    bucket["rows"] += 1
    bucket["weight"] += weight
    for key, value in errors.items():
        bucket[key] += value


def _mae(total: float, weight: float) -> float | None:
    if weight <= 0:
        return None
    return round(total / weight, 2)


def _rate(covered: float, weight: float) -> float | None:
    if weight <= 0:
        return None
    return round(covered / weight, 4)


def _pack_model(bucket: dict) -> dict:
    return {
        "rows": bucket["rows"],
        "passengers": int(round(bucket["weight"])),
        "model_mae": _mae(bucket["model"], bucket["weight"]),
        "raw_10_90_coverage": _rate(bucket["raw_covered"], bucket["weight"]),
        "conformal_10_90_coverage": _rate(bucket["conformal_covered"], bucket["weight"]),
    }


def _pack(bucket: dict, formula: bool) -> dict:
    packed = {
        "rows": bucket["rows"],
        "model_mae": _mae(bucket["model"], bucket["weight"]),
        "empirical_mae": _mae(bucket["empirical"], bucket["weight"]),
        "route_average_mae": _mae(bucket["route"], bucket["weight"]),
        "linear_mae": _mae(bucket["linear"], bucket["weight"]),
        "raw_10_90_coverage": _rate(bucket["raw_covered"], bucket["weight"]),
        "conformal_10_90_coverage": _rate(bucket["conformal_covered"], bucket["weight"]),
    }
    if formula:
        packed["formula_mae"] = _mae(bucket["formula"], bucket["weight"])
    return packed


def _shares(connection) -> tuple[dict, dict]:
    rows = connection.execute(
        """
        SELECT origin, dest, airline, SUM(passengers) AS passengers
        FROM market_fares
        WHERE year = 2024 AND quarter IN (3, 4)
        GROUP BY origin, dest, airline
        """
    ).fetchall()
    pair: dict[tuple[str, str, str], int] = {}
    route: dict[tuple[str, str], int] = {}
    for row in rows:
        passengers = int(row["passengers"])
        pair[(row["origin"], row["dest"], row["airline"])] = passengers
        key = (row["origin"], row["dest"])
        route[key] = route.get(key, 0) + passengers
    share = {key: passengers / route[(key[0], key[1])] for key, passengers in pair.items() if route[(key[0], key[1])] > 0}
    return share, route


def _models() -> tuple[list[lgb.Booster], dict]:
    metadata_path = PHASE2_DIR / "metadata.json"
    if not metadata_path.exists():
        raise SystemExit("Run python -m scripts.train_phase2 first.")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    boosters = []
    for alpha in ALPHAS:
        path = PHASE2_DIR / f"quantile_{int(round(alpha * 100)):02d}.txt"
        if not path.exists():
            raise SystemExit(f"Missing {path.name}. Run python -m scripts.train_phase2 first.")
        boosters.append(lgb.Booster(model_file=str(path)))
    return boosters, metadata


def _dollars(value) -> str:
    if value is None:
        return ""
    return f"${value:,.2f}"


def _percent(value) -> str:
    if value is None:
        return ""
    scaled = int(value * 1000 + 0.5) / 10
    return f"{scaled:.1f}%"


def _write_card(metadata: dict, metrics: dict, shap: dict) -> None:
    tuning_lines = [
        f"| {row['name']} | {row['fold']} | {row['mae']:.2f} | {row['rounds']} |"
        for row in metadata["tuning"]
    ]
    shap_lines = [
        f"| {name} | {value:.2f} |"
        for name, value in sorted(shap["mean_abs"].items(), key=lambda item: item[1], reverse=True)
    ]
    population = metrics["comparison"]
    empirical_coverage = population.get("empirical_coverage")
    tiers = "\n".join(
        f"| {name} | {row['rows']:,} | {_dollars(row['model_mae'])} | {_percent(row['conformal_10_90_coverage'])} |"
        for name, row in metrics["by_volume_tier"].items()
    )
    airlines = "\n".join(
        f"| {row['airline']} | {row['passengers']:,} | {_dollars(row['model_mae'])} | {_percent(row['conformal_10_90_coverage'])} |"
        for row in metrics["by_airline"][:15]
    )
    card = f"""# Model card: {VERSION}

This model estimates the paid fare distribution for a directional DB1B market. It is not a forecast of what a ticket will cost on a booking date. DB1B has no purchase date.

## Data

Source: {SOURCE}. Training rows are 2024 Q3 and 2024 Q4 only. 2025 Q1 supplies the conformal adjustment and is also the second rolling-origin score. 2025 Q2 is the holdout and is not used for training, tuning, or calibration.

Market rows are one direction of travel. The extract has no round-trip flag, so none is invented. Nonstop is coupons equal to 1. Carrier share is that airline's fraction of the route's passengers in the training quarters only.

The sample flight board is unchanged. A route with no training tickets stays uncovered. A route with fewer than 50 training passengers is labeled low confidence.

## Fit

Seven LightGBM quantile models: {", ".join(str(alpha) for alpha in ALPHAS)}. Predictions are sorted so a lower quantile cannot sit above a higher one. Seed {SEED}. The displayed 10th to 90th band is then shifted by a conformal offset of {metadata["conformal_offset"]:.2f}, chosen so about {int(COVERAGE_LEVEL * 100)} percent of 2025 Q1 tickets fall inside.

Selected parameters: `{metadata["params"]["name"]}`, learning rate {metadata["params"]["learning_rate"]}, {metadata["params"]["num_leaves"]} leaves, {metadata["rounds"]} rounds.

| Config | Fold | Median MAE | Rounds |
| --- | --- | ---: | ---: |
{chr(10).join(tuning_lines)}

Mean absolute TreeSHAP on {shap["rows"]} training rows (seed {SEED}), from LightGBM `pred_contrib`:

| Feature | Mean absolute SHAP |
| --- | ---: |
{chr(10).join(shap_lines)}

Stops and nonstop receive no splits. In this extract, stops are coupons minus one, and nonstop means one coupon, so coupons already carry that information.

MLflow writes a local file store at `backend/mlruns`. The training script sets `MLFLOW_ALLOW_FILE_STORE` so that folder is accepted.

## Holdout

2025 Q2 tickets that both this model and the empirical table can score: {population["rows"]:,}.

| Estimate | MAE | 10–90 coverage |
| --- | ---: | ---: |
| Phase 2 median | {_dollars(population["model_mae"])} | {_percent(population["conformal_10_90_coverage"])} |
| Empirical median ({EMPIRICAL_VERSION}) | {_dollars(population["empirical_mae"])} | {_percent(empirical_coverage)} |
| Route average | {_dollars(population["route_average_mae"])} |  |
| Linear model | {_dollars(population["linear_mae"])} |  |

Raw model 10–90 coverage, before the conformal shift: {_percent(population["raw_10_90_coverage"])}.
Conformal 10–90 coverage: {_percent(population["conformal_10_90_coverage"])}.

### By training volume

| Tier | Rows | Median MAE | Conformal coverage |
| --- | ---: | ---: | ---: |
{tiers}

### By airline

The fifteen airlines with the most holdout passengers in the comparison set:

| Airline | Passengers | Median MAE | Conformal coverage |
| --- | ---: | ---: | ---: |
{airlines}

## Limits

The quarterly file is a 10 percent sample. The model does not know how far ahead a ticket was bought, the weekday, or whether the market was half of a round trip. Uncovered routes are stated as uncovered. The older whitelist LightGBM files are kept and are not served.
"""
    path = PHASE2_DIR / "MODEL_CARD.md"
    path.write_text(card, encoding="utf-8")
    root = BACKEND_DIR.parent / "MODEL_CARD.md"
    root.write_text(card, encoding="utf-8")
    print(f"wrote {path}", flush=True)


def main() -> None:
    np.random.seed(SEED)
    boosters, metadata = _models()
    offset = float(metadata["conformal_offset"])
    categories = metadata["categories"]
    indexes = {
        name: {code: position for position, code in enumerate(values)}
        for name, values in categories.items()
    }
    connection = connect()
    try:
        print("loading training shares", flush=True)
        shares, route_passengers = _shares(connection)
        print("fitting linear baseline", flush=True)
        coefficients, airline_index, width = _fit_linear(connection, _airlines(connection))
        routes, slices = load_indexes(connection)
        comparison = _empty_bucket()
        comparison["empirical_covered"] = 0.0
        formula_bucket = _empty_bucket()
        tiers = {}
        airlines = {}
        skipped = 0
        scanned = 0
        print("scoring holdout", flush=True)
        cursor = connection.execute(
            """
            SELECT origin, dest, airline, distance, year, quarter, coupons, stops, fare, passengers
            FROM market_fares
            WHERE year = ? AND quarter = ?
            """,
            HOLDOUT,
        )
        while True:
            fetched = cursor.fetchmany(BATCH)
            if not fetched:
                break
            scanned += len(fetched)
            print(f"  holdout rows {scanned:,}", flush=True)
            keep = []
            origin_codes = []
            dest_codes = []
            airline_codes = []
            for row in fetched:
                origin = indexes["origin"].get(row["origin"])
                dest = indexes["dest"].get(row["dest"])
                airline = indexes["airline"].get(row["airline"])
                if origin is None or dest is None or airline is None:
                    skipped += 1
                    continue
                keep.append(row)
                origin_codes.append(origin)
                dest_codes.append(dest)
                airline_codes.append(airline)
            if not keep:
                continue
            share = np.array(
                [shares.get((row["origin"], row["dest"], row["airline"]), 0.0) for row in keep],
                dtype=np.float32,
            )
            matrix = design_matrix(
                np.array(origin_codes),
                np.array(dest_codes),
                np.array(airline_codes),
                np.array([row["distance"] for row in keep], dtype=np.float32),
                np.array([row["quarter"] for row in keep], dtype=np.float32),
                np.array([row["coupons"] for row in keep], dtype=np.float32),
                np.array([row["stops"] for row in keep], dtype=np.float32),
                share,
            )
            repaired = repair_quantiles(np.column_stack([model.predict(matrix) for model in boosters]))
            low, mid, high = widen_band(repaired, offset)
            raw_low = repaired[:, 1]
            raw_high = repaired[:, 5]
            for index, row in enumerate(keep):
                empirical = predict_cached(routes, slices, row["origin"], row["dest"])
                if empirical is None:
                    continue
                weight = float(row["passengers"])
                fare = float(row["fare"])
                linear = _linear_price(coefficients, airline_index, width, row)
                model_error = abs(float(mid[index]) - fare) * weight
                empirical_error = abs(float(empirical["mid"]) - fare) * weight
                route_error = abs(float(empirical["mean_fare"]) - fare) * weight
                linear_error = abs(linear - fare) * weight
                raw_hit = weight if raw_low[index] <= fare <= raw_high[index] else 0.0
                conf_hit = weight if low[index] <= fare <= high[index] else 0.0
                empirical_hit = weight if empirical["low"] <= fare <= empirical["high"] else 0.0
                _add(
                    comparison,
                    weight,
                    model=model_error,
                    empirical=empirical_error,
                    route=route_error,
                    linear=linear_error,
                    raw_covered=raw_hit,
                    conformal_covered=conf_hit,
                )
                comparison["empirical_covered"] += empirical_hit
                tier_name = volume_tier(route_passengers.get((row["origin"], row["dest"]), 0))
                tier = tiers.setdefault(tier_name, _empty_bucket())
                _add(tier, weight, model=model_error, raw_covered=raw_hit, conformal_covered=conf_hit)
                airline = airlines.setdefault(row["airline"], _empty_bucket())
                _add(airline, weight, model=model_error, raw_covered=raw_hit, conformal_covered=conf_hit)
                formula = _formula(row["origin"], row["dest"], row["airline"], int(row["stops"]))
                if formula is None:
                    continue
                _add(
                    formula_bucket,
                    weight,
                    model=model_error,
                    empirical=empirical_error,
                    route=route_error,
                    linear=linear_error,
                    formula=abs(formula - fare) * weight,
                    raw_covered=raw_hit,
                    conformal_covered=conf_hit,
                )
    finally:
        connection.close()

    packed = _pack(comparison, False)
    packed["empirical_coverage"] = _rate(comparison["empirical_covered"], comparison["weight"])
    airline_rows = []
    for code, bucket in airlines.items():
        row = _pack_model(bucket)
        row["airline"] = code
        airline_rows.append(row)
    airline_rows.sort(key=lambda item: item["passengers"], reverse=True)
    metrics = {
        "version": VERSION,
        "empirical_version": EMPIRICAL_VERSION,
        "source": SOURCE,
        "holdout": f"{HOLDOUT[0]}Q{HOLDOUT[1]}",
        "train_periods": metadata["train_periods"],
        "calibration_period": metadata["calibration_period"],
        "seed": SEED,
        "conformal_offset": round(offset, 4),
        "coverage_level": COVERAGE_LEVEL,
        "features": list(FEATURES),
        "skipped_unknown_category": skipped,
        "comparison": packed,
        "formula_comparable": _pack(formula_bucket, True),
        "by_volume_tier": {name: _pack_model(bucket) for name, bucket in sorted(tiers.items())},
        "by_airline": airline_rows,
    }
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    path = MODEL_DIR / "phase2_metrics.json"
    path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    shap = json.loads((PHASE2_DIR / "shap_summary.json").read_text(encoding="utf-8"))
    _write_card(metadata, metrics, shap)
    os.environ["MLFLOW_ALLOW_FILE_STORE"] = "true"
    mlflow.set_tracking_uri((BACKEND_DIR / "mlruns").as_uri())
    mlflow.set_experiment("dot-fare-phase2")
    with mlflow.start_run(run_name="holdout-2025q2"):
        mlflow.log_params({"version": VERSION, "seed": SEED})
        mlflow.log_metrics(
            {
                "model_mae": packed["model_mae"] or 0.0,
                "empirical_mae": packed["empirical_mae"] or 0.0,
                "route_average_mae": packed["route_average_mae"] or 0.0,
                "linear_mae": packed["linear_mae"] or 0.0,
                "raw_10_90_coverage": packed["raw_10_90_coverage"] or 0.0,
                "conformal_10_90_coverage": packed["conformal_10_90_coverage"] or 0.0,
                "rows": packed["rows"],
            }
        )
        mlflow.log_artifact(str(path))
    print(json.dumps({key: metrics[key] for key in ("comparison", "formula_comparable", "by_volume_tier")}, indent=2), flush=True)
    print(f"wrote {path}", flush=True)


if __name__ == "__main__":
    main()
