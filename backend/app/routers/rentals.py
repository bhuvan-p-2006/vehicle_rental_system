from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_session
from app.models.rental import RentalRequest, RentalStatus
from app.models.user import Role, User
from app.schemas.proof import UploadUrlRequest, UploadUrlResponse
from app.schemas.rental import (
    ProofUrl,
    RejectRequest,
    RentalCreate,
    RentalDetailOut,
    RentalListOut,
    RentalOut,
)
from app.services.rental import RentalRuleError, RentalService
from app.services.storage import PRESIGN_EXPIRY_SECONDS, StorageError, get_storage
from app.utils.deps import (
    ApiError,
    forbidden,
    not_found,
    require_any,
    require_customer,
    require_staff,
)

router = APIRouter(prefix="/rentals", tags=["rentals"])

SessionDep = Annotated[Session, Depends(get_session)]
CustomerDep = Annotated[User, Depends(require_customer)]
StaffDep = Annotated[User, Depends(require_staff)]
AnyUserDep = Annotated[User, Depends(require_any)]

# SPEC 3.3 — business-rule code -> HTTP status.
_RULE_STATUS: dict[str, int] = {
    "ACTIVE_RENTAL_EXISTS": status.HTTP_409_CONFLICT,
    "VEHICLE_UNAVAILABLE": status.HTTP_409_CONFLICT,
    "VEHICLE_NOT_FOUND": status.HTTP_404_NOT_FOUND,
    "NOT_FOUND": status.HTTP_404_NOT_FOUND,
    "FORBIDDEN": status.HTTP_403_FORBIDDEN,
}


def _raise_rule_error(exc: RentalRuleError) -> ApiError:
    if exc.code == "FORBIDDEN":
        return forbidden(exc.code, exc.message)
    return ApiError(
        _RULE_STATUS.get(exc.code, status.HTTP_422_UNPROCESSABLE_ENTITY), exc.code, exc.message
    )


# ---------------------------------------------------------------------------
# Proof upload (presigned direct-to-storage)
# ---------------------------------------------------------------------------
@router.post(
    "/upload-url",
    response_model=UploadUrlResponse,
    summary="Mint a presigned proof upload URL",
    description=(
        "Customer only. Returns a short-lived presigned PUT so the browser uploads "
        "directly to object storage, plus the `object_key` to echo back in POST /rentals."
    ),
)
def create_upload_url(payload: UploadUrlRequest, _: CustomerDep) -> UploadUrlResponse:
    storage = get_storage()
    object_key = storage.build_object_key(payload.draft_id, payload.kind, payload.filename)
    try:
        url = storage.presigned_put(object_key)
    except StorageError as exc:
        raise ApiError(status.HTTP_503_SERVICE_UNAVAILABLE, exc.code, exc.message) from exc
    return UploadUrlResponse(
        upload_url=url,
        object_key=object_key,
        expires_in_seconds=PRESIGN_EXPIRY_SECONDS,
    )


# ---------------------------------------------------------------------------
# Customer lifecycle
# ---------------------------------------------------------------------------
@router.post(
    "",
    response_model=RentalOut,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a rental request",
    description=(
        "Customer only. Enforces R1 (one outstanding rental), R2 (14-day advance "
        "booking), R3 (14-day max duration), R4 (both proofs supplied) and vehicle "
        "availability. Proof bytes must already be uploaded under the supplied keys."
    ),
)
def create_rental(payload: RentalCreate, db: SessionDep, customer: CustomerDep) -> RentalRequest:
    service = RentalService(db)
    try:
        return service.create(
            customer_id=customer.id,
            vehicle_id=payload.vehicle_id,
            start_date=payload.start_date,
            end_date=payload.end_date,
            contact_name=payload.contact_name,
            contact_phone=payload.contact_phone,
            contact_email=payload.contact_email,
            proof_specs=payload.proofs,
        )
    except RentalRuleError as exc:
        raise _raise_rule_error(exc) from exc


@router.get(
    "/me",
    response_model=RentalListOut,
    summary="List my rentals",
    description="Customer only — own requests, newest first, including history.",
)
def my_rentals(
    db: SessionDep,
    customer: CustomerDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> RentalListOut:
    items, total = RentalService(db).list_for_customer(customer.id, page=page, page_size=page_size)
    return RentalListOut(
        items=[RentalOut.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/pending",
    response_model=RentalListOut,
    summary="Approval queue",
    description="Staff only — pending requests ordered by requested start date.",
)
def pending_queue(
    db: SessionDep,
    _: StaffDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> RentalListOut:
    items, total = RentalService(db).list_by_status(
        RentalStatus.pending, page=page, page_size=page_size
    )
    return RentalListOut(
        items=[RentalOut.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/{rental_id}/cancel", response_model=RentalOut, summary="Cancel a pending request")
def cancel_rental(rental_id: uuid.UUID, db: SessionDep, customer: CustomerDep) -> RentalRequest:
    try:
        return RentalService(db).cancel_by_customer(rental_id, customer.id)
    except RentalRuleError as exc:
        raise _raise_rule_error(exc) from exc


# ---------------------------------------------------------------------------
# Shared reads
# ---------------------------------------------------------------------------
def _load_visible(db: Session, rental_id: uuid.UUID, viewer: User) -> RentalRequest:
    rental = RentalService(db).get(rental_id)
    if rental is None:
        raise not_found("RENTAL_NOT_FOUND", "Rental request not found.")
    if viewer.role is Role.customer and rental.customer_id != viewer.id:
        raise forbidden("NOT_YOUR_RENTAL", "You do not have access to this rental request.")
    return rental


@router.get(
    "/{rental_id}",
    response_model=RentalDetailOut,
    summary="Rental detail",
    description="Owner or staff. Includes vehicle, proof metadata and the audit trail.",
)
def get_rental(rental_id: uuid.UUID, db: SessionDep, viewer: AnyUserDep) -> RentalDetailOut:
    rental = _load_visible(db, rental_id, viewer)
    return RentalDetailOut.model_validate(rental)


@router.get(
    "/{rental_id}/proofs",
    response_model=list[ProofUrl],
    summary="Presigned proof download URLs",
    description=(
        "Owner or staff only. Issues short-lived presigned GET URLs; object keys "
        "are never exposed as static public paths (PII, SPEC 3.4)."
    ),
)
def get_proof_urls(rental_id: uuid.UUID, db: SessionDep, viewer: AnyUserDep) -> list[ProofUrl]:
    rental = _load_visible(db, rental_id, viewer)
    storage = get_storage()
    urls: list[ProofUrl] = []
    for proof in rental.proofs:
        try:
            urls.append(
                ProofUrl(kind=proof.kind.value, url=storage.presigned_get(proof.object_key))
            )
        except StorageError as exc:
            raise ApiError(status.HTTP_503_SERVICE_UNAVAILABLE, exc.code, exc.message) from exc
    return urls


# ---------------------------------------------------------------------------
# Staff decisions (SPEC 3.5)
# ---------------------------------------------------------------------------
def _detail(service: RentalService, rental: RentalRequest) -> RentalDetailOut:
    service.db.refresh(rental, attribute_names=["vehicle", "proofs", "audit_events"])
    return RentalDetailOut.model_validate(rental)


@router.post("/{rental_id}/approve", response_model=RentalDetailOut, summary="Approve a request")
def approve_rental(rental_id: uuid.UUID, db: SessionDep, staff: StaffDep) -> RentalDetailOut:
    service = RentalService(db)
    try:
        return _detail(service, service.approve(rental_id, staff.id))
    except RentalRuleError as exc:
        raise _raise_rule_error(exc) from exc


@router.post("/{rental_id}/reject", response_model=RentalDetailOut, summary="Reject a request")
def reject_rental(
    rental_id: uuid.UUID, payload: RejectRequest, db: SessionDep, staff: StaffDep
) -> RentalDetailOut:
    service = RentalService(db)
    try:
        return _detail(service, service.reject(rental_id, staff.id, payload.reason))
    except RentalRuleError as exc:
        raise _raise_rule_error(exc) from exc


@router.post("/{rental_id}/activate", response_model=RentalDetailOut, summary="Mark as active")
def activate_rental(rental_id: uuid.UUID, db: SessionDep, staff: StaffDep) -> RentalDetailOut:
    service = RentalService(db)
    try:
        return _detail(service, service.activate(rental_id, staff.id))
    except RentalRuleError as exc:
        raise _raise_rule_error(exc) from exc


@router.post("/{rental_id}/complete", response_model=RentalDetailOut, summary="Mark as completed")
def complete_rental(rental_id: uuid.UUID, db: SessionDep, staff: StaffDep) -> RentalDetailOut:
    service = RentalService(db)
    try:
        return _detail(service, service.complete(rental_id, staff.id))
    except RentalRuleError as exc:
        raise _raise_rule_error(exc) from exc
