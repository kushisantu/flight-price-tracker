"""Download DB1B Market quarters and keep every airport in those files.

Raw zips stay in backend/data/raw, which is gitignored. This replaces the
market_fares rows so the old airport whitelist is not left in place.
"""

from __future__ import annotations

import csv
import sys
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.services.db1b import (  # noqa: E402
    DB_PATH,
    OPENFLIGHTS_URL,
    QUARTERS,
    RAW_DIR,
    connect,
    loaded_quarters,
    normalize_fare,
    quarter_url,
    reset_market_fares,
)

csv.field_size_limit(10_000_000)

COLUMNS = {
    "year": "year",
    "quarter": "quarter",
    "origin": "origin",
    "dest": "dest",
    "tkcarrier": "tk",
    "opcarrier": "op",
    "bulkfare": "bulk",
    "passengers": "passengers",
    "mktfare": "fare",
    "mktdistance": "distance",
    "mktcoupons": "coupons",
    "originstate": "origin_state",
    "deststate": "dest_state",
}

INSERT = """
INSERT INTO market_fares (
    year, quarter, origin, dest, airline, distance, passengers, fare, stops,
    coupons, origin_state, dest_state
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def _download(url: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": "flight-price-tracker"})
    with urlopen(request, timeout=120) as response:
        expected = int(response.headers.get("Content-Length") or 0)
        if destination.exists() and expected and destination.stat().st_size == expected:
            print(f"already downloaded {destination.name}", flush=True)
            return destination
        temporary = destination.with_suffix(destination.suffix + ".partial")
        written = 0
        with temporary.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                written += len(chunk)
                if written % (20 * 1024 * 1024) < 1024 * 1024:
                    print(f"  {destination.name} {written // (1024 * 1024)} MB", flush=True)
        temporary.replace(destination)
    print(f"saved {destination.name}", flush=True)
    return destination


def _header_map(header: list[str]) -> dict[str, int]:
    lookup = {name.strip().lower(): index for index, name in enumerate(header)}
    found = {}
    for source, alias in COLUMNS.items():
        if source not in lookup:
            raise ValueError(f"DB1B file is missing the {source} column.")
        found[alias] = lookup[source]
    return found


def _load_zip(connection, path: Path, year: int, quarter: int, airport_passengers: dict[str, int]) -> int:
    kept = 0
    scanned = 0
    batch: list[tuple] = []
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if not names:
            raise ValueError(f"{path.name} has no CSV.")
        with archive.open(names[0], "r") as raw:
            text = (line.decode("utf-8", "replace") for line in raw)
            reader = csv.reader(text)
            columns = _header_map(next(reader))

            def cell(row: list[str], alias: str) -> str:
                index = columns[alias]
                return row[index] if index < len(row) else ""

            for row in reader:
                scanned += 1
                if scanned % 1_000_000 == 0:
                    print(f"  {path.name} scanned {scanned:,} kept {kept:,}", flush=True)
                parsed = normalize_fare(
                    {
                        "year": cell(row, "year"),
                        "quarter": cell(row, "quarter"),
                        "origin": cell(row, "origin"),
                        "dest": cell(row, "dest"),
                        "tk": cell(row, "tk"),
                        "op": cell(row, "op"),
                        "bulk": cell(row, "bulk"),
                        "passengers": cell(row, "passengers"),
                        "fare": cell(row, "fare"),
                        "distance": cell(row, "distance"),
                        "coupons": cell(row, "coupons"),
                        "origin_state": cell(row, "origin_state"),
                        "dest_state": cell(row, "dest_state"),
                    }
                )
                if parsed is None or parsed[0] != year or parsed[1] != quarter:
                    continue
                airport_passengers[parsed[2]] = airport_passengers.get(parsed[2], 0) + parsed[6]
                airport_passengers[parsed[3]] = airport_passengers.get(parsed[3], 0) + parsed[6]
                batch.append(parsed)
                kept += 1
                if len(batch) >= 10000:
                    connection.executemany(INSERT, batch)
                    batch.clear()
    if batch:
        connection.executemany(INSERT, batch)
    connection.execute(
        "INSERT OR REPLACE INTO load_log (year, quarter, rows, source_file) VALUES (?, ?, ?, ?)",
        (year, quarter, kept, path.name),
    )
    connection.commit()
    print(f"{year} Q{quarter}: kept {kept:,} of {scanned:,} rows", flush=True)
    return kept


def _openflights(connection, airport_passengers: dict[str, int]) -> None:
    path = _download(OPENFLIGHTS_URL, RAW_DIR / "airports.dat")
    found: set[str] = set()
    with path.open(encoding="utf-8", errors="replace", newline="") as handle:
        for row in csv.reader(handle):
            if len(row) < 12:
                continue
            code = row[4].strip().upper()
            if code not in airport_passengers or code in ("\\N", ""):
                continue
            try:
                lat = float(row[6])
                lon = float(row[7])
            except ValueError:
                lat = lon = None
            name = row[1].strip() or "Name unavailable"
            city = row[2].strip() or code
            country = row[3].strip()
            timezone = row[11].strip()
            if timezone == "\\N":
                timezone = ""
            connection.execute(
                """
                INSERT OR REPLACE INTO airports (code, name, city, country, lat, lon, timezone, passengers)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (code, name, city, country, lat, lon, timezone, airport_passengers[code]),
            )
            found.add(code)
    for code, passengers in airport_passengers.items():
        if code in found:
            continue
        connection.execute(
            """
            INSERT INTO airports (code, name, city, country, lat, lon, timezone, passengers)
            VALUES (?, 'Name unavailable', ?, '', NULL, NULL, '', ?)
            """,
            (code, code, passengers),
        )
    connection.commit()
    print(f"airports {len(airport_passengers):,}  named {len(found):,}", flush=True)


def main() -> None:
    connection = connect(DB_PATH)
    airport_passengers: dict[str, int] = {}
    try:
        reset_market_fares(connection)
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = OFF")
        done = loaded_quarters(connection)
        for year, quarter in QUARTERS:
            if (year, quarter) in done:
                print(f"skip {year} Q{quarter}", flush=True)
                continue
            path = _download(quarter_url(year, quarter), RAW_DIR / f"DB1BMarket_{year}_{quarter}.zip")
            _load_zip(connection, path, year, quarter, airport_passengers)
        connection.execute("CREATE INDEX IF NOT EXISTS idx_market_route ON market_fares(origin, dest)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_market_period ON market_fares(year, quarter)")
        connection.commit()
        _openflights(connection, airport_passengers)
        total = connection.execute("SELECT COUNT(*) FROM market_fares").fetchone()[0]
        airports = connection.execute("SELECT COUNT(*) FROM airports").fetchone()[0]
        print(f"stored {total:,} fares and {airports:,} airports in {DB_PATH}", flush=True)
    finally:
        connection.close()


if __name__ == "__main__":
    main()
