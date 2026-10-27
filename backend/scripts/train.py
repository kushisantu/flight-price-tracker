"""Build the empirical paid-fare table from training quarters only."""

from __future__ import annotations

import numpy as np

from app.services.db1b import DB_PATH, connect
from app.services.empirical import SEED, build_quantile_tables


def main() -> None:
    np.random.seed(SEED)
    if not DB_PATH.exists():
        raise SystemExit("Load DB1B first: python -m scripts.load_db1b")
    connection = connect()
    try:
        stats = build_quantile_tables(connection)
    finally:
        connection.close()
    print(
        f"saved {stats['version']}  routes {stats['routes']:,}  slices {stats['slices']:,}",
        flush=True,
    )


if __name__ == "__main__":
    main()
