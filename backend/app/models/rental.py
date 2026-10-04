from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from enum import StrEnum

from sqlalchemy import Date, ForeignKey, Index, String, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql.elements import TextClause

from app.database import Base

# Statuses that occupy a customer's single rental slot (R1).
OUTSTANDING_STATUSES = ("pending", "approved", "active")


def _outstanding_predicate() -> TextClause:
    """`status IN (...)` SQL fragment for the partial-index WHERE clause."""
    values = ", ".join(f"'{s}'" for s in OUTSTANDING_STATUSES)
    return text(f"status IN ({values})")


class RentalStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    active = "active"
    completed = "completed"
    cancelled = "cancelled"


class RentalRequest(Base):
    __tablename__ = "rental_requests"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    status: Mapped[RentalStatus] = mapped_column(
        SAEnum(RentalStatus, name="rental_status"), default=RentalStatus.pending
    )
    contact_name: Mapped[str] = mapped_column(String(255))
    contact_phone: Mapped[str] = mapped_column(String(20))
    contact_email: Mapped[str] = mapped_column(String(255))
    rejection_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    customer = relationship("User", back_populates="rentals", foreign_keys=[customer_id])
    vehicle = relationship("Vehicle", back_populates="rentals")
    proofs = relationship("ProofDocument", back_populates="request", cascade="all, delete-orphan")
    audit_events = relationship(
        "AuditEvent", back_populates="request", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # R1: at most one outstanding rental per customer. A plain UNIQUE on
        # (customer_id, status) would be wrong -- it would forbid a customer from
        # ever holding two rejected/completed rows. A partial unique index scoped to
        # the outstanding statuses expresses the rule directly and still guards the
        # check-then-insert race at the database level.
        #
        # The predicate is registered for both dialects: SQLite (used by the test
        # suite) ignores `postgresql_where` and would otherwise create a *full*
        # unique index on customer_id alone.
        Index(
            "uq_rentals_one_outstanding_per_customer",
            "customer_id",
            unique=True,
            postgresql_where=_outstanding_predicate(),
            sqlite_where=_outstanding_predicate(),
        ),
        Index("ix_rentals_vehicle_window", "vehicle_id", "start_date", "end_date"),
        Index("ix_rentals_status", "status"),
    )
