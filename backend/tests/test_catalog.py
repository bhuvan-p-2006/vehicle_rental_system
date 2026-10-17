"""Catalog reads, staff fleet management, and auth edge cases.

Fills the coverage gap left by the rule/lifecycle suites: the availability
window filter is a correlated EXISTS and is easy to get subtly wrong.
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.models.vehicle import VehicleStatus, VehicleType


def _iso(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


# ---------------------------------------------------------------------------
# Catalog reads (public, no auth)
# ---------------------------------------------------------------------------
def test_catalog_is_publicly_readable(client: TestClient, make_vehicle) -> None:
    make_vehicle()
    r = client.get("/api/v1/vehicles")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_filter_by_type(client: TestClient, db, make_vehicle) -> None:
    car = make_vehicle()
    suv = make_vehicle()
    suv.type = VehicleType.suv
    db.commit()
    db.refresh(suv)

    only_cars = client.get("/api/v1/vehicles", params={"type": "car"}).json()
    assert [v["id"] for v in only_cars] == [str(car.id)]

    only_suvs = client.get("/api/v1/vehicles", params={"type": "suv"}).json()
    assert [v["id"] for v in only_suvs] == [str(suv.id)]


def test_filter_by_status(client: TestClient, make_vehicle) -> None:
    make_vehicle(status=VehicleStatus.maintenance)
    make_vehicle(status=VehicleStatus.available)

    only_available = client.get("/api/v1/vehicles", params={"status": "available"}).json()
    assert len(only_available) == 1
    assert only_available[0]["status"] == "available"


def test_search_matches_make_or_model(client: TestClient, make_vehicle) -> None:
    make_vehicle()  # Maruti Swift-1
    make_vehicle()  # Maruti Swift-2
    make_vehicle()  # Maruti Swift-3

    by_make = client.get("/api/v1/vehicles", params={"search": "Maruti"}).json()
    assert len(by_make) == 3

    by_model = client.get("/api/v1/vehicles", params={"search": "Swift-2"}).json()
    assert len(by_model) == 1
    assert by_model[0]["model"] == "Swift-2"


def test_unknown_vehicle_returns_404(client: TestClient) -> None:
    import uuid

    r = client.get(f"/api/v1/vehicles/{uuid.uuid4()}")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "VEHICLE_NOT_FOUND"


def test_availability_window_excludes_booked_vehicles(
    client: TestClient, auth, make_vehicle
) -> None:
    """The window filter must drop vehicles with an overlapping approved rental."""
    customer = auth["register_customer"]()
    staff = auth["login_staff"]()
    booked = make_vehicle()
    free = make_vehicle()

    created = client.post(
        "/api/v1/rentals",
        json=_rental_body(booked.id, _iso(20), _iso(24)),
        headers=customer["headers"],
    )
    assert created.status_code == 201
    assert (
        client.post(
            f"/api/v1/rentals/{created.json()['id']}/approve", headers=staff["headers"]
        ).status_code
        == 200
    )

    result = client.get(
        "/api/v1/vehicles",
        params={"available_from": _iso(20), "available_to": _iso(24)},
    ).json()
    ids = [v["id"] for v in result]
    assert str(free.id) in ids
    assert str(booked.id) not in ids


def test_availability_window_allows_adjacent_booking(
    client: TestClient, auth, make_vehicle
) -> None:
    """A rental ending exactly when the window starts must not exclude the vehicle."""
    customer = auth["register_customer"]()
    staff = auth["login_staff"]()
    vehicle = make_vehicle()

    created = client.post(
        "/api/v1/rentals",
        json=_rental_body(vehicle.id, _iso(20), _iso(24)),
        headers=customer["headers"],
    )
    client.post(f"/api/v1/rentals/{created.json()['id']}/approve", headers=staff["headers"])

    result = client.get(
        "/api/v1/vehicles",
        params={"available_from": _iso(24), "available_to": _iso(28)},
    ).json()
    assert str(vehicle.id) in [v["id"] for v in result]


def test_availability_window_ignores_pending_rentals(
    client: TestClient, auth, make_vehicle
) -> None:
    """Pending does not block the calendar, so it must not hide the vehicle."""
    customer = auth["register_customer"]()
    vehicle = make_vehicle()

    created = client.post(
        "/api/v1/rentals",
        json=_rental_body(vehicle.id, _iso(20), _iso(24)),
        headers=customer["headers"],
    )
    assert created.status_code == 201

    result = client.get(
        "/api/v1/vehicles",
        params={"available_from": _iso(20), "available_to": _iso(24)},
    ).json()
    assert str(vehicle.id) in [v["id"] for v in result]


def test_pagination_bounds(client: TestClient, make_vehicle) -> None:
    for _ in range(3):
        make_vehicle()

    first = client.get("/api/v1/vehicles", params={"page": 1, "page_size": 2}).json()
    second = client.get("/api/v1/vehicles", params={"page": 2, "page_size": 2}).json()
    assert len(first) == 2
    assert len(second) == 1
    assert {v["id"] for v in first}.isdisjoint({v["id"] for v in second})


def test_invalid_pagination_is_rejected(client: TestClient) -> None:
    assert client.get("/api/v1/vehicles", params={"page": 0}).status_code == 422
    assert client.get("/api/v1/vehicles", params={"page_size": 0}).status_code == 422
    assert client.get("/api/v1/vehicles", params={"page_size": 101}).status_code == 422


# ---------------------------------------------------------------------------
# Staff fleet management
# ---------------------------------------------------------------------------
def _vehicle_payload(**overrides: object) -> dict:
    payload = {
        "type": "car",
        "make": "Maruti",
        "model": "Baleno",
        "year": 2024,
        "registration_no": "NEW-001",
        "seats": 5,
        "price_per_day": "1200.00",
    }
    payload.update(overrides)
    return payload


def test_staff_can_create_vehicle(client: TestClient, auth) -> None:
    staff = auth["login_staff"]()
    r = client.post("/api/v1/vehicles", json=_vehicle_payload(), headers=staff["headers"])
    assert r.status_code == 201
    assert r.json()["registration_no"] == "NEW-001"
    assert r.json()["status"] == "available"
    assert r.json()["price_per_day"] == 1200.0
    # Contract: money must arrive as a JSON number, not a string, so the
    # frontend's `number` type is truthful.
    assert isinstance(r.json()["price_per_day"], (int, float))


def test_duplicate_registration_number_is_rejected(client: TestClient, auth) -> None:
    staff = auth["login_staff"]()
    assert (
        client.post(
            "/api/v1/vehicles", json=_vehicle_payload(), headers=staff["headers"]
        ).status_code
        == 201
    )
    dupe = client.post("/api/v1/vehicles", json=_vehicle_payload(), headers=staff["headers"])
    assert dupe.status_code == 409
    assert dupe.json()["detail"]["code"] == "REGISTRATION_TAKEN"


def test_create_vehicle_rejects_invalid_payload(client: TestClient, auth) -> None:
    staff = auth["login_staff"]()
    assert (
        client.post(
            "/api/v1/vehicles", json=_vehicle_payload(seats=0), headers=staff["headers"]
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/vehicles", json=_vehicle_payload(year=1800), headers=staff["headers"]
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/vehicles", json=_vehicle_payload(type="spaceship"), headers=staff["headers"]
        ).status_code
        == 422
    )


def test_unknown_payload_field_is_rejected(client: TestClient, auth) -> None:
    staff = auth["login_staff"]()
    r = client.post(
        "/api/v1/vehicles",
        json=_vehicle_payload(unexpected="boom"),
        headers=staff["headers"],
    )
    assert r.status_code == 422


def test_staff_can_update_vehicle(client: TestClient, auth, make_vehicle) -> None:
    staff = auth["login_staff"]()
    vehicle = make_vehicle()
    r = client.put(
        f"/api/v1/vehicles/{vehicle.id}",
        json={"make": "Honda", "price_per_day": "990.50"},
        headers=staff["headers"],
    )
    assert r.status_code == 200
    assert r.json()["make"] == "Honda"
    assert r.json()["price_per_day"] == 990.50
    assert isinstance(r.json()["price_per_day"], (int, float))
    # Untouched fields survive a partial update.
    assert r.json()["model"] == vehicle.model


def test_update_missing_vehicle_returns_404(client: TestClient, auth) -> None:
    import uuid

    staff = auth["login_staff"]()
    r = client.put(
        f"/api/v1/vehicles/{uuid.uuid4()}", json={"make": "Honda"}, headers=staff["headers"]
    )
    assert r.status_code == 404


def test_invalid_status_value_is_rejected(client: TestClient, auth, make_vehicle) -> None:
    staff = auth["login_staff"]()
    vehicle = make_vehicle()
    r = client.patch(
        f"/api/v1/vehicles/{vehicle.id}/status",
        json={"status": "on_fire"},
        headers=staff["headers"],
    )
    assert r.status_code == 422


def test_retired_vehicle_cannot_be_requested(client: TestClient, auth, make_vehicle) -> None:
    customer = auth["register_customer"]()
    staff = auth["login_staff"]()
    vehicle = make_vehicle()

    assert (
        client.patch(
            f"/api/v1/vehicles/{vehicle.id}/status",
            json={"status": "retired"},
            headers=staff["headers"],
        ).status_code
        == 200
    )
    r = client.post(
        "/api/v1/rentals",
        json=_rental_body(vehicle.id, _iso(20), _iso(24)),
        headers=customer["headers"],
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "VEHICLE_UNAVAILABLE"


# ---------------------------------------------------------------------------
# Auth edge cases
# ---------------------------------------------------------------------------
def test_duplicate_registration_is_rejected(client: TestClient) -> None:
    body = {"name": "A", "email": "dup@example.com", "password": "Passw0rd!"}
    assert client.post("/api/v1/auth/register", json=body).status_code == 201
    dupe = client.post("/api/v1/auth/register", json=body)
    assert dupe.status_code == 409
    assert dupe.json()["detail"]["code"] == "EMAIL_TAKEN"


def test_weak_passwords_are_rejected(client: TestClient) -> None:
    base = {"name": "A", "email": "weak@example.com"}
    assert (
        client.post("/api/v1/auth/register", json={**base, "password": "short1A"}).status_code
        == 422
    )
    assert (
        client.post("/api/v1/auth/register", json={**base, "password": "alllowercase1"}).status_code
        == 422
    )
    assert (
        client.post("/api/v1/auth/register", json={**base, "password": "NoDigitsHere"}).status_code
        == 422
    )


def test_oversized_password_is_rejected(client: TestClient) -> None:
    """bcrypt ignores bytes past 72; the schema must reject rather than truncate."""
    r = client.post(
        "/api/v1/auth/register",
        json={"name": "A", "email": "big@example.com", "password": "A1" + "x" * 100},
    )
    assert r.status_code == 422


def test_login_with_wrong_password_is_unauthorized(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/register",
        json={"name": "A", "email": "a@example.com", "password": "Passw0rd!"},
    )
    r = client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "Wrong123!"})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "INVALID_CREDENTIALS"


def test_unknown_email_login_is_indistinguishable_from_wrong_password(
    client: TestClient,
) -> None:
    """Do not disclose whether an account exists."""
    client.post(
        "/api/v1/auth/register",
        json={"name": "A", "email": "known@example.com", "password": "Passw0rd!"},
    )
    unknown = client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "Passw0rd!"}
    )
    wrong = client.post(
        "/api/v1/auth/login", json={"email": "known@example.com", "password": "Wrong123!"}
    )
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"]["code"] == wrong.json()["detail"]["code"]


def test_email_lookup_is_case_insensitive(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/register",
        json={"name": "A", "email": "Mixed@Example.com", "password": "Passw0rd!"},
    )
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "mixed@example.com", "password": "Passw0rd!"},
    ).json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "mixed@example.com"


def test_health_endpoint_is_public(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_nested_vehicle_price_is_a_json_number(client: TestClient, auth, make_vehicle) -> None:
    """Rental detail embeds a vehicle summary; its price must obey the same rule."""
    customer = auth["register_customer"]()
    vehicle = make_vehicle(price="2500.00")
    created = client.post(
        "/api/v1/rentals",
        json=_rental_body(vehicle.id, _iso(20), _iso(24)),
        headers=customer["headers"],
    )
    assert created.status_code == 201

    detail = client.get(
        f"/api/v1/rentals/{created.json()['id']}", headers=customer["headers"]
    ).json()
    assert detail["vehicle"] is not None
    assert detail["vehicle"]["price_per_day"] == 2500.0
    assert isinstance(detail["vehicle"]["price_per_day"], (int, float))


# ---------------------------------------------------------------------------
# helper
# ---------------------------------------------------------------------------
def _rental_body(vehicle_id, start: str, end: str) -> dict:
    return {
        "vehicle_id": str(vehicle_id),
        "start_date": start,
        "end_date": end,
        "contact_name": "Rahul Sharma",
        "contact_phone": "9876543210",
        "contact_email": "rahul@example.com",
        "proofs": [
            {
                "kind": "aadhaar",
                "object_key": f"rentals/{vehicle_id}/aadhaar.jpg",
                "content_type": "image/jpeg",
                "size": 1024,
            },
            {
                "kind": "licence",
                "object_key": f"rentals/{vehicle_id}/licence.jpg",
                "content_type": "image/jpeg",
                "size": 2048,
            },
        ],
    }
