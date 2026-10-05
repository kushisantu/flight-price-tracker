"""Plain-language trip search.

This parser handles a fixed set of phrases. A language model can replace it
later for requests like "somewhere warm next month under $400".
"""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta

from app.catalog import PLACE_ALIASES, get_place
from app.services.flights import TripQuery, quote_parts

WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
MONTHS = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}


def parse_smart(text: str, fallback_origin: str | None, today: date | None = None) -> dict:
    raw = " ".join((text or "").strip().split())
    if len(raw) < 3:
        raise ValueError('Try "New York to London in December under $700".')
    today = today or date.today()
    lowered = raw.lower()

    trip_type = "oneway" if re.search(r"\bone[\s-]?way\b", lowered) else "round"
    cabin = "economy"
    if "first class" in lowered:
        cabin = "first"
    elif "business" in lowered:
        cabin = "business"
    elif "premium" in lowered:
        cabin = "premium"

    passengers = 1
    people = re.search(r"\bfor (\d) (?:people|passengers|adults)\b", lowered)
    if people:
        passengers = int(people.group(1))

    max_price = None
    price_match = re.search(r"\b(?:under|below|less than)\s+\$?\s*(\d{2,5})\b", lowered)
    if price_match:
        max_price = int(price_match.group(1))

    nights = 7 if trip_type == "round" else None
    nights_match = re.search(r"\b(\d{1,2})\s+nights?\b", lowered)
    if nights_match:
        nights = int(nights_match.group(1))
        trip_type = "round"
    elif re.search(r"\bfor a week\b", lowered):
        nights = 7
        trip_type = "round"

    origin_code, dest_code = _places(lowered, fallback_origin)
    month = _month(lowered)
    weekday = _weekday(lowered)
    picked_reason = None

    if "weekend" in lowered and month is None and weekday is None:
        depart, ret = _weekend(today, nights)
        picked_reason = "the coming weekend"
    elif month is not None:
        year = _year_for_month(today, month)
        found = _cheapest_in_month(
            origin_code, dest_code, year, month, today, cabin, nights if trip_type == "round" else None, weekday,
        )
        if found is None and month == today.month:
            found = _cheapest_in_month(
                origin_code, dest_code, today.year + 1, month, today, cabin,
                nights if trip_type == "round" else None, weekday,
            )
        if found is None:
            raise ValueError("I couldn't find a future date in that month.")
        _price, depart, ret = found
        month_name = calendar.month_name[depart.month]
        if weekday is not None:
            picked_reason = f"the cheapest {calendar.day_name[weekday]} in {month_name}"
        else:
            picked_reason = f"the cheapest day in {month_name}"
    elif weekday is not None:
        depart = _next_named_day(today, weekday, "next" in lowered and "this" not in lowered)
        ret = depart + timedelta(days=nights) if trip_type == "round" and nights else None
    else:
        depart = today + timedelta(days=36)
        while depart.weekday() != 1:
            depart += timedelta(days=1)
        ret = depart + timedelta(days=nights) if trip_type == "round" and nights else None
        picked_reason = "a Tuesday about five weeks out"

    if trip_type == "oneway":
        ret = None

    origin = get_place(origin_code)
    destination = get_place(dest_code)
    interpretation = _sentence(origin, destination, depart, ret, cabin, passengers, picked_reason, max_price)
    return {
        "interpretation": interpretation,
        "max_price": max_price,
        "criteria": {
            "origin": origin,
            "destination": destination,
            "depart_date": depart.isoformat(),
            "return_date": ret.isoformat() if ret else None,
            "trip_type": "oneway" if ret is None else "round",
            "passengers": passengers,
            "cabin": cabin,
        },
    }


def _places(text: str, fallback_origin: str | None) -> tuple[str, str]:
    found = _find_places(text)
    splitter = re.search(r"\bto\b", text)
    if splitter:
        before = [item for item in found if item[0] < splitter.start()]
        after = [item for item in found if item[0] >= splitter.end()]
        dest = after[0][1] if after else None
        origin = before[0][1] if before else None
    elif len(found) >= 2:
        origin, dest = found[0][1], found[1][1]
    elif len(found) == 1:
        origin, dest = None, found[0][1]
    else:
        origin, dest = None, None

    if origin is None:
        origin = (fallback_origin or "").strip().upper() or None
    if origin is None or dest is None:
        raise ValueError('Name two places, such as "Chicago to Miami this weekend".')
    if origin == dest:
        raise ValueError("Choose two different places.")
    return origin, dest


def _find_places(text: str) -> list[tuple[int, str]]:
    found = []
    index = 0
    while index < len(text):
        if index > 0 and text[index - 1].isalnum():
            index += 1
            continue
        if not text[index].isalnum():
            index += 1
            continue
        match = None
        for phrase, code in PLACE_ALIASES:
            end = index + len(phrase)
            if text.startswith(phrase, index) and (end == len(text) or not text[end].isalnum()):
                match = (index, code, end)
                break
        if match:
            found.append((match[0], match[1]))
            index = match[2]
        else:
            index += 1
    return found


def _month(text: str) -> int | None:
    match = re.search(
        r"\b(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\b",
        text,
    )
    if not match:
        return None
    return MONTHS[match.group(1)]


def _weekday(text: str) -> int | None:
    match = re.search(r"\b(?:next|this)?\s*(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", text)
    if not match:
        return None
    return WEEKDAYS[match.group(1)]


def _year_for_month(today: date, month: int) -> int:
    if month < today.month:
        return today.year + 1
    return today.year


def _next_named_day(today: date, weekday: int, force_next: bool) -> date:
    delta = (weekday - today.weekday()) % 7
    if delta == 0 and force_next:
        delta = 7
    if delta == 0 and not force_next:
        return today
    return today + timedelta(days=delta or 7)


def _weekend(today: date, nights: int | None) -> tuple[date, date | None]:
    if today.weekday() == 6:
        start = today + timedelta(days=5)
    elif today.weekday() in (4, 5):
        start = today if today.weekday() == 4 else today - timedelta(days=1)
        if today.weekday() == 5:
            start = today - timedelta(days=1)
    else:
        start = today + timedelta(days=(4 - today.weekday()) % 7)
    span = nights if nights and nights != 7 else 2
    return start, start + timedelta(days=span)


def _cheapest_in_month(origin, dest, year, month, today, cabin, nights, weekday):
    if month == 12:
        last = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    best = None
    cursor = date(year, month, 1)
    while cursor <= last:
        if cursor >= today and (weekday is None or cursor.weekday() == weekday):
            ret = cursor + timedelta(days=nights) if nights else None
            try:
                price, _, _ = quote_parts(TripQuery(
                    origin=origin,
                    destination=dest,
                    depart=cursor,
                    ret=ret,
                    cabin=cabin,
                    trip_type="oneway" if ret is None else "round",
                ))
            except ValueError:
                cursor += timedelta(days=1)
                continue
            if best is None or price < best[0]:
                best = (price, cursor, ret)
        cursor += timedelta(days=1)
    return best


def _sentence(origin, destination, depart, ret, cabin, passengers, reason, max_price) -> str:
    depart_label = depart.strftime("%a, %b ") + str(depart.day)
    if ret:
        ret_label = ret.strftime("%a, %b ") + str(ret.day)
        trip = f"Round trip from {origin['city']} to {destination['city']}, departing {depart_label} and returning {ret_label}"
    else:
        trip = f"One way from {origin['city']} to {destination['city']}, departing {depart_label}"
    if reason:
        trip += f". I used {reason}"
    if cabin != "economy":
        trip += f", in {cabin}"
    if passengers > 1:
        trip += f", for {passengers} passengers"
    if max_price:
        trip += f". Fares at or below ${max_price:,} are highlighted"
    return trip + "."
