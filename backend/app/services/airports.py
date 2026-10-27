"""Airport search over the DOT extract, with OpenFlights names when we have them."""

from __future__ import annotations

import sqlite3

from app.catalog import CITIES, POPULAR_CODES, get_place, search_places
from app.services.db1b import DB_PATH, connect


def _dot_place(row) -> dict:
    return {
        "code": row["code"],
        "type": "airport",
        "city": row["city"] or row["code"],
        "name": row["name"] or "Name unavailable",
        "country": row["country"] or "",
        "airports": [row["code"]],
    }


def _catalog_matches(needle: str) -> list[dict]:
    matches = []
    for code in POPULAR_CODES if not needle else CITIES:
        try:
            place = get_place(code)
        except ValueError:
            continue
        if needle and needle not in place["city"].lower() and needle != code.lower():
            continue
        matches.append(place)
    if needle:
        for place in search_places(needle, limit=8):
            if place["code"] not in {item["code"] for item in matches}:
                matches.append(place)
    return matches


def search_airports(query: str, limit: int = 8) -> list[dict]:
    needle = (query or "").strip().lower()
    if not DB_PATH.exists():
        return search_places(query, limit)
    try:
        connection = connect()
    except sqlite3.OperationalError:
        return search_places(query, limit)
    try:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'airports'"
        ).fetchone()
        if exists is None:
            return search_places(query, limit)
        if needle:
            rows = connection.execute(
                """
                SELECT code, name, city, country, passengers
                FROM airports
                WHERE code = ? OR city LIKE ? OR name LIKE ? OR code LIKE ?
                ORDER BY CASE WHEN code = ? THEN 0 WHEN city LIKE ? THEN 1 ELSE 2 END,
                         passengers DESC
                LIMIT ?
                """,
                (
                    needle.upper(),
                    f"{needle}%",
                    f"%{needle}%",
                    f"{needle}%",
                    needle.upper(),
                    f"{needle}%",
                    limit,
                ),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT code, name, city, country, passengers
                FROM airports
                ORDER BY passengers DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    except sqlite3.OperationalError:
        return search_places(query, limit)
    finally:
        connection.close()

    places = []
    seen = set()
    for place in _catalog_matches(needle):
        if place["type"] == "city" and place["code"] not in seen:
            places.append(place)
            seen.add(place["code"])
    for row in rows:
        if row["code"] in seen:
            continue
        places.append(_dot_place(row))
        seen.add(row["code"])
        if len(places) >= limit:
            break
    return places[:limit]
