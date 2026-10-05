"""Sample fare engine.

Prices come from a seeded market simulator. Distance, season, weekday, cabin,
and how far ahead you look set a base fare, and a hidden demand path moves it.
The same inputs always return the same fare, so charts and alerts stay stable.
Swap this module for a live provider later.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache

from app.catalog import AIRLINES, AIRPORTS, get_place, region_of

CABINS = {
    "economy": 1.0,
    "premium": 1.6,
    "business": 3.1,
    "first": 4.6,
}
EMISSIONS = {
    "economy": 1.0,
    "premium": 1.45,
    "business": 2.3,
    "first": 3.2,
}
LONG_HAUL = {
    "DL", "UA", "AA", "BA", "LH", "AF", "KL", "AC", "IB", "TK",
    "EK", "QR", "SQ", "JL", "NH", "QF", "KE", "CX", "LA",
}
LCC = {"WN", "NK", "F9", "B6", "AS"}
SHORT_HAUL_AIRPORTS = {"LGA", "MDW", "DCA"}
DOW = {0: 0.98, 1: 0.94, 2: 0.94, 3: 0.97, 4: 1.06, 5: 1.03, 6: 1.08}
FEATURED = [
    ("LON", "London"),
    ("PAR", "Paris"),
    ("TYO", "Tokyo"),
    ("LAX", "Los Angeles"),
    ("MIA", "Miami"),
    ("CUN", "Cancun"),
    ("DXB", "Dubai"),
    ("HNL", "Honolulu"),
    ("SFO", "San Francisco"),
    ("DUB", "Dublin"),
    ("BCN", "Barcelona"),
    ("SYD", "Sydney"),
]


@dataclass
class TripQuery:
    origin: str
    destination: str
    depart: date
    ret: date | None
    passengers: int = 1
    cabin: str = "economy"
    trip_type: str = "round"
    observed: date | None = None

    def __post_init__(self) -> None:
        self.origin = self.origin.strip().upper()
        self.destination = self.destination.strip().upper()
        self.cabin = self.cabin if self.cabin in CABINS else "economy"
        self.passengers = min(6, max(1, int(self.passengers)))
        if self.observed is None:
            self.observed = date.today()
        if self.trip_type == "oneway":
            self.ret = None
        elif self.ret is None:
            self.ret = self.depart + timedelta(days=7)
            self.trip_type = "round"


def from_payload(data: dict, observed: date | None = None) -> TripQuery:
    depart = _as_date(data["depart_date"])
    ret_raw = data.get("return_date")
    trip_type = data.get("trip_type") or "round"
    ret = None if trip_type == "oneway" or not ret_raw else _as_date(ret_raw)
    query = TripQuery(
        origin=data["origin"],
        destination=data["destination"],
        depart=depart,
        ret=ret,
        passengers=int(data.get("passengers") or 1),
        cabin=data.get("cabin") or "economy",
        trip_type="oneway" if trip_type == "oneway" else "round",
        observed=observed or date.today(),
    )
    _validate(query)
    return query


def _as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _validate(query: TripQuery) -> None:
    get_place(query.origin)
    get_place(query.destination)
    if query.origin == query.destination:
        raise ValueError("Choose two different places.")
    if set(get_place(query.origin)["airports"]) == set(get_place(query.destination)["airports"]):
        raise ValueError("Choose two different places.")
    if query.depart < date.today():
        raise ValueError("Departure date is in the past.")
    if query.ret and query.ret <= query.depart:
        raise ValueError("Return date must be after departure.")
    if query.observed and query.observed > query.depart:
        raise ValueError("That departure date had already passed on the observation day.")


def _hash_unit(*parts: str) -> float:
    raw = "|".join(parts).encode()
    return int(hashlib.md5(raw).hexdigest()[:8], 16) / 0xFFFFFFFF


def distance_km(origin: dict, dest: dict) -> float:
    radius = 6371.0
    lat1, lat2 = math.radians(origin["lat"]), math.radians(dest["lat"])
    dlat = math.radians(dest["lat"] - origin["lat"])
    dlon = math.radians(dest["lon"] - origin["lon"])
    hav = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(hav))


def _advance(days_out: int) -> float:
    points = [(0, 1.92), (3, 1.7), (7, 1.42), (14, 1.18), (21, 1.05), (35, 0.9), (60, 0.95), (90, 1.0), (150, 1.08), (280, 1.18)]
    if days_out <= points[0][0]:
        return points[0][1]
    for (left_day, left_mult), (right_day, right_mult) in zip(points, points[1:]):
        if days_out <= right_day:
            span = right_day - left_day
            weight = (days_out - left_day) / span
            return left_mult + (right_mult - left_mult) * weight
    return points[-1][1]


def _season(day: date) -> float:
    month_day = (day.month, day.day)
    if month_day >= (12, 15) or month_day <= (1, 6):
        return 1.22
    if (11, 20) <= month_day <= (11, 30):
        return 1.1
    if day.month in (6, 7, 8):
        return 1.16
    if day.month == 3 and 8 <= day.day <= 28:
        return 1.08
    if day.month in (1, 2, 9, 10):
        return 0.96
    return 1.0


def _market(origin: dict, dest: dict, km: float) -> float:
    left, right = region_of(origin), region_of(dest)
    pair = {left, right}
    if pair == {"na"}:
        if km < 900:
            return 1.35
        if km < 2000:
            return 1.1
        return 0.95
    if pair == {"na", "eu"}:
        return 0.82
    if "asia" in pair and "na" in pair:
        return 0.88
    if "oc" in pair:
        return 0.92
    if "me" in pair or "af" in pair:
        return 0.9
    if pair == {"eu"}:
        return 1.25
    return 0.94


def carriers_for(origin: dict, dest: dict) -> list[dict]:
    left, right = region_of(origin), region_of(dest)
    km = distance_km(origin, dest)
    codes: set[str] = set()
    pair = {left, right}
    if pair == {"na"}:
        codes.update({"DL", "UA", "AA", "WN", "B6", "AS", "NK", "F9"})
        if "Canada" in (origin["country"], dest["country"]):
            codes.add("AC")
        if km > 4500:
            codes -= {"WN", "NK", "F9", "B6"}
    if pair == {"eu"}:
        codes.update({"BA", "LH", "AF", "KL", "IB", "TK"})
    if pair == {"asia"}:
        codes.update({"JL", "NH", "SQ", "KE", "CX"})
    if pair == {"oc"}:
        codes.update({"QF"})
    if left != right:
        if pair == {"na", "eu"}:
            codes.update({"DL", "UA", "AA", "BA", "LH", "AF", "KL", "AC", "IB"})
        if "me" in pair or "af" in pair:
            codes.update({"EK", "QR", "TK", "DL", "UA", "BA", "LH", "AF"})
        if "asia" in pair:
            codes.update({"UA", "DL", "AA", "JL", "NH", "SQ", "KE", "CX"})
        if "oc" in pair:
            codes.update({"QF", "UA", "DL", "AA"})
        if "latam" in pair:
            codes.update({"AA", "DL", "UA", "LA"})
        codes -= LCC
    if not codes:
        codes.update({"DL", "UA", "AA"})
    return [AIRLINES[code] for code in sorted(codes) if code in AIRLINES]


def allows_nonstop(airline_code: str, origin: dict, dest: dict) -> bool:
    km = distance_km(origin, dest)
    if km > 3200 and (origin["code"] in SHORT_HAUL_AIRPORTS or dest["code"] in SHORT_HAUL_AIRPORTS):
        return False
    return nonstop_ok(airline_code, km)


def nonstop_ok(airline_code: str, km: float) -> bool:
    if airline_code in {"NK", "F9"}:
        return km <= 3600
    if airline_code == "WN":
        return km <= 4000
    if airline_code in {"B6", "AS"}:
        return km <= 5000
    if km <= 4500:
        return True
    if km <= 10000 and airline_code in LONG_HAUL:
        return True
    if km <= 16000 and airline_code in {"EK", "QR", "SQ", "QF", "CX", "JL", "NH", "KE", "UA", "DL", "AA"}:
        return True
    return False


def connection_hub(airline: dict, origin: dict, dest: dict) -> dict | None:
    direct = distance_km(origin, dest)
    best = None
    best_extra = None
    for code in airline["hubs"]:
        if code in (origin["code"], dest["code"]):
            continue
        hub = AIRPORTS.get(code)
        if hub is None:
            continue
        extra = distance_km(origin, hub) + distance_km(hub, dest) - direct
        if extra < 120:
            continue
        if best is None or extra < best_extra:
            best = hub
            best_extra = extra
    if best is not None and best_extra is not None and best_extra > max(7500, direct * 0.85):
        return None
    return best


def _air_minutes(km: float) -> int:
    return max(48, int(round(km / 830 * 60 + 22)))


def _clock(airline: str, origin: str, dest: str, stops: int, slot: int, day: date) -> int:
    start = [6 * 60 + 25, 11 * 60 + 35, 17 * 60 + 10][slot]
    span = [150, 160, 150][slot]
    bump = int(_hash_unit(airline, origin, dest, str(stops), str(slot), day.isoformat()) * span)
    return start + bump


def _at(day: date, minutes: int) -> datetime:
    return datetime.combine(day, datetime.min.time()) + timedelta(minutes=minutes)


def _arrive(depart_at: datetime, duration: int, origin: dict, dest: dict) -> datetime:
    shift = float(dest["tz"]) - float(origin["tz"])
    return depart_at + timedelta(minutes=duration) + timedelta(hours=shift)


def _aircraft(airline: str, km: float, key: str) -> str:
    if airline in {"NK", "F9", "WN", "B6", "AS"}:
        return "Airbus A320" if _hash_unit(key, "ac") > 0.5 else "Boeing 737-800"
    if km < 1800:
        return "Airbus A320neo"
    if km < 4500:
        return "Boeing 737 MAX 8"
    if km < 8000:
        return "Boeing 787-9"
    return "Airbus A350-900"


@lru_cache(maxsize=200_000)
def _unit_fare(
    origin_code: str,
    dest_code: str,
    airline_code: str,
    stops: int,
    cabin: str,
    depart_iso: str,
    observed_iso: str,
    passengers: int = 1,
) -> int:
    from app.services.simulator import DEFAULT_SEED, fare_on

    return fare_on(
        origin_code,
        dest_code,
        airline_code,
        stops,
        cabin,
        date.fromisoformat(depart_iso),
        date.fromisoformat(observed_iso),
        passengers,
        DEFAULT_SEED,
    )


def _leg(
    origin: dict,
    dest: dict,
    day: date,
    airline: dict,
    stops: int,
    slot: int,
    cabin: str,
) -> dict | None:
    km = distance_km(origin, dest)
    if stops == 0 and not nonstop_ok(airline["code"], km):
        return None
    hub = None
    path_km = km
    layover = 0
    if stops == 1:
        hub = connection_hub(airline, origin, dest)
        if hub is None:
            return None
        path_km = distance_km(origin, hub) + distance_km(hub, dest)
        layover = 70 + int(_hash_unit(airline["code"], origin["code"], dest["code"], "lay") * 55)
        duration = _air_minutes(distance_km(origin, hub)) + _air_minutes(distance_km(hub, dest)) + layover
    else:
        duration = _air_minutes(km)

    depart_at = _at(day, _clock(airline["code"], origin["code"], dest["code"], stops, slot, day))
    arrive_at = _arrive(depart_at, duration, origin, dest)
    number = 100 + int(_hash_unit(airline["code"], origin["code"], dest["code"], str(stops), str(slot)) * 800)
    return {
        "origin": origin["code"],
        "origin_city": origin["city"],
        "destination": dest["code"],
        "destination_city": dest["city"],
        "depart_at": depart_at.isoformat(timespec="minutes"),
        "arrive_at": arrive_at.isoformat(timespec="minutes"),
        "duration_minutes": int(duration),
        "airline_code": airline["code"],
        "airline_name": airline["name"],
        "airline_color": airline["color"],
        "flight_number": f"{airline['code']} {number}",
        "stops": stops,
        "stop_city": hub["city"] if hub else None,
        "stop_code": hub["code"] if hub else None,
        "layover_minutes": max(0, int(layover)),
        "aircraft": _aircraft(airline["code"], path_km, f"{origin['code']}{dest['code']}{slot}"),
        "emissions_kg": int(round(path_km * 0.095 * EMISSIONS[cabin])),
    }


def _airports(code: str) -> list[dict]:
    return [AIRPORTS[item] for item in get_place(code)["airports"]]


def _candidates(query: TripQuery) -> list[dict]:
    origins = _airports(query.origin)
    destinations = _airports(query.destination)
    flights: list[dict] = []
    observed = query.observed.isoformat()
    for origin in origins:
        for dest in destinations:
            if origin["code"] == dest["code"]:
                continue
            for airline in carriers_for(origin, dest):
                direct = distance_km(origin, dest)
                patterns = []
                if allows_nonstop(airline["code"], origin, dest):
                    patterns.append((0, 0))
                    patterns.append((0, 2))
                if connection_hub(airline, origin, dest):
                    patterns.append((1, 1))
                for stops, slot in patterns:
                    outbound = _leg(origin, dest, query.depart, airline, stops, slot, query.cabin)
                    if outbound is None:
                        continue
                    legs = [outbound]
                    price = _unit_fare(
                        origin["code"], dest["code"], airline["code"], stops, query.cabin,
                        query.depart.isoformat(), observed, query.passengers,
                    )
                    if query.ret:
                        back_slot = (slot + 1) % 3
                        inbound = _leg(dest, origin, query.ret, airline, stops, back_slot, query.cabin)
                        if inbound is None:
                            continue
                        legs.append(inbound)
                        price += _unit_fare(
                            dest["code"], origin["code"], airline["code"], stops, query.cabin,
                            query.ret.isoformat(), observed, query.passengers,
                        )
                    flights.append({
                        "id": f"{origin['code']}-{dest['code']}-{query.depart.isoformat()}-{airline['code']}-{stops}-{slot}-{query.cabin}",
                        "price": price,
                        "total_price": price * query.passengers,
                        "airline_code": airline["code"],
                        "airline_name": airline["name"],
                        "airline_color": airline["color"],
                        "stops": stops,
                        "total_duration_minutes": sum(leg["duration_minutes"] for leg in legs),
                        "emissions_kg": sum(leg["emissions_kg"] for leg in legs),
                        "bag_note": "Personal item only on the base fare" if airline["code"] in {"NK", "F9"} else "Carry-on included",
                        "legs": legs,
                    })
    return flights


def _diverse(flights: list[dict], limit: int = 24) -> list[dict]:
    ordered = sorted(flights, key=lambda flight: (flight["price"], flight["total_duration_minutes"]))
    picked: list[dict] = []
    seen: set[int] = set()

    def add(flight: dict, cap: int = 2) -> bool:
        marker = id(flight)
        if marker in seen:
            return False
        count = sum(1 for item in picked if item["airline_code"] == flight["airline_code"])
        if count >= cap:
            return False
        seen.add(marker)
        picked.append(flight)
        return True

    for stops in (0, 1):
        seen_airlines: set[str] = set()
        for flight in ordered:
            if flight["stops"] != stops or flight["airline_code"] in seen_airlines:
                continue
            if add(flight):
                seen_airlines.add(flight["airline_code"])
    for flight in ordered:
        if len(picked) >= limit:
            break
        add(flight)
    return picked[:limit]


def _rank(flights: list[dict]) -> list[dict]:
    if not flights:
        return []
    prices = [flight["price"] for flight in flights]
    durations = [flight["total_duration_minutes"] for flight in flights]
    low_p, high_p = min(prices), max(prices)
    low_d, high_d = min(durations), max(durations)

    def score(flight: dict) -> float:
        price_part = (flight["price"] - low_p) / (high_p - low_p or 1)
        time_part = (flight["total_duration_minutes"] - low_d) / (high_d - low_d or 1)
        nonstop_bonus = 0.06 if flight["stops"] == 0 else 0
        return price_part * 0.58 + time_part * 0.42 - nonstop_bonus

    for flight in flights:
        flight["score"] = round(score(flight), 4)
    flights.sort(key=lambda flight: flight["score"])
    return flights


@lru_cache(maxsize=50_000)
def _carrier_codes(origin_code: str, dest_code: str) -> tuple[str, ...]:
    return tuple(airline["code"] for airline in carriers_for(AIRPORTS[origin_code], AIRPORTS[dest_code]))


@lru_cache(maxsize=50_000)
def _hub_code(airline_code: str, origin_code: str, dest_code: str) -> str | None:
    hub = connection_hub(AIRLINES[airline_code], AIRPORTS[origin_code], AIRPORTS[dest_code])
    return None if hub is None else hub["code"]


def quote_parts(query: TripQuery, airline_code: str | None = None, stops: int | None = None) -> tuple[int, str, int]:
    """Cheapest per-person fare without building flight times."""
    _validate(query)
    observed = query.observed.isoformat()
    best: tuple[int, str, int] | None = None
    for origin in _airports(query.origin):
        for dest in _airports(query.destination):
            if origin["code"] == dest["code"]:
                continue
            direct = distance_km(origin, dest)
            for code in _carrier_codes(origin["code"], dest["code"]):
                if airline_code and code != airline_code:
                    continue
                choices = []
                if allows_nonstop(code, origin, dest):
                    choices.append(0)
                if _hub_code(code, origin["code"], dest["code"]):
                    choices.append(1)
                for stop_count in choices:
                    if stops is not None and stop_count != stops:
                        continue
                    price = _unit_fare(
                        origin["code"], dest["code"], code, stop_count, query.cabin,
                        query.depart.isoformat(), observed, query.passengers,
                    )
                    if query.ret:
                        price += _unit_fare(
                            dest["code"], origin["code"], code, stop_count, query.cabin,
                            query.ret.isoformat(), observed, query.passengers,
                        )
                    if best is None or price < best[0] or (price == best[0] and stop_count < best[2]):
                        best = (price, code, stop_count)
    if best is None:
        raise ValueError("No fares are available for that route.")
    return best


def search(data: dict) -> dict:
    query = from_payload(data)
    flights = _rank(_diverse(_candidates(query)))
    if not flights:
        raise ValueError("No fares are available for that route.")
    history = price_history(query)
    strip = date_strip(query)
    return {
        "provider": "sample",
        "criteria": _public(query),
        "flights": flights,
        "date_strip": strip,
        "history": history,
        "insight": build_insight(query, history, strip),
    }


def price_history(query: TripQuery, days: int = 90) -> list[dict]:
    points = []
    start = query.observed - timedelta(days=days - 1)
    for offset in range(days):
        observed = start + timedelta(days=offset)
        if observed > query.observed or observed > query.depart:
            continue
        past = TripQuery(
            origin=query.origin,
            destination=query.destination,
            depart=query.depart,
            ret=query.ret,
            passengers=query.passengers,
            cabin=query.cabin,
            trip_type=query.trip_type,
            observed=observed,
        )
        price, _, _ = quote_parts(past)
        points.append({"date": observed.isoformat(), "price": price})
    return points


def date_strip(query: TripQuery) -> list[dict]:
    length = (query.ret - query.depart) if query.ret else None
    rows = []
    for offset in range(-3, 4):
        day = query.depart + timedelta(days=offset)
        if day < date.today():
            continue
        ret = day + length if length is not None else None
        past = TripQuery(
            origin=query.origin,
            destination=query.destination,
            depart=day,
            ret=ret,
            passengers=query.passengers,
            cabin=query.cabin,
            trip_type="oneway" if ret is None else "round",
            observed=query.observed,
        )
        try:
            price, _, _ = quote_parts(past)
        except ValueError:
            continue
        rows.append({
            "date": day.isoformat(),
            "return_date": ret.isoformat() if ret else None,
            "price": price,
            "selected": offset == 0,
        })
    return rows


def calendar(origin: str, destination: str, month: str, nights: int, cabin: str, trip_type: str) -> dict:
    year_text, month_text = month.split("-")
    year, month_number = int(year_text), int(month_text)
    if month_number == 12:
        last = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last = date(year, month_number + 1, 1) - timedelta(days=1)
    today = date.today()
    days = []
    cursor = date(year, month_number, 1)
    while cursor <= last:
        price = None
        if cursor >= today:
            ret = None if trip_type == "oneway" else cursor + timedelta(days=max(1, nights))
            try:
                price, _, _ = quote_parts(TripQuery(
                    origin=origin,
                    destination=destination,
                    depart=cursor,
                    ret=ret,
                    cabin=cabin,
                    trip_type=trip_type,
                ))
            except ValueError:
                price = None
        days.append({"date": cursor.isoformat(), "price": price})
        cursor += timedelta(days=1)
    return {"month": f"{year:04d}-{month_number:02d}", "days": days}


def build_insight(query: TripQuery, history: list[dict], strip: list[dict]) -> dict:
    prices = [point["price"] for point in history] or [0]
    current = prices[-1]
    average = int(round(sum(prices) / len(prices)))
    low, high = min(prices), max(prices)
    percentile = int(round(100 * sum(1 for price in prices if price <= current) / len(prices)))
    recent = prices[-14:]
    prior = prices[-28:-14] or recent
    recent_avg = sum(recent) / len(recent)
    prior_avg = sum(prior) / len(prior)
    if recent_avg < prior_avg * 0.97:
        trend = "falling"
    elif recent_avg > prior_avg * 1.03:
        trend = "rising"
    else:
        trend = "flat"

    if current <= average * 0.92:
        level = "low"
        title = "Prices are lower than usual"
    elif current >= average * 1.08:
        level = "high"
        title = "Prices are higher than usual"
    else:
        level = "typical"
        title = "Prices are typical"

    days_out = (query.depart - query.observed).days
    gap = abs(current - average)
    direction = "below" if current <= average else "above"
    summary = (
        f"Today's cheapest fare is ${current:,} per person, "
        f"${gap:,} {direction} the 90-day average of ${average:,}."
    )
    if days_out <= 7:
        advice = "Departure is close. Fares this near the flight usually climb from here."
    elif level == "low" and trend != "rising":
        advice = "This is a good time to book. The fare is in the low part of its recent range."
    elif trend == "falling" and days_out > 21:
        advice = "Fares have been drifting down. Waiting a few days could help, and the price can still turn."
    elif level == "high":
        advice = "This date is priced higher than most of the last 90 days. Check a nearby date before you book."
    elif trend == "rising":
        advice = "The fare has been rising. Booking sooner is the safer move if these dates work."
    else:
        advice = "This is a fairly typical fare for these dates."

    alternative = None
    if strip:
        best = min(strip, key=lambda item: item["price"])
        savings = current - best["price"]
        if best["date"] != query.depart.isoformat() and savings >= max(30, int(current * 0.06)):
            alternative = {
                "depart_date": best["date"],
                "return_date": best["return_date"],
                "price": best["price"],
                "savings": savings,
            }
            advice = f"Leaving on that nearby date saves ${savings:,} per person. {advice}"

    return {
        "level": level,
        "title": title,
        "summary": summary,
        "advice": advice,
        "percentile": percentile,
        "average": average,
        "low": low,
        "high": high,
        "current": current,
        "trend": trend,
        "alternative": alternative,
    }


def outlook(data: dict) -> dict:
    query = from_payload(data)
    history = price_history(query)
    strip = date_strip(query)
    return {
        "provider": "sample",
        "criteria": _public(query),
        "history": history,
        "insight": build_insight(query, history, strip),
    }


def deals(origin: str) -> dict:
    place = get_place(origin)
    today = date.today()
    cursor = today + timedelta(days=35)
    while cursor.weekday() != 1:
        cursor += timedelta(days=1)
    found = []
    for index, (code, _name) in enumerate(FEATURED):
        dest = get_place(code)
        if dest["city"] == place["city"] or dest["code"] == place["code"]:
            continue
        depart = cursor + timedelta(days=(index % 3) * 2)
        ret = depart + timedelta(days=7)
        query = TripQuery(origin=place["code"], destination=code, depart=depart, ret=ret)
        try:
            history = []
            for week in range(11, -1, -1):
                observed = today - timedelta(days=7 * week)
                if observed > depart:
                    continue
                price, _, _ = quote_parts(TripQuery(
                    origin=place["code"],
                    destination=code,
                    depart=depart,
                    ret=ret,
                    observed=observed,
                ))
                history.append(price)
            price = history[-1]
        except ValueError:
            continue
        average = sum(history) / len(history)
        if price < average * 0.95:
            level = "low"
        elif price > average * 1.08:
            level = "high"
        else:
            level = "typical"
        found.append({
            "destination": dest,
            "depart_date": depart.isoformat(),
            "return_date": ret.isoformat(),
            "price": price,
            "level": level,
            "history": history,
        })
        if len(found) >= 8:
            break
    return {"origin": place, "deals": found}


def _public(query: TripQuery) -> dict:
    return {
        "origin": get_place(query.origin),
        "destination": get_place(query.destination),
        "depart_date": query.depart.isoformat(),
        "return_date": query.ret.isoformat() if query.ret else None,
        "trip_type": query.trip_type,
        "passengers": query.passengers,
        "cabin": query.cabin,
    }


def log_quote(db, query: TripQuery, price: int, airline: str, stops: int) -> None:
    from app.models import PriceQuote

    return_key = query.ret.isoformat() if query.ret else ""
    existing = (
        db.query(PriceQuote)
        .filter_by(
            origin=query.origin,
            destination=query.destination,
            depart_date=query.depart,
            return_key=return_key,
            cabin=query.cabin,
            observed_on=query.observed,
        )
        .one_or_none()
    )
    if existing:
        existing.price = price
        existing.airline_code = airline
        existing.stops = stops
        existing.return_date = query.ret
        return
    db.add(PriceQuote(
        origin=query.origin,
        destination=query.destination,
        depart_date=query.depart,
        return_date=query.ret,
        return_key=return_key,
        cabin=query.cabin,
        observed_on=query.observed,
        price=price,
        airline_code=airline,
        stops=stops,
    ))
