"""Download DB1B Market quarters and keep fares for catalog US airports.

Raw zips stay in backend/data/raw, which is gitignored. Re-running skips a
quarter that is already in the sqlite file.
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
    QUARTERS,
    RAW_DIR,
    connect,
    ensure_schema,
    loaded_quarters,
    normalize_fare,
    quarter_url,
    us_airports,
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
}


def _download(year: int, quarter: int) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    destination = RAW_DIR / f"DB1BMarket_{year}_{quarter}.zip"
    url = quarter_url(year, quarter)
    request = Request(url, headers={"User-Agent": "flight-price-tracker"})
    with urlopen(request, timeout=120) as response:
        expected = int(response.headers.get("Content-Length") or 0)
        if destination.exists() and expected and destination.stat().st_size == expected:
            print(f"already downloaded {destination.name}", flush=True)
            return destination
        temporary = destination.with_suffix(".zip.partial")
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


def _load_zip(connection, path: Path, year: int, quarter: int, airports: set[str]) -> int:
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
                    },
                    airports,
                )
                if parsed is None:
                    continue
                if parsed[0] != year or parsed[1] != quarter:
                    continue
                if kept < 5:
                    print(
                        f"  sample {parsed[2]}-{parsed[3]} {parsed[4]} "
                        f"passengers={parsed[6]} fare={parsed[7]} stops={parsed[8]}",
                        flush=True,
                    )
                batch.append(parsed)
                kept += 1
                if len(batch) >= 5000:
                    connection.executemany(
                        """
                        INSERT INTO market_fares (
                            year, quarter, origin, dest, airline, distance, passengers, fare, stops
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        batch,
                    )
                    batch.clear()
    if batch:
        connection.executemany(
            """
            INSERT INTO market_fares (
                year, quarter, origin, dest, airline, distance, passengers, fare, stops
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            batch,
        )
    connection.execute(
        "INSERT OR REPLACE INTO load_log (year, quarter, rows, source_file) VALUES (?, ?, ?, ?)",
        (year, quarter, kept, path.name),
    )
    connection.commit()
    print(f"{year} Q{quarter}: kept {kept:,} of {scanned:,} rows", flush=True)
    return kept


def main() -> None:
    airports = us_airports()
    connection = connect(DB_PATH)
    try:
        ensure_schema(connection)
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = OFF")
        done = loaded_quarters(connection)
        for year, quarter in QUARTERS:
            if (year, quarter) in done:
                print(f"skip {year} Q{quarter}", flush=True)
                continue
            path = _download(year, quarter)
            _load_zip(connection, path, year, quarter, airports)
        connection.execute("CREATE INDEX IF NOT EXISTS idx_market_route ON market_fares(origin, dest)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_market_period ON market_fares(year, quarter)")
        connection.commit()
        total = connection.execute("SELECT COUNT(*) FROM market_fares").fetchone()[0]
        sample = connection.execute(
            """
            SELECT COUNT(*) AS rows, ROUND(AVG(fare), 1) AS avg_fare
            FROM market_fares
            WHERE origin = 'JFK' AND dest = 'LAX'
            """
        ).fetchone()
        print(f"stored {total:,} fares in {DB_PATH}", flush=True)
        print(f"JFK-LAX rows={sample['rows']} avg={sample['avg_fare']}", flush=True)
    finally:
        connection.close()


if __name__ == "__main__":
    main()
