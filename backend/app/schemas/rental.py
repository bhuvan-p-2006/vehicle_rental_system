from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, EmailStr, Field, field_serializer, model_validator

# Business-rule windows from SPEC 1.4 (single source of truth for Pydantic).
MIN_ADVANCE_DAYS = 14
MAX_DURATION_DAYS = 14

ProofKind = Literal["aadhaar", "licence"]


class ProofIn(BaseModel):
    """Proof metadata submitted alongside the rental request.

    The bytes already live in object storage under ``object_key`` (uploaded via a
    presigned PUT); the database only ever records the key plus metadata.
    """

    model_config = {"extra": "forbid"}

    kind: ProofKind
    object_key: str = Field(..., min_length=1, max_length=500)
    content_type: str = Field(
        ...,
        pattern=r"^(image/jpeg|image/png|image/webp|application/pdf)$",
    )
    size: int = Field(..., gt=0, le=5 * 1024 * 1024)


class RentalCreate(BaseModel):
    model_config = {"extra": "forbid"}

    vehicle_id: uuid.UUID
    start_date: date
    end_date: date
    contact_name: str = Field(..., min_length=1, max_length=255)
    contact_phone: str = Field(..., min_length=5, max_length=20)
    contact_email: EmailStr
    proofs: list[ProofIn] = Field(..., min_length=2, max_length=2)

    @model_validator(mode="after")
    def validate_dates(self) -> RentalCreate:
        today = date.today()
        min_start = today + timedelta(days=MIN_ADVANCE_DAYS)

        if self.start_date < min_start:
            raise ValueError(f"start_date must be at least {MIN_ADVANCE_DAYS} days from today")
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        duration = (self.end_date - self.start_date).days
        if duration > MAX_DURATION_DAYS:
            raise ValueError(f"rental duration cannot exceed {MAX_DURATION_DAYS} days")
        return self

    @model_validator(mode="after")
    def validate_proofs(self) -> RentalCreate:
        # R4: exactly one aadhaar and one licence.
        kinds = [p.kind for p in self.proofs]
        if sorted(kinds) != ["aadhaar", "licence"]:
            raise ValueError("exactly one aadhaar and one licence proof are required")
        keys = [p.object_key for p in self.proofs]
        if len(set(keys)) != len(keys):
            raise ValueError("proof object keys must be distinct")
        return self


class RejectRequest(BaseModel):
    model_config = {"extra": "forbid"}

    reason: str = Field(..., min_length=1, max_length=1000)


class StaffCancelRequest(BaseModel):
    """Optional reason recorded on a staff-initiated cancellation."""

    model_config = {"extra": "forbid"}

    reason: str | None = Field(default=None, max_length=1000)


class VehicleBrief(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    make: str
    model: str
    year: int
    registration_no: str
    price_per_day: Decimal

    @field_serializer("price_per_day")
    def _serialize_price(self, value: Decimal) -> float:
        """Match VehicleOut: money is a JSON number for the frontend."""
        return float(value)


class ProofOut(BaseModel):
    id: uuid.UUID
    kind: str
    content_type: str
    size: int

    model_config = {"from_attributes": True}


class AuditEventOut(BaseModel):
    action: str
    from_status: str
    to_status: str
    reason: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class RentalOut(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    vehicle_id: uuid.UUID
    start_date: date
    end_date: date
    status: str
    contact_name: str
    contact_phone: str
    contact_email: str
    rejection_reason: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RentalDetailOut(RentalOut):
    vehicle: VehicleBrief | None = None
    proofs: list[ProofOut] = Field(default_factory=list)
    audit_events: list[AuditEventOut] = Field(default_factory=list)


class Page(BaseModel):
    page: Annotated[int, Field(ge=1)] = 1
    page_size: Annotated[int, Field(ge=1, le=100)] = 20


class RentalListOut(BaseModel):
    items: list[RentalOut]
    total: int
    page: int
    page_size: int


class ProofUrl(BaseModel):
    kind: str
    url: str
