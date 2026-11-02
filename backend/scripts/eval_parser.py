"""Score the rule parser, and the language-model parser when a key is set."""

from __future__ import annotations

import json
from datetime import date

from app.config import settings
from app.parser_queries import QUERIES
from app.services.fare_band import MODEL_DIR
from app.services.llm_parse import interpret
from app.services.smart import parse_rules

TODAY = date(2026, 10, 26)
FIELDS = ("origin", "destination", "trip_type", "passengers", "cabin", "max_price")


def _fields(result: dict) -> dict:
    criteria = result["criteria"]
    return {
        "origin": criteria["origin"]["code"],
        "destination": criteria["destination"]["code"],
        "trip_type": criteria["trip_type"],
        "passengers": criteria["passengers"],
        "cabin": criteria["cabin"],
        "max_price": result.get("max_price"),
    }


def _score(rows: list[dict]) -> dict:
    totals = {field: 0 for field in FIELDS}
    exact = 0
    for row in rows:
        if row is None:
            continue
        matched = all(row["actual"][field] == row["expected"][field] for field in FIELDS)
        exact += int(matched)
        for field in FIELDS:
            totals[field] += int(row["actual"][field] == row["expected"][field])
    count = len(rows)
    return {
        "queries": count,
        "exact_match": round(exact / count, 4) if count else None,
        "by_field": {field: round(totals[field] / count, 4) if count else None for field in FIELDS},
    }


def main() -> None:
    rule_rows = []
    llm_rows = []
    key_present = bool((settings.llm_api_key or "").strip())
    for item in QUERIES:
        expected = {field: item[field] for field in FIELDS}
        fallback = item.get("fallback")
        try:
            ruled = parse_rules(item["query"], fallback, TODAY)
            actual = _fields(ruled)
        except ValueError:
            actual = None
        rule_rows.append(None if actual is None else {"query": item["query"], "expected": expected, "actual": actual})
        if not key_present:
            continue
        drafted = interpret(item["query"], TODAY)
        llm_rows.append(None if drafted is None else {"query": item["query"], "expected": expected, "actual": _fields(drafted)})
    metrics = {
        "queries": len(QUERIES),
        "rules": _score([row for row in rule_rows if row is not None]),
        "rules_failed": sum(1 for row in rule_rows if row is None),
        "llm_ran": key_present,
        "llm": None if not key_present else _score([row for row in llm_rows if row is not None]),
        "rule_mismatches": [
            {"query": row["query"], "expected": row["expected"], "actual": row["actual"]}
            for row in rule_rows
            if row is not None and row["expected"] != row["actual"]
        ],
    }
    path = MODEL_DIR / "parser_metrics.json"
    path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps({key: metrics[key] for key in ("rules", "rules_failed", "llm_ran", "llm")}, indent=2), flush=True)
    print(f"wrote {path}", flush=True)


if __name__ == "__main__":
    main()
