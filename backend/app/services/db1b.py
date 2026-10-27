"""US DOT DB1B market fares for every airport in the survey files.

The survey records a paid fare for a directional market. It has no purchase
date and no day-by-day price path, so these rows cannot train a forecast.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.config import BACKEND_DIR

DATA_DIR = BACKEND_DIR / "data"
DB_PATH = DATA_DIR / "db1b.sqlite"
RAW_DIR = DATA_DIR / "raw"
SCHEMA_VERSION = "2"
SOURCE = "US DOT DB1B Market"
OPENFLIGHTS_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airports.dat"

# A later quarter is held out in training. These four are the newest Market
# files published on the BTS prezip server at the time of the load.
QUARTERS = ((2024, 3), (2024, 4), (2025, 1), (2025, 2))
HOLDOUT = (2025, 2)


def quarter_url(year: int, quarter: int) -> str:
    return (
        "https://transtats.bts.gov/PREZIP/"
        f"Origin_and_Destination_Survey_DB1BMarket_{year}_{quarter}.zip"
    )


def is_holdout(year: int, quarter: int) -> bool:
    return (year, quarter) == HOLDOUT


def normalize_fare(row: dict, _airports: set[str] | None = None) -> tuple | None:
    """Return one stored fare, or None when the row is not a usable ticket.

    Every origin and destination in the file is kept. MktFare in this extract
    is already the dollars per person, and Passengers is how many people paid
    it. Bulk tickets are dropped.
    """
    del _airports
    origin = str(row.get("origin") or "").strip().upper()
    dest = str(row.get("dest") or "").strip().upper()
    if len(origin) != 3 or len(dest) != 3 or not origin.isalpha() or not dest.isalpha():
        return None
    if origin == dest:
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
        fare = float(row["fare"])
        distance = float(row["distance"])
        coupons = int(float(row.get("coupons") or 1))
    except (KeyError, TypeError, ValueError):
        return None
    if passengers <= 0 or distance <= 0 or quarter not in {1, 2, 3, 4} or coupons <= 0:
        return None
    if fare < 20 or fare > 4000:
        return None
    origin_state = str(row.get("origin_state") or "").strip().upper()[:8]
    dest_state = str(row.get("dest_state") or "").strip().upper()[:8]
    stops = max(0, coupons - 1)
    return (
        year,
        quarter,
        origin,
        dest,
        airline,
        round(distance, 1),
        passengers,
        round(fare, 2),
        stops,
        coupons,
        origin_state,
        dest_state,
    )


def connect(path: Path | None = None) -> sqlite3.Connection:
    target = path or DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target)
    connection.row_factory = sqlite3.Row
    return connection


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS dot_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS market_fares (
            year INTEGER NOT NULL,
            quarter INTEGER NOT NULL,
            origin TEXT NOT NULL,
            dest TEXT NOT NULL,
            airline TEXT NOT NULL,
            distance REAL NOT NULL,
            passengers INTEGER NOT NULL,
            fare REAL NOT NULL,
            stops INTEGER NOT NULL,
            coupons INTEGER NOT NULL,
            origin_state TEXT NOT NULL,
            dest_state TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS load_log (
            year INTEGER NOT NULL,
            quarter INTEGER NOT NULL,
            rows INTEGER NOT NULL,
            source_file TEXT NOT NULL,
            PRIMARY KEY (year, quarter)
        );
        CREATE TABLE IF NOT EXISTS airports (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            city TEXT NOT NULL,
            country TEXT NOT NULL,
            lat REAL,
            lon REAL,
            timezone TEXT,
            passengers INTEGER NOT NULL DEFAULT 0
        );
        """
    )


def reset_market_fares(connection: sqlite3.Connection) -> None:
    """Replace the fare extract. Other application tables are not in this file."""
    connection.executescript(
        """
        DROP TABLE IF EXISTS market_fares;
        DROP TABLE IF EXISTS load_log;
        DROP TABLE IF EXISTS airports;
        DROP TABLE IF EXISTS route_quantiles;
        DROP TABLE IF EXISTS slice_quantiles;
        """
    )
    ensure_schema(connection)
    connection.execute(
        "INSERT OR REPLACE INTO dot_meta (key, value) VALUES ('schema', ?)",
        (SCHEMA_VERSION,),
    )
    connection.commit()


def loaded_quarters(connection: sqlite3.Connection) -> set[tuple[int, int]]:
    ensure_schema(connection)
    rows = connection.execute("SELECT year, quarter FROM load_log").fetchall()
    return {(row["year"], row["quarter"]) for row in rows}


def known_airport(code: str, path: Path | None = None) -> bool:
    target = path or DB_PATH
    if not target.exists():
        return False
    connection = connect(target)
    try:
        row = connection.execute(
            "SELECT 1 FROM airports WHERE code = ?",
            (code.strip().upper(),),
        ).fetchone()
    except sqlite3.OperationalError:
        return False
    finally:
        connection.close()
    return row is not None


def route_summary(origin: str, dest: str, path: Path | None = None) -> dict:
    """Passenger counts for one airport pair, if the file exists."""
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
