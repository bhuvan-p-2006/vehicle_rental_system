"""Shared pytest fixtures.

The suite runs against the backend HTTP API (SPEC §10) using an in-process ASGI
client and a temporary SQLite database, so `make test` works on a bare checkout
without Docker, Postgres, or MinIO (SPEC §9, §13.4).

SQLite is sufficient here because the rules under test (R1–R5, RBAC, lifecycle)
are enforced by the service layer; the Postgres-only partial index is additionally
covered by the migration round-trip check.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

import pytest

# Must be set before app.config is imported anywhere.
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_session
from app.main import create_app
from app.models.user import Role, User
from app.models.vehicle import Vehicle, VehicleStatus, VehicleType
from app.services import storage as storage_module
from app.services.auth import hash_password

CUSTOMER_PW = "Customer123"
STAFF_PW = "Staff123"


@pytest.fixture()
def engine() -> Iterator[Any]:
    """In-memory SQLite shared across the connection (StaticPool)."""
    eng = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=eng)
    try:
        yield eng
    finally:
        Base.metadata.drop_all(bind=eng)
        eng.dispose()


@pytest.fixture()
def db(engine: Any) -> Iterator[Session]:
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    with factory() as session:
        yield session


@pytest.fixture()
def client(db: Session) -> Iterator[TestClient]:
    app = create_app()

    def override_session() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def stub_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace MinIO with an in-memory stand-in so tests never touch S3."""
    fake = storage_module.StorageService.__new__(storage_module.StorageService)
    fake.bucket = "test-bucket"
    fake.client = None  # type: ignore[assignment]
    monkeypatch.setattr(storage_module, "get_storage", lambda: fake)
    monkeypatch.setattr(storage_module.Minio, "__init__", lambda *a, **k: None)
    monkeypatch.setattr(storage_module.Minio, "bucket_exists", lambda *a, **k: True)
    monkeypatch.setattr(storage_module.Minio, "make_bucket", lambda *a, **k: None)
    monkeypatch.setattr(
        storage_module.Minio,
        "presigned_put_object",
        lambda self, bucket, key, **k: f"http://minio.test/{bucket}/{key}?sig=put",
    )
    monkeypatch.setattr(
        storage_module.Minio,
        "presigned_get_object",
        lambda self, bucket, key, **k: f"http://minio.test/{bucket}/{key}?sig=get",
    )


# ---------------------------------------------------------------------------
# Data factories
# ---------------------------------------------------------------------------
@pytest.fixture()
def make_user(db: Session):
    def _make(email: str, password: str, role: Role = Role.customer) -> User:
        user = User(
            name=email.split("@")[0].title(),
            email=email,
            password_hash=hash_password(password),
            role=role,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    return _make


@pytest.fixture()
def make_vehicle(db: Session):
    counter = {"n": 0}

    def _make(
        *,
        status: VehicleStatus = VehicleStatus.available,
        reg: str | None = None,
        price: str = "1000.00",
    ) -> Vehicle:
        counter["n"] += 1
        vehicle = Vehicle(
            type=VehicleType.car,
            make="Maruti",
            model=f"Swift-{counter['n']}",
            year=2024,
            registration_no=reg or f"TEST-{counter['n']:04d}",
            seats=5,
            price_per_day=price,
            status=status,
        )
        db.add(vehicle)
        db.commit()
        db.refresh(vehicle)
        return vehicle

    return _make


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
@pytest.fixture()
def auth(client: TestClient, make_user) -> dict[str, Any]:
    """Register a customer and a staff member; return auth helpers."""

    def register_customer(email: str = "c1@example.com", password: str = CUSTOMER_PW) -> dict:
        r = client.post(
            "/api/v1/auth/register", json={"name": "Cust", "email": email, "password": password}
        )
        assert r.status_code == 201, r.text
        token = client.post(
            "/api/v1/auth/login", json={"email": email, "password": password}
        ).json()["access_token"]
        return {
            "headers": {"Authorization": f"Bearer {token}"},
            "email": email,
            "password": password,
        }

    def login_staff(email: str = "staff@example.com", password: str = STAFF_PW) -> dict:
        make_user(email, password, Role.staff)
        token = client.post(
            "/api/v1/auth/login", json={"email": email, "password": password}
        ).json()["access_token"]
        return {"headers": {"Authorization": f"Bearer {token}"}, "email": email}

    return {"register_customer": register_customer, "login_staff": login_staff}


@pytest.fixture()
def rental_payload(make_vehicle):
    """Build a valid rental body (R2/R3/R4 satisfied)."""

    def _build(vehicle_id: str | None = None, **overrides: Any) -> dict:
        vehicle = vehicle_id or str(make_vehicle().id)
        start = date.today() + timedelta(days=15)
        body = {
            "vehicle_id": vehicle,
            "start_date": start.isoformat(),
            "end_date": (start + timedelta(days=3)).isoformat(),
            "contact_name": "Rahul Sharma",
            "contact_phone": "9876543210",
            "contact_email": "rahul@example.com",
            "proofs": [
                {
                    "kind": "aadhaar",
                    "object_key": "rentals/draft-1/aadhaar.jpg",
                    "content_type": "image/jpeg",
                    "size": 1024,
                },
                {
                    "kind": "licence",
                    "object_key": "rentals/draft-1/licence.jpg",
                    "content_type": "image/jpeg",
                    "size": 2048,
                },
            ],
        }
        body.update(overrides)
        return body

    return _build
