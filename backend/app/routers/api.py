import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.catalog import AIRLINES, get_place
from app.services.airports import search_airports
from app import database as database_module
from app.database import get_db
from app.models import Alert, PriceQuote
from app.schemas import AlertCreate, SearchRequest, SmartRequest
from app.services.deal import deal_score
from app.services.fare_band import paid_fare_band
from app.services.flights import TripQuery, calendar, deals, log_quote, outlook, quote_parts, sample_outbound, search
from app.services.smart import parse_smart

router = APIRouter(prefix="/api")
EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _apply_price(alert: Alert, price: int) -> None:
    alert.last_price = price
    alert.last_checked_at = _now()
    if price <= alert.target_price and alert.triggered_at is None:
        alert.triggered_at = _now()
        alert.triggered_reason = "price"


def _status(alert: Alert) -> str:
    if not alert.active:
        return "paused"
    if alert.last_price is not None and alert.last_price <= alert.target_price:
        return "hit"
    if alert.deal_watch and alert.deal_percentile is not None and alert.deal_percentile <= 25:
        return "deal"
    if alert.triggered_at is not None:
        return "rose"
    return "watching"


def _alert_query(alert: Alert) -> TripQuery:
    return TripQuery(
        origin=alert.origin,
        destination=alert.destination,
        depart=alert.depart_date,
        ret=alert.return_date,
        passengers=alert.passengers,
        cabin=alert.cabin,
        trip_type="oneway" if alert.return_date is None else "round",
    )


def _watch_deal(alert: Alert, airline: str, outbound: int) -> None:
    if not alert.deal_watch or not airline:
        return
    from app.services.deal import deal_score

    quarter = (alert.depart_date.month - 1) // 3 + 1
    try:
        score = deal_score(alert.origin, alert.destination, airline, quarter, outbound, "sample")
    except Exception:
        return
    alert.deal_label = score.get("label")
    percentile = score.get("percentile")
    alert.deal_percentile = None if percentile is None else int(round(percentile))
    good = score.get("available") and alert.deal_percentile is not None and alert.deal_percentile <= 25
    if good and alert.triggered_at is None:
        alert.triggered_at = _now()
        alert.triggered_reason = "deal"


def _refresh(alert: Alert) -> None:
    if alert.depart_date < datetime.now().date():
        return
    query = _alert_query(alert)
    price, airline, _stops = quote_parts(query, alert.airline_code, alert.stops)
    outbound, airline, _stops = sample_outbound(query, alert.airline_code, alert.stops)
    _apply_price(alert, price)
    _watch_deal(alert, airline, outbound)


def _public_alert(alert: Alert) -> dict:
    return {
        "id": alert.id,
        "origin": get_place(alert.origin),
        "destination": get_place(alert.destination),
        "depart_date": alert.depart_date.isoformat(),
        "return_date": alert.return_date.isoformat() if alert.return_date else None,
        "passengers": alert.passengers,
        "cabin": alert.cabin,
        "airline_code": alert.airline_code,
        "airline_name": AIRLINES[alert.airline_code]["name"] if alert.airline_code in AIRLINES else None,
        "stops": alert.stops,
        "target_price": alert.target_price,
        "deal_watch": bool(alert.deal_watch),
        "deal_label": alert.deal_label,
        "deal_percentile": alert.deal_percentile,
        "triggered_reason": alert.triggered_reason,
        "last_price": alert.last_price,
        "email": alert.email,
        "active": alert.active,
        "status": _status(alert),
        "created_at": alert.created_at.isoformat() if alert.created_at else None,
        "triggered_at": alert.triggered_at.isoformat() if alert.triggered_at else None,
        "last_checked_at": alert.last_checked_at.isoformat() if alert.last_checked_at else None,
    }


def _sync_alerts(db: Session, query: TripQuery, price: int) -> None:
    rows = (
        db.query(Alert)
        .filter_by(
            origin=query.origin,
            destination=query.destination,
            depart_date=query.depart,
            cabin=query.cabin,
            active=True,
        )
        .all()
    )
    for alert in rows:
        if (alert.return_date is None) != (query.ret is None):
            continue
        if query.ret and alert.return_date != query.ret:
            continue
        if alert.airline_code or alert.stops is not None:
            airline_price, airline, _stops = quote_parts(query, alert.airline_code, alert.stops)
            outbound, airline, _stops = sample_outbound(query, alert.airline_code, alert.stops)
            _apply_price(alert, airline_price)
        else:
            airline_price = price
            outbound, airline, _stops = sample_outbound(query)
            _apply_price(alert, airline_price)
        _watch_deal(alert, airline, outbound)


@router.get("/model/metrics")
def model_metrics():
    from pathlib import Path
    import json

    from app.services.phase2 import PHASE2_DIR, VERSION

    path = Path(PHASE2_DIR).parent / "phase2_metrics.json"
    if not path.exists():
        return {"available": False, "model_version": VERSION, "note": "Run python -m scripts.eval_phase2 to write holdout metrics."}
    data = json.loads(path.read_text(encoding="utf-8"))
    comparison = data.get("comparison") or {}
    return {
        "available": True,
        "model_version": data.get("version") or VERSION,
        "source": data.get("source"),
        "holdout": data.get("holdout"),
        "train_periods": data.get("train_periods"),
        "calibration_period": data.get("calibration_period"),
        "comparison": comparison,
        "formula_comparable": data.get("formula_comparable"),
        "by_volume_tier": data.get("by_volume_tier"),
        "limitations": [
            "DB1B has no booking date, so this is not a forecast of a purchase.",
            "Each row is a directional market. The file has no round-trip flag.",
            "The quarterly file is a 10 percent sample.",
            "The flight board is a simulation. On covered routes its base fare is the model median, then lead time, weekday, cabin, and a demand path are applied as assumptions.",
            "Book or wait is a heuristic on that sample path.",
            "A deal label compares a simulated or caller-supplied fare with real DOT tickets.",
        ],
    }


@router.get("/health")
def health(db: Session = Depends(get_db)):
    quotes = db.query(func.count(PriceQuote.id)).scalar() or 0
    alerts = db.query(func.count(Alert.id)).scalar() or 0
    return {
        "status": "ok",
        "database": database_module.database_backend,
        "quotes": quotes,
        "alerts": alerts,
        "provider": "sample",
    }


@router.get("/airports")
def airports(q: str = Query(default="")):
    return {"places": search_airports(q)}


@router.post("/search")
def search_flights(body: SearchRequest, db: Session = Depends(get_db)):
    result = search(body.model_dump())
    query = TripQuery(
        origin=body.origin,
        destination=body.destination,
        depart=body.depart_date,
        ret=None if body.trip_type == "oneway" else body.return_date,
        passengers=body.passengers,
        cabin=body.cabin,
        trip_type=body.trip_type,
    )
    price, airline, stops = quote_parts(query)
    log_quote(db, query, price, airline, stops)
    _sync_alerts(db, query, price)
    db.commit()
    return result


@router.get("/fare-band")
def fare_band(origin: str, destination: str):
    return paid_fare_band(origin, destination)


@router.get("/deal-score")
def score_deal(
    origin: str,
    destination: str,
    airline: str,
    quarter: int,
    fare: float,
    fare_kind: str = "sample",
):
    return deal_score(origin, destination, airline, quarter, fare, fare_kind)


@router.get("/outlook")
def route_outlook(
    origin: str,
    destination: str,
    depart_date: str,
    return_date: str | None = None,
    trip_type: str = "round",
    passengers: int = 1,
    cabin: str = "economy",
):
    return outlook({
        "origin": origin,
        "destination": destination,
        "depart_date": depart_date,
        "return_date": return_date,
        "trip_type": trip_type,
        "passengers": passengers,
        "cabin": cabin,
    })


@router.get("/calendar")
def route_calendar(
    origin: str,
    destination: str,
    month: str,
    nights: int = 7,
    cabin: str = "economy",
    trip_type: str = "round",
):
    return calendar(origin, destination, month, nights, cabin, trip_type)


@router.get("/deals")
def route_deals(origin: str = "NYC"):
    return deals(origin)


@router.post("/smart-search")
def smart_search(body: SmartRequest):
    return parse_smart(body.query, body.origin)


@router.get("/alerts")
def list_alerts(db: Session = Depends(get_db)):
    rows = db.query(Alert).order_by(Alert.created_at.desc()).all()
    for alert in rows:
        try:
            _refresh(alert)
        except ValueError:
            continue
    db.commit()
    return {"alerts": [_public_alert(alert) for alert in rows]}


@router.post("/alerts")
def create_alert(body: AlertCreate, db: Session = Depends(get_db)):
    email = (body.email or "").strip() or None
    if email and not EMAIL_RE.fullmatch(email):
        raise ValueError("Enter a valid email or leave it blank.")
    query = TripQuery(
        origin=body.origin,
        destination=body.destination,
        depart=body.depart_date,
        ret=body.return_date,
        passengers=body.passengers,
        cabin=body.cabin,
        trip_type="oneway" if body.return_date is None else "round",
    )
    airline_code = (body.airline_code or "").strip().upper() or None
    price, airline, _stops = quote_parts(query, airline_code, body.stops)
    outbound, airline, _stops = sample_outbound(query, airline_code, body.stops)
    alert = Alert(
        origin=query.origin,
        destination=query.destination,
        depart_date=query.depart,
        return_date=query.ret,
        passengers=query.passengers,
        cabin=query.cabin,
        airline_code=airline_code,
        stops=body.stops,
        target_price=body.target_price,
        deal_watch=body.deal_watch,
        email=email,
        active=True,
        created_at=_now(),
    )
    _apply_price(alert, price)
    _watch_deal(alert, airline, outbound)
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return _public_alert(alert)


@router.delete("/alerts/{alert_id}")
def delete_alert(alert_id: int, db: Session = Depends(get_db)):
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise ValueError("That alert is no longer here.")
    db.delete(alert)
    db.commit()
    return {"ok": True}
