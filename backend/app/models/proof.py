from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ProofKind(StrEnum):
    aadhaar = "aadhaar"
    licence = "licence"


class ProofDocument(Base):
    __tablename__ = "proof_documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rental_requests.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[ProofKind] = mapped_column(SAEnum(ProofKind, name="proof_kind"))
    object_key: Mapped[str] = mapped_column(String(500))
    content_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    request = relationship("RentalRequest", back_populates="proofs")

    __table_args__ = (
        # R4: exactly one artifact per kind per request.
        UniqueConstraint("request_id", "kind", name="uq_proof_one_per_kind_per_request"),
    )
