from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.audit import AuditAction, AuditEvent
from app.models.proof import ProofDocument
from app.models.rental import OUTSTANDING_STATUSES, RentalRequest, RentalStatus
from app.models.vehicle import Vehicle, VehicleStatus
from app.schemas.rental import ProofIn

# Statuses that occupy a customer's single rental slot (R1).
OUTSTANDING = tuple(RentalStatus(s) for s in OUTSTANDING_STATUSES)
# Statuses that occupy a vehicle's calendar.
BLOCKING = (RentalStatus.approved, RentalStatus.active)

_R1_INDEX = "uq_rentals_one_outstanding_per_customer"


class RentalRuleError(Exception):
    """A business rule from SPEC §1.4 was violated.

    Carries a machine-readable ``code`` so the HTTP layer can return the stable
    error envelope from SPEC §3.3 instead of leaking internals.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def windows_overlap(a_start: date, a_end: date, b_start: date, b_end: date) -> bool:
    """Half-open interval overlap on [start, end)."""
    return a_start < b_end and b_start < a_end


class RentalService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Rule checks
    # ------------------------------------------------------------------
    def assert_no_outstanding_rental(self, customer_id: uuid.UUID) -> None:
        """R1 — a customer may hold at most one pending/approved/active rental."""
        found = self.db.execute(
            select(RentalRequest.id).where(
                RentalRequest.customer_id == customer_id,
                RentalRequest.status.in_(OUTSTANDING),
            )
        ).first()
        if found is not None:
            raise RentalRuleError(
                "ACTIVE_RENTAL_EXISTS",
                "You already have a pending, approved, or active rental.",
            )

    def assert_vehicle_requestable(self, vehicle_id: uuid.UUID) -> None:
        vehicle = self.db.get(Vehicle, vehicle_id)
        if vehicle is None:
            raise RentalRuleError("VEHICLE_NOT_FOUND", "Vehicle does not exist.")
        if vehicle.status is not VehicleStatus.available:
            raise RentalRuleError("VEHICLE_UNAVAILABLE", "Vehicle is not open for booking.")

    def assert_window_free(
        self,
        vehicle_id: uuid.UUID,
        start: date,
        end: date,
        *,
        exclude_id: uuid.UUID | None = None,
    ) -> None:
        """No double-booking against approved/active rentals on the same vehicle."""
        stmt: Select[uuid.UUID] = select(RentalRequest.id).where(
            RentalRequest.vehicle_id == vehicle_id,
            RentalRequest.status.in_(BLOCKING),
            RentalRequest.start_date < end,
            RentalRequest.end_date > start,
        )
        if exclude_id is not None:
            stmt = stmt.where(RentalRequest.id != exclude_id)
        if self.db.execute(stmt.limit(1)).first() is not None:
            raise RentalRuleError(
                "VEHICLE_UNAVAILABLE",
                "Vehicle is already booked for part of that window.",
            )

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    def get(self, rental_id: uuid.UUID) -> RentalRequest | None:
        return self.db.get(RentalRequest, rental_id)

    def list_for_customer(
        self, customer_id: uuid.UUID, *, page: int = 1, page_size: int = 20
    ) -> tuple[list[RentalRequest], int]:
        stmt = (
            select(RentalRequest)
            .where(RentalRequest.customer_id == customer_id)
            .order_by(RentalRequest.created_at.desc())
        )
        return self._paginate(stmt, page, page_size)

    def list_by_status(
        self, status: RentalStatus, *, page: int = 1, page_size: int = 20
    ) -> tuple[list[RentalRequest], int]:
        stmt = (
            select(RentalRequest)
            .where(RentalRequest.status == status)
            .order_by(RentalRequest.start_date.asc(), RentalRequest.created_at.asc())
        )
        return self._paginate(stmt, page, page_size)

    def _paginate(
        self, stmt: Select[RentalRequest], page: int, page_size: int
    ) -> tuple[list[RentalRequest], int]:
        total = self.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        rows = self.db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).scalars()
        return list(rows), total

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------
    def create(
        self,
        *,
        customer_id: uuid.UUID,
        vehicle_id: uuid.UUID,
        start_date: date,
        end_date: date,
        contact_name: str,
        contact_phone: str,
        contact_email: str,
        proof_specs: list[ProofIn],
    ) -> RentalRequest:
        """Create a pending rental.

        R2/R3 (date windows) and R4 (proof completeness) are enforced by the
        Pydantic schema. This method owns R1, vehicle availability, and overlap.
        """
        self.assert_no_outstanding_rental(customer_id)
        self.assert_vehicle_requestable(vehicle_id)
        self.assert_window_free(vehicle_id, start_date, end_date)

        rental = RentalRequest(
            customer_id=customer_id,
            vehicle_id=vehicle_id,
            start_date=start_date,
            end_date=end_date,
            contact_name=contact_name,
            contact_phone=contact_phone,
            contact_email=contact_email,
            status=RentalStatus.pending,
        )
        self.db.add(rental)

        try:
            self.db.flush()
            for spec in proof_specs:
                self.db.add(
                    ProofDocument(
                        request_id=rental.id,
                        kind=spec.kind,
                        object_key=spec.object_key,
                        content_type=spec.content_type,
                        size=spec.size,
                    )
                )
            self.db.add(
                AuditEvent(
                    request_id=rental.id,
                    actor_id=customer_id,
                    action=AuditAction.submitted,
                    from_status="none",
                    to_status=RentalStatus.pending.value,
                )
            )
            self.db.commit()
        except IntegrityError as exc:
            # The partial unique index is the authoritative R1 guard; this branch
            # covers losing a race with a concurrent insert.
            self.db.rollback()
            if _R1_INDEX in str(exc.orig):
                raise RentalRuleError(
                    "ACTIVE_RENTAL_EXISTS",
                    "You already have a pending, approved, or active rental.",
                ) from exc
            raise

        self.db.refresh(rental)
        return rental

    def cancel_by_customer(self, rental_id: uuid.UUID, customer_id: uuid.UUID) -> RentalRequest:
        rental = self._owned(rental_id, customer_id)
        if rental.status is not RentalStatus.pending:
            raise RentalRuleError("CANNOT_CANCEL", "Only a pending request can be cancelled.")
        return self._transition(
            rental,
            to=RentalStatus.cancelled,
            actor_id=customer_id,
            action=AuditAction.cancelled,
        )

    def approve(self, rental_id: uuid.UUID, actor_id: uuid.UUID) -> RentalRequest:
        rental = self._require_status(rental_id, RentalStatus.pending)
        # Pending requests do not block the calendar, so two customers can queue
        # for the same window. Re-check here, when the booking actually takes hold.
        self.assert_window_free(
            rental.vehicle_id,
            rental.start_date,
            rental.end_date,
            exclude_id=rental.id,
        )
        return self._transition(
            rental,
            to=RentalStatus.approved,
            actor_id=actor_id,
            action=AuditAction.approved,
        )

    def reject(self, rental_id: uuid.UUID, actor_id: uuid.UUID, reason: str) -> RentalRequest:
        rental = self._require_status(rental_id, RentalStatus.pending)
        rental.rejection_reason = reason
        return self._transition(
            rental,
            to=RentalStatus.rejected,
            actor_id=actor_id,
            action=AuditAction.rejected,
            reason=reason,
        )

    def activate(self, rental_id: uuid.UUID, actor_id: uuid.UUID) -> RentalRequest:
        rental = self._require_status(rental_id, RentalStatus.approved)
        return self._transition(
            rental,
            to=RentalStatus.active,
            actor_id=actor_id,
            action=AuditAction.activated,
        )

    def complete(self, rental_id: uuid.UUID, actor_id: uuid.UUID) -> RentalRequest:
        rental = self._require_status(rental_id, RentalStatus.active)
        return self._transition(
            rental,
            to=RentalStatus.completed,
            actor_id=actor_id,
            action=AuditAction.completed,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _owned(self, rental_id: uuid.UUID, customer_id: uuid.UUID) -> RentalRequest:
        rental = self.get(rental_id)
        if rental is None:
            raise RentalRuleError("NOT_FOUND", "Rental request not found.")
        if rental.customer_id != customer_id:
            raise RentalRuleError("FORBIDDEN", "You do not own this rental request.")
        return rental

    def _require_status(self, rental_id: uuid.UUID, expected: RentalStatus) -> RentalRequest:
        rental = self.get(rental_id)
        if rental is None:
            raise RentalRuleError("NOT_FOUND", "Rental request not found.")
        if rental.status is not expected:
            raise RentalRuleError(
                "INVALID_TRANSITION",
                f"Cannot act on a request in state '{rental.status.value}'.",
            )
        return rental

    def _transition(
        self,
        rental: RentalRequest,
        *,
        to: RentalStatus,
        actor_id: uuid.UUID,
        action: AuditAction,
        reason: str | None = None,
    ) -> RentalRequest:
        previous = rental.status
        rental.status = to
        rental.audit_events.append(
            AuditEvent(
                request_id=rental.id,
                actor_id=actor_id,
                action=action,
                from_status=previous.value,
                to_status=to.value,
                reason=reason,
            )
        )
        self.db.commit()
        self.db.refresh(rental)
        return rental
