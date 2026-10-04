from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.rental import RentalRequest, RentalStatus
from app.models.vehicle import Vehicle, VehicleStatus
from app.schemas.vehicle import VehicleCreate, VehicleUpdate

# Statuses that make a vehicle un-bookable for new requests.
BOOKED_STATUSES = (RentalStatus.approved, RentalStatus.active)


class VehicleError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class VehicleService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    def list(
        self,
        *,
        type_filter: str | None = None,
        status_filter: str | None = None,
        search: str | None = None,
        available_from: date | None = None,
        available_to: date | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Vehicle], int]:
        stmt: Select[Vehicle] = select(Vehicle)
        if type_filter:
            stmt = stmt.where(Vehicle.type == type_filter)
        if status_filter:
            stmt = stmt.where(Vehicle.status == status_filter)
        if search:
            pattern = f"%{search}%"
            stmt = stmt.where(or_(Vehicle.make.ilike(pattern), Vehicle.model.ilike(pattern)))
        if available_from and available_to:
            # Only vehicles with no approved/active rental overlapping the window.
            overlapping = (
                select(RentalRequest.id)
                .where(
                    RentalRequest.vehicle_id == Vehicle.id,
                    RentalRequest.status.in_(BOOKED_STATUSES),
                    RentalRequest.start_date < available_to,
                    RentalRequest.end_date > available_from,
                )
                .exists()
            )
            stmt = stmt.where(Vehicle.status == VehicleStatus.available, ~overlapping)
        stmt = stmt.order_by(Vehicle.make.asc(), Vehicle.model.asc())

        total = self.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        rows = self.db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).scalars()
        return list(rows), total

    def get(self, vehicle_id: uuid.UUID) -> Vehicle | None:
        return self.db.get(Vehicle, vehicle_id)

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------
    def create(self, data: VehicleCreate) -> Vehicle:
        vehicle = Vehicle(**data.model_dump())
        self.db.add(vehicle)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise VehicleError(
                "REGISTRATION_TAKEN", "Registration number is already in the fleet."
            ) from exc
        self.db.refresh(vehicle)
        return vehicle

    def update(self, vehicle_id: uuid.UUID, data: VehicleUpdate) -> Vehicle:
        vehicle = self.get(vehicle_id)
        if vehicle is None:
            raise VehicleError("NOT_FOUND", "Vehicle not found.")
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(vehicle, field, value)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise VehicleError(
                "REGISTRATION_TAKEN", "Registration number is already in the fleet."
            ) from exc
        self.db.refresh(vehicle)
        return vehicle

    def set_status(self, vehicle_id: uuid.UUID, new_status: str) -> Vehicle:
        vehicle = self.get(vehicle_id)
        if vehicle is None:
            raise VehicleError("NOT_FOUND", "Vehicle not found.")
        vehicle.status = VehicleStatus(new_status)
        self.db.commit()
        self.db.refresh(vehicle)
        return vehicle
