from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PriceQuote(Base):
    __tablename__ = "price_quotes"
    __table_args__ = (
        UniqueConstraint(
            "origin",
            "destination",
            "depart_date",
            "return_key",
            "cabin",
            "observed_on",
            name="uq_price_quote",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    origin: Mapped[str] = mapped_column(String(8), index=True)
    destination: Mapped[str] = mapped_column(String(8), index=True)
    depart_date: Mapped[date] = mapped_column(Date, index=True)
    return_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    return_key: Mapped[str] = mapped_column(String(10), default="")
    cabin: Mapped[str] = mapped_column(String(16), default="economy")
    observed_on: Mapped[date] = mapped_column(Date, index=True)
    price: Mapped[int] = mapped_column(Integer)
    airline_code: Mapped[str | None] = mapped_column(String(4), nullable=True)
    stops: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    origin: Mapped[str] = mapped_column(String(8), index=True)
    destination: Mapped[str] = mapped_column(String(8), index=True)
    depart_date: Mapped[date] = mapped_column(Date)
    return_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    passengers: Mapped[int] = mapped_column(Integer, default=1)
    cabin: Mapped[str] = mapped_column(String(16), default="economy")
    airline_code: Mapped[str | None] = mapped_column(String(4), nullable=True)
    stops: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_price: Mapped[int] = mapped_column(Integer)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Meta(Base):
    __tablename__ = "meta"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(64))
