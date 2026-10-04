"""Idempotent demo data for local development (SPEC §4).

Run with `make seed` or `uv run seed`. Safe to run repeatedly: it no-ops once any
user exists.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.user import Role, User
from app.models.vehicle import Vehicle, VehicleStatus, VehicleType
from app.services.auth import hash_password

DEMO_CUSTOMER = ("customer@demo.com", "Customer123")
DEMO_STAFF = ("staff@demo.com", "Staff123")

_VEHICLES = [
    ("car", "Maruti", "Swift", 2023, "MH-12-AB-1234", 5, "1500.00", VehicleStatus.available),
    ("suv", "Hyundai", "Creta", 2024, "MH-12-CD-5678", 7, "2500.00", VehicleStatus.available),
    (
        "bike",
        "Royal Enfield",
        "Classic 350",
        2023,
        "MH-12-EF-9012",
        2,
        "800.00",
        VehicleStatus.available,
    ),
    ("van", "Tata", "Nexon EV", 2024, "MH-12-GH-3456", 5, "2000.00", VehicleStatus.available),
    ("truck", "Tata", "Ace", 2022, "MH-12-IJ-7890", 2, "3000.00", VehicleStatus.maintenance),
]


def seed(db: Session) -> bool:
    """Insert demo users and vehicles. Returns False if already seeded."""
    if db.query(User).count() > 0:
        return False

    db.add_all(
        [
            User(
                id=uuid.uuid4(),
                name="Rahul Sharma",
                email=DEMO_CUSTOMER[0],
                password_hash=hash_password(DEMO_CUSTOMER[1]),
                role=Role.customer,
            ),
            User(
                id=uuid.uuid4(),
                name="Priya Verma",
                email=DEMO_STAFF[0],
                password_hash=hash_password(DEMO_STAFF[1]),
                role=Role.staff,
            ),
        ]
    )
    db.add_all(
        Vehicle(
            id=uuid.uuid4(),
            type=VehicleType(kind),
            make=make,
            model=model,
            year=year,
            registration_no=reg,
            seats=seats,
            price_per_day=Decimal(price),
            status=st,
        )
        for kind, make, model, year, reg, seats, price, st in _VEHICLES
    )
    db.commit()
    return True


def main() -> None:
    """Insert demo data.

    Deliberately does NOT create tables: Alembic is the sole mechanism for DDL
    (SPEC §6.1). Run `alembic upgrade head` first — the container CMD does exactly
    that. This script only inserts rows.
    """
    with SessionLocal() as db:
        created = seed(db)
    if created:
        print("Seeded demo data.")
        print(f"  customer: {DEMO_CUSTOMER[0]} / {DEMO_CUSTOMER[1]}")
        print(f"  staff:    {DEMO_STAFF[0]} / {DEMO_STAFF[1]}")
    else:
        print("Demo data already present; nothing to do.")


if __name__ == "__main__":
    main()
