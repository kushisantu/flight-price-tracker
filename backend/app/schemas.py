from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


Cabin = Literal["economy", "premium", "business", "first"]
TripType = Literal["round", "oneway"]


class SearchRequest(BaseModel):
    origin: str = Field(min_length=3, max_length=8)
    destination: str = Field(min_length=3, max_length=8)
    depart_date: date
    return_date: date | None = None
    trip_type: TripType = "round"
    passengers: int = Field(default=1, ge=1, le=6)
    cabin: Cabin = "economy"


class SmartRequest(BaseModel):
    query: str = Field(min_length=3, max_length=240)
    origin: str | None = None


class AlertCreate(BaseModel):
    origin: str = Field(min_length=3, max_length=8)
    destination: str = Field(min_length=3, max_length=8)
    depart_date: date
    return_date: date | None = None
    passengers: int = Field(default=1, ge=1, le=6)
    cabin: Cabin = "economy"
    airline_code: str | None = None
    stops: int | None = Field(default=None, ge=0, le=2)
    target_price: int = Field(ge=20, le=20000)
    email: str | None = None
