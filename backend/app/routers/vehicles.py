from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_session
from app.models.vehicle import Vehicle
from app.schemas.vehicle import VehicleCreate, VehicleOut, VehicleStatusUpdate, VehicleUpdate
from app.services.vehicle import VehicleError, VehicleService
from app.utils.deps import ApiError, not_found, require_staff

router = APIRouter(prefix="/vehicles", tags=["vehicles"])

SessionDep = Annotated[Session, Depends(get_session)]
StaffDep = Annotated[object, Depends(require_staff)]


@router.get("", response_model=list[VehicleOut])
def list_vehicles(
    db: SessionDep,
    type: str | None = Query(default=None, description="car|suv|van|truck|bike"),
    status_filter: str | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None, max_length=100),
    available_from: date | None = Query(default=None),
    available_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> list[Vehicle]:
    """Public catalog read. Pass `available_from`/`available_to` to filter to
    vehicles that are actually free for that window."""
    items, _ = VehicleService(db).list(
        type_filter=type,
        status_filter=status_filter,
        search=search,
        available_from=available_from,
        available_to=available_to,
        page=page,
        page_size=page_size,
    )
    return items


@router.get("/{vehicle_id}", response_model=VehicleOut)
def get_vehicle(vehicle_id: uuid.UUID, db: SessionDep) -> Vehicle:
    vehicle = VehicleService(db).get(vehicle_id)
    if vehicle is None:
        raise not_found("VEHICLE_NOT_FOUND", "Vehicle not found.")
    return vehicle


@router.post(
    "",
    response_model=VehicleOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a vehicle",
    description="Staff only — add a vehicle to the catalog.",
)
def create_vehicle(payload: VehicleCreate, db: SessionDep, _: StaffDep) -> Vehicle:
    try:
        return VehicleService(db).create(payload)
    except VehicleError as exc:
        raise ApiError(status.HTTP_409_CONFLICT, exc.code, exc.message) from exc


@router.put(
    "/{vehicle_id}",
    response_model=VehicleOut,
    summary="Update a vehicle",
    description="Staff only — update vehicle details.",
)
def update_vehicle(
    vehicle_id: uuid.UUID, payload: VehicleUpdate, db: SessionDep, _: StaffDep
) -> Vehicle:
    try:
        return VehicleService(db).update(vehicle_id, payload)
    except VehicleError as exc:
        status_code = (
            status.HTTP_404_NOT_FOUND if exc.code == "NOT_FOUND" else status.HTTP_409_CONFLICT
        )
        raise ApiError(status_code, exc.code, exc.message) from exc


@router.patch(
    "/{vehicle_id}/status",
    response_model=VehicleOut,
    summary="Set vehicle status",
    description="Staff only — move a vehicle between available/maintenance/retired.",
)
def set_vehicle_status(
    vehicle_id: uuid.UUID, payload: VehicleStatusUpdate, db: SessionDep, _: StaffDep
) -> Vehicle:
    try:
        return VehicleService(db).set_status(vehicle_id, payload.status)
    except VehicleError as exc:
        if exc.code == "NOT_FOUND":
            raise not_found(exc.code, exc.message) from exc
        raise ApiError(status.HTTP_409_CONFLICT, exc.code, exc.message) from exc
