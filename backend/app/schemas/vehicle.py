from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

VEHICLE_TYPES = ("car", "suv", "van", "truck", "bike")
VEHICLE_STATUSES = ("available", "maintenance", "retired")


class VehicleCreate(BaseModel):
    model_config = {"extra": "forbid"}

    type: str = Field(..., pattern=f"^({'|'.join(VEHICLE_TYPES)})$")
    make: str = Field(..., min_length=1, max_length=100)
    model: str = Field(..., min_length=1, max_length=100)
    year: int = Field(..., ge=1900, le=2100)
    registration_no: str = Field(..., min_length=3, max_length=50)
    seats: int = Field(..., ge=1, le=50)
    price_per_day: Decimal = Field(..., gt=0, le=10000, decimal_places=2)
    image_url: str | None = Field(None, max_length=500)


class VehicleUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    type: str | None = Field(None, pattern=f"^({'|'.join(VEHICLE_TYPES)})$")
    make: str | None = Field(None, min_length=1, max_length=100)
    model: str | None = Field(None, min_length=1, max_length=100)
    year: int | None = Field(None, ge=1900, le=2100)
    registration_no: str | None = Field(None, min_length=3, max_length=50)
    seats: int | None = Field(None, ge=1, le=50)
    price_per_day: Decimal | None = Field(None, gt=0, le=10000, decimal_places=2)
    image_url: str | None = Field(None, max_length=500)


class VehicleStatusUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    status: str = Field(..., pattern=f"^({'|'.join(VEHICLE_STATUSES)})$")


class VehicleOut(BaseModel):
    id: uuid.UUID
    type: str
    make: str
    model: str
    year: int
    registration_no: str
    seats: int
    price_per_day: Decimal
    status: str
    image_url: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
