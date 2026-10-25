"""US DOT DB1B market fares kept for the airports this app already knows.

The survey records a paid fare for a directional market. It has no purchase
date and no day-by-day price path, so these rows cannot train a forecast.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.catalog import AIRPORTS
from app.config import BACKEND_DIR

DATA_DIR = BACKEND_DIR / "data"
DB_PATH = DATA_DIR / "db1b.sqlite"
RAW_DIR = DATA_DIR / "raw"

# A later quarter is held out in training. These four are the newest Market
# files published on the BTS prezip server at the time of the load.
QUARTERS = ((2024, 3), (2024, 4), (2025, 1), (2025, 2))

SOURCE = "US DOT DB1B Market"


def us_airports() -> set[str]:
    return {code for code, airport in AIRPORTS.items() if airport["country"] == "United States"}


def quarter_url(year: int, quarter: int) -> str:
    return (
        "https://transtats.bts.gov/PREZIP/"
        f"Origin_and_Destination_Survey_DB1BMarket_{year}_{quarter}.zip"
    )


def normalize_fare(row: dict, airports: set[str] | None = None) -> tuple | None:
    """Return one stored fare, or None when the row is outside the sample.

    In this Market extract, MktFare is already the dollars per person and
    Passengers is how many people paid it. Bulk tickets are dropped.
    """
    airports = us_airports() if airports is None else airports
    origin = str(row.get("origin") or "").strip().upper()
    dest = str(row.get("dest") or "").strip().upper()
    if origin not in airports or dest not in airports or origin == dest:
        return None
    if str(row.get("bulk") or "").strip() in {"1", "1.0"}:
        return None

    airline = str(row.get("tk") or "").strip().upper() or str(row.get("op") or "").strip().upper()
    if len(airline) < 2 or airline == "99":
        return None

    try:
        year = int(float(row["year"]))
        quarter = int(float(row["quarter"]))
        passengers = int(float(row["passengers"]))
        total_fare = float(row["fare"])
        distance = float(row["distance"])
        coupons = int(float(row.get("coupons") or 1))
    except (KeyError, TypeError, ValueError):
        return None
    if passengers <= 0 or distance <= 0 or quarter not in {1, 2, 3, 4}:
        return None
    fare = total_fare
    if fare < 20 or fare > 4000:
        return None
    stops = max(0, coupons - 1)
    return (year, quarter, origin, dest, airline, round(distance, 1), passengers, round(fare, 2), stops)


def connect(path: Path | None = None) -> sqlite3.Connection:
    target = path or DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target)
    connection.row_factory = sqlite3.Row
    return connection


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS market_fares (
            year INTEGER NOT NULL,
            quarter INTEGER NOT NULL,
            origin TEXT NOT NULL,
            dest TEXT NOT NULL,
            airline TEXT NOT NULL,
            distance REAL NOT NULL,
            passengers INTEGER NOT NULL,
            fare REAL NOT NULL,
            stops INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS load_log (
            year INTEGER NOT NULL,
            quarter INTEGER NOT NULL,
            rows INTEGER NOT NULL,
            source_file TEXT NOT NULL,
            PRIMARY KEY (year, quarter)
        );
        """
    )


def loaded_quarters(connection: sqlite3.Connection) -> set[tuple[int, int]]:
    ensure_schema(connection)
    rows = connection.execute("SELECT year, quarter FROM load_log").fetchall()
    return {(row["year"], row["quarter"]) for row in rows}


def route_summary(origin: str, dest: str, path: Path | None = None) -> dict:
    """Passenger-weighted fare counts for one airport pair, if the file exists."""
    target = path or DB_PATH
    if not target.exists():
        return {"rows": 0, "passengers": 0}
    connection = connect(target)
    try:
        ensure_schema(connection)
        row = connection.execute(
            """
            SELECT COUNT(*) AS rows, COALESCE(SUM(passengers), 0) AS passengers
            FROM market_fares
            WHERE origin = ? AND dest = ?
            """,
            (origin, dest),
        ).fetchone()
    finally:
        connection.close()
    return {"rows": int(row["rows"]), "passengers": int(row["passengers"])}


def fare_count(path: Path | None = None) -> int:
    target = path or DB_PATH
    if not target.exists():
        return 0
    connection = connect(target)
    try:
        ensure_schema(connection)
        return int(connection.execute("SELECT COUNT(*) AS n FROM market_fares").fetchone()["n"])
    finally:
        connection.close()
