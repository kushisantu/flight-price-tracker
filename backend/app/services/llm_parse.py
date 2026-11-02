"""Provider-agnostic trip parser.

The client speaks the OpenAI chat-completions JSON shape. The key, base URL,
and model name come from the environment. Any missing key, network error, or
invalid payload returns None so the rule parser can take over.
"""

from __future__ import annotations

import json
from datetime import date
from urllib import error, request

from pydantic import ValidationError

from app.catalog import PLACE_ALIASES, get_place
from app.config import settings
from app.schemas import ParsedTrip

SYSTEM = (
    "Extract a flight search as JSON with keys origin, destination, depart_date, "
    "return_date, trip_type, passengers, cabin, max_price. "
    "origin and destination are city or airport codes such as NYC, CHI, LAX, LON. "
    "depart_date and return_date are YYYY-MM-DD or null. "
    "trip_type is round or oneway. cabin is economy, premium, business, or first. "
    "passengers is an integer. max_price is an integer or null. "
    "Use null when a field is not stated. Do not invent a city that was not named."
)


def interpret(text: str, today: date) -> dict | None:
    parsed = _fetch(text)
    if parsed is None:
        return None
    origin = _resolve(parsed.origin)
    destination = _resolve(parsed.destination)
    if origin is None or destination is None or origin["code"] == destination["code"]:
        return None
    if parsed.depart_date < today:
        return None
    ret = None if parsed.trip_type == "oneway" else parsed.return_date
    if ret is not None and ret < parsed.depart_date:
        return None
    from app.services.smart import _sentence

    return {
        "parser": "llm",
        "interpretation": _sentence(
            origin, destination, parsed.depart_date, ret, parsed.cabin, parsed.passengers, "the requested dates", parsed.max_price,
        ),
        "max_price": parsed.max_price,
        "criteria": {
            "origin": origin,
            "destination": destination,
            "depart_date": parsed.depart_date.isoformat(),
            "return_date": ret.isoformat() if ret else None,
            "trip_type": "oneway" if ret is None else "round",
            "passengers": parsed.passengers,
            "cabin": parsed.cabin,
        },
    }


def _resolve(value: str) -> dict | None:
    text = " ".join((value or "").strip().lower().split())
    if not text:
        return None
    for phrase, code in PLACE_ALIASES:
        if text == phrase:
            try:
                return get_place(code)
            except ValueError:
                return None
    try:
        return get_place(text)
    except ValueError:
        return None


def _fetch(text: str) -> ParsedTrip | None:
    key = (settings.llm_api_key or "").strip()
    if not key:
        return None
    url = settings.llm_base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": settings.llm_model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": text},
        ],
        "response_format": {"type": "json_object"},
    }
    body = json.dumps(payload).encode()
    call = request.Request(
        url,
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(call, timeout=20) as response:
            raw = json.loads(response.read().decode())
        content = raw["choices"][0]["message"]["content"]
        data = json.loads(content)
        return ParsedTrip.model_validate(data)
    except (error.URLError, TimeoutError, KeyError, json.JSONDecodeError, ValidationError, TypeError, ValueError):
        return None
