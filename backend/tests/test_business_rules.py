"""Business rules R1–R4 — SPEC §1.4.

Boundary cases are explicit: 13 vs 14 days advance, 14 vs 15 days duration.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.models.vehicle import VehicleStatus


def _iso(days_from_today: int) -> str:
    return (date.today() + timedelta(days=days_from_today)).isoformat()


# ---------------------------------------------------------------------------
# R2 — advance booking
# ---------------------------------------------------------------------------
def test_start_date_exactly_14_days_out_is_accepted(client, auth, rental_payload) -> None:
    customer = auth["register_customer"]()
    body = rental_payload(start_date=_iso(14), end_date=_iso(16))
    assert client.post("/api/v1/rentals", json=body, headers=customer["headers"]).status_code == 201


def test_start_date_13_days_out_is_rejected(client, auth, rental_payload) -> None:
    customer = auth["register_customer"]()
    body = rental_payload(start_date=_iso(13), end_date=_iso(16))
    r = client.post("/api/v1/rentals", json=body, headers=customer["headers"])
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# R3 — max duration
# ---------------------------------------------------------------------------
def test_duration_of_exactly_14_days_is_accepted(client, auth, rental_payload) -> None:
    customer = auth["register_customer"]()
    body = rental_payload(start_date=_iso(20), end_date=_iso(34))
    assert client.post("/api/v1/rentals", json=body, headers=customer["headers"]).status_code == 201


def test_duration_of_15_days_is_rejected(client, auth, rental_payload) -> None:
    customer = auth["register_customer"]()
    body = rental_payload(start_date=_iso(20), end_date=_iso(35))
    r = client.post("/api/v1/rentals", json=body, headers=customer["headers"])
    assert r.status_code == 422


def test_end_date_before_start_date_is_rejected(client, auth, rental_payload) -> None:
    customer = auth["register_customer"]()
    body = rental_payload(start_date=_iso(20), end_date=_iso(18))
    assert client.post("/api/v1/rentals", json=body, headers=customer["headers"]).status_code == 422


# ---------------------------------------------------------------------------
# R1 — one outstanding rental per customer
# ---------------------------------------------------------------------------
def test_second_pending_request_is_blocked(client, auth, rental_payload) -> None:
    customer = auth["register_customer"]()
    assert (
        client.post(
            "/api/v1/rentals", json=rental_payload(), headers=customer["headers"]
        ).status_code
        == 201
    )
    second = client.post("/api/v1/rentals", json=rental_payload(), headers=customer["headers"])
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "ACTIVE_RENTAL_EXISTS"


def test_request_allowed_after_cancellation(client, auth, rental_payload) -> None:
    customer = auth["register_customer"]()
    first = client.post("/api/v1/rentals", json=rental_payload(), headers=customer["headers"])
    assert first.status_code == 201

    cancelled = client.post(
        f"/api/v1/rentals/{first.json()['id']}/cancel", headers=customer["headers"]
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    assert (
        client.post(
            "/api/v1/rentals", json=rental_payload(), headers=customer["headers"]
        ).status_code
        == 201
    )


def test_request_allowed_after_rejection(client, auth, rental_payload) -> None:
    customer = auth["register_customer"]()
    staff = auth["login_staff"]()
    first = client.post("/api/v1/rentals", json=rental_payload(), headers=customer["headers"])

    rejected = client.post(
        f"/api/v1/rentals/{first.json()['id']}/reject",
        json={"reason": "Illegible licence"},
        headers=staff["headers"],
    )
    assert rejected.status_code == 200
    assert (
        client.post(
            "/api/v1/rentals", json=rental_payload(), headers=customer["headers"]
        ).status_code
        == 201
    )


def test_second_rejected_request_does_not_trip_r1(client, auth, rental_payload) -> None:
    """Regression guard for R1.

    The original schema used UNIQUE (customer_id, status), which would reject this
    scenario: both rows end up with status='rejected'. Only the partial index over
    outstanding statuses permits it.
    """
    customer = auth["register_customer"]("repeat@example.com")
    staff = auth["login_staff"]()

    first = client.post("/api/v1/rentals", json=rental_payload(), headers=customer["headers"])
    assert first.status_code == 201
    client.post(
        f"/api/v1/rentals/{first.json()['id']}/reject",
        json={"reason": "first rejection"},
        headers=staff["headers"],
    )

    second = client.post("/api/v1/rentals", json=rental_payload(), headers=customer["headers"])
    assert second.status_code == 201, second.text
    client.post(
        f"/api/v1/rentals/{second.json()['id']}/reject",
        json={"reason": "second rejection"},
        headers=staff["headers"],
    )

    rejected = [
        r
        for r in client.get("/api/v1/rentals/me", headers=customer["headers"]).json()["items"]
        if r["status"] == "rejected"
    ]
    assert len(rejected) == 2


# ---------------------------------------------------------------------------
# R4 — proofs
# ---------------------------------------------------------------------------
def test_request_without_proofs_is_rejected(client, auth, rental_payload) -> None:
    customer = auth["register_customer"]()
    body = rental_payload()
    del body["proofs"]
    r = client.post("/api/v1/rentals", json=body, headers=customer["headers"])
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_request_with_only_aadhaar_is_rejected(client, auth, rental_payload) -> None:
    customer = auth["register_customer"]()
    body = rental_payload()
    body["proofs"] = [p for p in body["proofs"] if p["kind"] == "aadhaar"]
    r = client.post("/api/v1/rentals", json=body, headers=customer["headers"])
    assert r.status_code == 422


def test_duplicate_proof_kinds_are_rejected(client, auth, rental_payload) -> None:
    customer = auth["register_customer"]()
    body = rental_payload()
    body["proofs"] = [body["proofs"][0], dict(body["proofs"][0])]
    r = client.post("/api/v1/rentals", json=body, headers=customer["headers"])
    assert r.status_code == 422


def test_proof_larger_than_cap_is_rejected(client, auth, rental_payload) -> None:
    customer = auth["register_customer"]()
    body = rental_payload()
    for proof in body["proofs"]:
        proof["size"] = 6 * 1024 * 1024
    r = client.post("/api/v1/rentals", json=body, headers=customer["headers"])
    assert r.status_code == 422


def test_disallowed_content_type_is_rejected(client, auth, rental_payload) -> None:
    customer = auth["register_customer"]()
    body = rental_payload()
    body["proofs"][0]["content_type"] = "application/zip"
    r = client.post("/api/v1/rentals", json=body, headers=customer["headers"])
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Vehicle availability
# ---------------------------------------------------------------------------
def test_non_available_vehicle_cannot_be_requested(
    client, auth, rental_payload, make_vehicle
) -> None:
    customer = auth["register_customer"]()
    vehicle = make_vehicle(status=VehicleStatus.maintenance)
    r = client.post(
        "/api/v1/rentals", json=rental_payload(str(vehicle.id)), headers=customer["headers"]
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "VEHICLE_UNAVAILABLE"


def test_unknown_vehicle_returns_404(client, auth, rental_payload) -> None:
    import uuid

    customer = auth["register_customer"]()
    r = client.post(
        "/api/v1/rentals", json=rental_payload(str(uuid.uuid4())), headers=customer["headers"]
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "VEHICLE_NOT_FOUND"
