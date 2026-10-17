"""RBAC matrix — SPEC §2.

Asserts the HTTP contract only: status codes and error codes, never internals.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.models.user import Role


def test_anonymous_can_browse_catalog(client: TestClient) -> None:
    assert client.get("/api/v1/vehicles").status_code == 200


def test_anonymous_cannot_create_rental(client: TestClient) -> None:
    r = client.post("/api/v1/rentals", json={})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] in {"MISSING_TOKEN", "VALIDATION_ERROR"}


def test_customer_cannot_approve_rentals(
    client: TestClient, auth, rental_payload, make_vehicle
) -> None:
    customer = auth["register_customer"]()
    created = client.post("/api/v1/rentals", json=rental_payload(), headers=customer["headers"])
    assert created.status_code == 201

    denied = client.post(
        f"/api/v1/rentals/{created.json()['id']}/approve", headers=customer["headers"]
    )
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "ROLE_REQUIRED"


def test_customer_cannot_create_vehicles(client: TestClient, auth) -> None:
    customer = auth["register_customer"]()
    r = client.post(
        "/api/v1/vehicles",
        json={
            "type": "car",
            "make": "Maruti",
            "model": "Swift",
            "year": 2024,
            "registration_no": "NEW-1",
            "seats": 5,
            "price_per_day": "1000.00",
        },
        headers=customer["headers"],
    )
    assert r.status_code == 403


def test_customer_cannot_see_approval_queue(client: TestClient, auth) -> None:
    customer = auth["register_customer"]()
    assert client.get("/api/v1/rentals", headers=customer["headers"]).status_code == 403


def test_staff_cannot_submit_rental_on_behalf_of_customer(
    client: TestClient, auth, rental_payload
) -> None:
    staff = auth["login_staff"]()
    r = client.post("/api/v1/rentals", json=rental_payload(), headers=staff["headers"])
    assert r.status_code == 403


def test_staff_can_manage_vehicles(client: TestClient, auth, make_vehicle) -> None:
    staff = auth["login_staff"]()
    vehicle = make_vehicle()
    r = client.patch(
        f"/api/v1/vehicles/{vehicle.id}/status",
        json={"status": "maintenance"},
        headers=staff["headers"],
    )
    assert r.status_code == 200
    assert r.json()["status"] == "maintenance"


def test_registration_never_grants_staff(client: TestClient) -> None:
    """R5: staff accounts are never self-service.

    Sending an explicit `role` is rejected outright (`extra="forbid"`), which is a
    stronger guarantee than silently ignoring the field.
    """
    escalation = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Sneaky",
            "email": "sneaky@example.com",
            "password": "Passw0rd!",
            "role": "staff",
        },
    )
    assert escalation.status_code == 422

    created = client.post(
        "/api/v1/auth/register",
        json={"name": "Normal", "email": "normal@example.com", "password": "Passw0rd!"},
    )
    assert created.status_code == 201
    assert created.json()["role"] == "customer"


def test_invalid_token_is_rejected(client: TestClient) -> None:
    r = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "INVALID_TOKEN"


def test_me_returns_role_for_staff(client: TestClient, auth, make_user) -> None:
    make_user("s2@example.com", "Staff123", Role.staff)
    token = client.post(
        "/api/v1/auth/login", json={"email": "s2@example.com", "password": "Staff123"}
    ).json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["role"] == "staff"
