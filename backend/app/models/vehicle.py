import uuid
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import DateTime, Integer, Numeric, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class VehicleStatus(StrEnum):
    available = "available"
    maintenance = "maintenance"
    retired = "retired"


class VehicleType(StrEnum):
    car = "car"
    suv = "suv"
    van = "van"
    truck = "truck"
    bike = "bike"


class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    type: Mapped[VehicleType] = mapped_column(SAEnum(VehicleType, name="vehicle_type"))
    make: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(100))
    year: Mapped[int] = mapped_column(Integer)
    registration_no: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    seats: Mapped[int] = mapped_column(Integer)
    price_per_day: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    status: Mapped[VehicleStatus] = mapped_column(
        SAEnum(VehicleStatus, name="vehicle_status"), default=VehicleStatus.available
    )
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    rentals = relationship("RentalRequest", back_populates="vehicle")
