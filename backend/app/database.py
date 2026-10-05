import logging
import re
import socket
from datetime import date, timedelta

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import SQLITE_PATH, settings

logger = logging.getLogger(__name__)

SEED_VERSION = "1"
SEED_ROUTES = [
    ("NYC", "LON", 36, 7),
    ("SFO", "TYO", 42, 10),
    ("LAX", "JFK", 21, 5),
    ("CHI", "MIA", 28, 4),
    ("BOS", "DUB", 45, 7),
    ("NYC", "PAR", 36, 7),
]


class Base(DeclarativeBase):
    pass


engine: Engine | None = None
SessionLocal = sessionmaker(autoflush=False, autocommit=False)
database_backend = "unknown"


def _sqlite_url() -> str:
    return "sqlite:///" + SQLITE_PATH.as_posix()


def _ensure_postgres_database(url: str) -> None:
    parsed = make_url(url)
    dbname = parsed.database or "flight_tracker"
    if not re.fullmatch(r"[A-Za-z0-9_]+", dbname):
        raise ValueError("Database name must be letters, numbers, or underscores.")

    import psycopg
    from psycopg import sql

    host = parsed.host or "127.0.0.1"
    if host == "localhost":
        host = "127.0.0.1"
    connection = psycopg.connect(
        host=host,
        port=parsed.port or 5432,
        user=parsed.username or "postgres",
        password=parsed.password or "",
        dbname="postgres",
        autocommit=True,
        connect_timeout=2,
    )
    try:
        row = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (dbname,),
        ).fetchone()
        if row is None:
            connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname)))
    finally:
        connection.close()


def _connect() -> tuple[Engine, str]:
    url = settings.database_url
    if url.startswith("sqlite"):
        connected = create_engine(url, connect_args={"check_same_thread": False})
        return connected, "sqlite"

    if url.startswith("postgresql"):
        try:
            parsed = make_url(url)
            host = parsed.host or "127.0.0.1"
            if host == "localhost":
                host = "127.0.0.1"
            with socket.create_connection((host, parsed.port or 5432), timeout=0.4):
                pass
            _ensure_postgres_database(url)
            connected = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 2})
            with connected.connect() as connection:
                connection.execute(text("SELECT 1"))
            return connected, "postgresql"
        except Exception as exc:
            if not settings.allow_sqlite_fallback:
                raise
            logger.warning(
                "PostgreSQL is unavailable (%s). Using SQLite at %s",
                exc,
                SQLITE_PATH,
            )

    connected = create_engine(_sqlite_url(), connect_args={"check_same_thread": False})
    return connected, "sqlite"


def _seed_history() -> None:
    from app.models import Meta, PriceQuote
    from app.services.flights import TripQuery, quote_parts

    db = SessionLocal()
    try:
        meta = db.get(Meta, "seed_version")
        if meta and meta.value == SEED_VERSION:
            return

        db.query(PriceQuote).delete()
        today = date.today()
        rows: list[PriceQuote] = []
        for origin, destination, ahead, nights in SEED_ROUTES:
            depart = today + timedelta(days=ahead)
            ret = depart + timedelta(days=nights)
            for back in range(45):
                observed = today - timedelta(days=back)
                query = TripQuery(
                    origin=origin,
                    destination=destination,
                    depart=depart,
                    ret=ret,
                    observed=observed,
                )
                price, airline, stops = quote_parts(query)
                rows.append(
                    PriceQuote(
                        origin=origin,
                        destination=destination,
                        depart_date=depart,
                        return_date=ret,
                        return_key=ret.isoformat(),
                        cabin="economy",
                        observed_on=observed,
                        price=price,
                        airline_code=airline,
                        stops=stops,
                    )
                )
        db.add_all(rows)
        if meta:
            meta.value = SEED_VERSION
        else:
            db.add(Meta(key="seed_version", value=SEED_VERSION))
        db.commit()
        logger.info("Stored %s sample price quotes", len(rows))
    except Exception:
        db.rollback()
        logger.exception("Could not seed price history")
    finally:
        db.close()


def _ensure_alert_columns() -> None:
    with engine.begin() as connection:
        if database_backend == "sqlite":
            rows = connection.execute(text("PRAGMA table_info(alerts)")).fetchall()
            names = {row[1] for row in rows}
            if "airline_code" not in names:
                connection.execute(text("ALTER TABLE alerts ADD COLUMN airline_code VARCHAR(4)"))
            if "stops" not in names:
                connection.execute(text("ALTER TABLE alerts ADD COLUMN stops INTEGER"))
        else:
            connection.execute(text("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS airline_code VARCHAR(4)"))
            connection.execute(text("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS stops INTEGER"))


def init_db() -> None:
    global engine, database_backend
    from app import models  # noqa: F401

    engine, database_backend = _connect()
    SessionLocal.configure(bind=engine)
    Base.metadata.create_all(engine)
    _ensure_alert_columns()
    _seed_history()
    logger.info("Database ready (%s)", database_backend)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
