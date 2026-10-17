"""Approval lifecycle, overlap control, and the audit trail — SPEC §3.5."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient


def _iso(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def _submit(client, headers, body) -> dict:
    r = client.post("/api/v1/rentals", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def test_full_lifecycle_pending_to_completed(client, auth, rental_payload) -> None:
    customer = auth["register_customer"]()
    staff = auth["login_staff"]()
    rental = _submit(client, customer["headers"], rental_payload())
    rid = rental["id"]

    assert rental["status"] == "pending"

    approved = client.post(f"/api/v1/rentals/{rid}/approve", headers=staff["headers"])
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    active = client.post(f"/api/v1/rentals/{rid}/activate", headers=staff["headers"])
    assert active.json()["status"] == "active"

    done = client.post(f"/api/v1/rentals/{rid}/complete", headers=staff["headers"])
    assert done.json()["status"] == "completed"


def test_audit_trail_records_every_decision(client, auth, rental_payload) -> None:
    customer = auth["register_customer"]()
    staff = auth["login_staff"]()
    rid = _submit(client, customer["headers"], rental_payload())["id"]

    client.post(f"/api/v1/rentals/{rid}/approve", headers=staff["headers"])
    client.post(f"/api/v1/rentals/{rid}/activate", headers=staff["headers"])

    detail = client.get(f"/api/v1/rentals/{rid}", headers=staff["headers"]).json()
    actions = [e["action"] for e in detail["audit_events"]]
    assert actions == ["submitted", "approved", "activated"]
    assert all(e["from_status"] for e in detail["audit_events"])


def test_rejection_stores_reason_and_is_visible_to_customer(client, auth, rental_payload) -> None:
    customer = auth["register_customer"]()
    staff = auth["login_staff"]()
    rid = _submit(client, customer["headers"], rental_payload())["id"]

    rejected = client.post(
        f"/api/v1/rentals/{rid}/reject",
        json={"reason": "Licence photo is unreadable"},
        headers=staff["headers"],
    )
    assert rejected.status_code == 200
    assert rejected.json()["rejection_reason"] == "Licence photo is unreadable"

    mine = client.get(f"/api/v1/rentals/{rid}", headers=customer["headers"]).json()
    assert mine["rejection_reason"] == "Licence photo is unreadable"


def test_reject_requires_a_reason(client, auth, rental_payload) -> None:
    customer = auth["register_customer"]()
    staff = auth["login_staff"]()
    rid = _submit(client, customer["headers"], rental_payload())["id"]
    r = client.post(f"/api/v1/rentals/{rid}/reject", json={"reason": ""}, headers=staff["headers"])
    assert r.status_code == 422


def test_cannot_approve_a_non_pending_request(client, auth, rental_payload) -> None:
    customer = auth["register_customer"]()
    staff = auth["login_staff"]()
    rid = _submit(client, customer["headers"], rental_payload())["id"]

    assert (
        client.post(f"/api/v1/rentals/{rid}/approve", headers=staff["headers"]).status_code == 200
    )
    again = client.post(f"/api/v1/rentals/{rid}/approve", headers=staff["headers"])
    assert again.status_code == 422
    assert again.json()["detail"]["code"] == "INVALID_TRANSITION"


def test_cannot_activate_before_approval(client, auth, rental_payload) -> None:
    customer = auth["register_customer"]()
    staff = auth["login_staff"]()
    rid = _submit(client, customer["headers"], rental_payload())["id"]
    r = client.post(f"/api/v1/rentals/{rid}/activate", headers=staff["headers"])
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "INVALID_TRANSITION"


def test_customer_cannot_cancel_an_approved_rental(client, auth, rental_payload) -> None:
    customer = auth["register_customer"]()
    staff = auth["login_staff"]()
    rid = _submit(client, customer["headers"], rental_payload())["id"]
    client.post(f"/api/v1/rentals/{rid}/approve", headers=staff["headers"])

    r = client.post(f"/api/v1/rentals/{rid}/cancel", headers=customer["headers"])
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "CANNOT_CANCEL"


def test_customer_cannot_cancel_another_customers_rental(client, auth, rental_payload) -> None:
    owner = auth["register_customer"]("owner@example.com")
    other = auth["register_customer"]("other@example.com")
    rid = _submit(client, owner["headers"], rental_payload())["id"]

    r = client.post(f"/api/v1/rentals/{rid}/cancel", headers=other["headers"])
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "FORBIDDEN"


def test_customer_cannot_read_another_customers_rental(client, auth, rental_payload) -> None:
    owner = auth["register_customer"]("owner@example.com")
    other = auth["register_customer"]("other@example.com")
    rid = _submit(client, owner["headers"], rental_payload())["id"]

    assert client.get(f"/api/v1/rentals/{rid}", headers=other["headers"]).status_code == 403
    assert client.get(f"/api/v1/rentals/{rid}/proofs", headers=other["headers"]).status_code == 403


# ---------------------------------------------------------------------------
# Overlap control — approved rentals block the calendar
# ---------------------------------------------------------------------------
def test_two_customers_may_both_request_the_same_window_while_pending(
    client, auth, rental_payload, make_vehicle
) -> None:
    """Pending does not block the calendar; the decision is made at approval."""
    a = auth["register_customer"]("a@example.com")
    b = auth["register_customer"]("b@example.com")
    vehicle = str(make_vehicle().id)
    body = rental_payload(vehicle, start_date=_iso(20), end_date=_iso(24))

    assert client.post("/api/v1/rentals", json=body, headers=a["headers"]).status_code == 201
    assert client.post("/api/v1/rentals", json=body, headers=b["headers"]).status_code == 201


def test_second_approval_on_overlapping_window_is_blocked(
    client, auth, rental_payload, make_vehicle
) -> None:
    a = auth["register_customer"]("a@example.com")
    b = auth["register_customer"]("b@example.com")
    staff = auth["login_staff"]()
    vehicle = str(make_vehicle().id)
    body = rental_payload(vehicle, start_date=_iso(20), end_date=_iso(24))

    first = _submit(client, a["headers"], body)
    second = _submit(client, b["headers"], body)

    assert (
        client.post(f"/api/v1/rentals/{first['id']}/approve", headers=staff["headers"]).status_code
        == 200
    )
    blocked = client.post(f"/api/v1/rentals/{second['id']}/approve", headers=staff["headers"])
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "VEHICLE_UNAVAILABLE"


def test_adjacent_non_overlapping_windows_are_allowed(
    client, auth, rental_payload, make_vehicle
) -> None:
    """Half-open intervals: [20,24) and [24,28) do not overlap."""
    a = auth["register_customer"]("a@example.com")
    b = auth["register_customer"]("b@example.com")
    staff = auth["login_staff"]()
    vehicle = str(make_vehicle().id)

    first = _submit(
        client, a["headers"], rental_payload(vehicle, start_date=_iso(20), end_date=_iso(24))
    )
    second = _submit(
        client, b["headers"], rental_payload(vehicle, start_date=_iso(24), end_date=_iso(28))
    )

    assert (
        client.post(f"/api/v1/rentals/{first['id']}/approve", headers=staff["headers"]).status_code
        == 200
    )
    assert (
        client.post(f"/api/v1/rentals/{second['id']}/approve", headers=staff["headers"]).status_code
        == 200
    )


def test_completed_rental_frees_the_calendar(client, auth, rental_payload, make_vehicle) -> None:
    a = auth["register_customer"]("a@example.com")
    b = auth["register_customer"]("b@example.com")
    staff = auth["login_staff"]()
    vehicle = str(make_vehicle().id)
    body = rental_payload(vehicle, start_date=_iso(20), end_date=_iso(24))

    first = _submit(client, a["headers"], body)
    second = _submit(client, b["headers"], body)

    client.post(f"/api/v1/rentals/{first['id']}/approve", headers=staff["headers"])
    client.post(f"/api/v1/rentals/{first['id']}/activate", headers=staff["headers"])
    client.post(f"/api/v1/rentals/{first['id']}/complete", headers=staff["headers"])

    ok = client.post(f"/api/v1/rentals/{second['id']}/approve", headers=staff["headers"])
    assert ok.status_code == 200


# ---------------------------------------------------------------------------
# Approval queue
# ---------------------------------------------------------------------------
def test_pending_queue_returns_only_pending_requests(
    client, auth, rental_payload, make_vehicle
) -> None:
    a = auth["register_customer"]("a@example.com")
    staff = auth["login_staff"]()

    vehicle = make_vehicle()
    rental = _submit(
        client,
        a["headers"],
        rental_payload(str(vehicle.id), start_date=_iso(20), end_date=_iso(24)),
    )

    assert client.get("/api/v1/rentals").status_code == 401
    assert client.get("/api/v1/rentals", headers=a["headers"]).status_code == 403

    queue = client.get("/api/v1/rentals", headers=staff["headers"])
    assert queue.status_code == 200
    assert queue.json()["total"] == 1
    assert queue.json()["items"][0]["id"] == rental["id"]

    client.post(
        f"/api/v1/rentals/{rental['id']}/reject", json={"reason": "no"}, headers=staff["headers"]
    )
    assert client.get("/api/v1/rentals", headers=staff["headers"]).json()["total"] == 0


def test_pending_queue_is_ordered_by_requested_start_date(
    client, auth, rental_payload, make_vehicle
) -> None:
    # R1 caps each customer at one outstanding rental, so ordering is exercised
    # across two customers submitting in deliberately "wrong" order.
    a = auth["register_customer"]("a@example.com")
    b = auth["register_customer"]("b@example.com")
    staff = auth["login_staff"]()

    late_vehicle = make_vehicle()
    early_vehicle = make_vehicle()
    _submit(
        client,
        a["headers"],
        rental_payload(str(late_vehicle.id), start_date=_iso(40), end_date=_iso(44)),
    )
    _submit(
        client,
        b["headers"],
        rental_payload(str(early_vehicle.id), start_date=_iso(20), end_date=_iso(24)),
    )

    items = client.get("/api/v1/rentals", headers=staff["headers"]).json()["items"]
    assert [i["vehicle_id"] for i in items] == [str(early_vehicle.id), str(late_vehicle.id)]


def test_staff_queue_can_reach_every_lifecycle_bucket(
    client, auth, rental_payload, make_vehicle
) -> None:
    """Regression guard.

    The queue used to return only `pending`. Once a request was approved it left
    the queue, so staff could never see it again to activate or complete it, and
    the customer stayed blocked by R1 forever. Every bucket must be listable.
    """
    customer = auth["register_customer"]()
    staff = auth["login_staff"]()
    vehicle = make_vehicle()
    rid = _submit(
        client,
        customer["headers"],
        rental_payload(str(vehicle.id), start_date=_iso(20), end_date=_iso(24)),
    )["id"]

    def count(status: str) -> int:
        r = client.get("/api/v1/rentals", params={"status": status}, headers=staff["headers"])
        assert r.status_code == 200
        return r.json()["total"]

    assert count("pending") == 1
    assert count("approved") == 0

    client.post(f"/api/v1/rentals/{rid}/approve", headers=staff["headers"])
    assert count("pending") == 0
    assert count("approved") == 1

    client.post(f"/api/v1/rentals/{rid}/activate", headers=staff["headers"])
    assert count("approved") == 0
    assert count("active") == 1

    client.post(f"/api/v1/rentals/{rid}/complete", headers=staff["headers"])
    assert count("active") == 0
    assert count("completed") == 1


def test_staff_queue_rejects_unknown_status(client: TestClient, auth) -> None:
    staff = auth["login_staff"]()
    r = client.get("/api/v1/rentals", params={"status": "teleported"}, headers=staff["headers"])
    assert r.status_code == 422


def test_queue_defaults_to_pending(client, auth, rental_payload, make_vehicle) -> None:
    customer = auth["register_customer"]()
    staff = auth["login_staff"]()
    vehicle = make_vehicle()
    _submit(
        client,
        customer["headers"],
        rental_payload(str(vehicle.id), start_date=_iso(20), end_date=_iso(24)),
    )
    assert client.get("/api/v1/rentals", headers=staff["headers"]).json()["total"] == 1


def test_staff_can_cancel_an_approved_rental(client, auth, rental_payload, make_vehicle) -> None:
    """A committed booking must be releasable when the customer drops out."""
    customer = auth["register_customer"]()
    staff = auth["login_staff"]()
    vehicle = make_vehicle()
    rid = _submit(
        client,
        customer["headers"],
        rental_payload(str(vehicle.id), start_date=_iso(20), end_date=_iso(24)),
    )["id"]
    client.post(f"/api/v1/rentals/{rid}/approve", headers=staff["headers"])

    cancelled = client.post(
        f"/api/v1/rentals/{rid}/cancel",
        json={"reason": "Customer withdrew"},
        headers=staff["headers"],
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    # The customer is released by R1 and the vehicle's calendar is free again.
    again = client.post(
        "/api/v1/rentals",
        json=rental_payload(str(vehicle.id), start_date=_iso(20), end_date=_iso(24)),
        headers=customer["headers"],
    )
    assert again.status_code == 201


def test_staff_can_cancel_an_active_rental(client, auth, rental_payload, make_vehicle) -> None:
    customer = auth["register_customer"]()
    staff = auth["login_staff"]()
    vehicle = make_vehicle()
    rid = _submit(
        client,
        customer["headers"],
        rental_payload(str(vehicle.id), start_date=_iso(20), end_date=_iso(24)),
    )["id"]
    client.post(f"/api/v1/rentals/{rid}/approve", headers=staff["headers"])
    client.post(f"/api/v1/rentals/{rid}/activate", headers=staff["headers"])

    r = client.post(f"/api/v1/rentals/{rid}/cancel", headers=staff["headers"])
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"


def test_staff_cannot_cancel_a_completed_rental(client, auth, rental_payload, make_vehicle) -> None:
    """Terminal states stay immutable."""
    customer = auth["register_customer"]()
    staff = auth["login_staff"]()
    vehicle = make_vehicle()
    rid = _submit(
        client,
        customer["headers"],
        rental_payload(str(vehicle.id), start_date=_iso(20), end_date=_iso(24)),
    )["id"]
    for action in ("approve", "activate", "complete"):
        client.post(f"/api/v1/rentals/{rid}/{action}", headers=staff["headers"])

    r = client.post(f"/api/v1/rentals/{rid}/cancel", headers=staff["headers"])
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "INVALID_TRANSITION"


def test_staff_cancellation_is_audited(client, auth, rental_payload, make_vehicle) -> None:
    customer = auth["register_customer"]()
    staff = auth["login_staff"]()
    vehicle = make_vehicle()
    rid = _submit(
        client,
        customer["headers"],
        rental_payload(str(vehicle.id), start_date=_iso(20), end_date=_iso(24)),
    )["id"]
    client.post(
        f"/api/v1/rentals/{rid}/cancel", json={"reason": "duplicate"}, headers=staff["headers"]
    )

    events = client.get(f"/api/v1/rentals/{rid}", headers=staff["headers"]).json()["audit_events"]
    last = events[-1]
    assert last["action"] == "cancelled"
    assert last["from_status"] == "pending"
    assert last["to_status"] == "cancelled"
    assert last["reason"] == "duplicate"


def test_proof_urls_are_presigned_and_scoped(client, auth, rental_payload) -> None:
    customer = auth["register_customer"]()
    staff = auth["login_staff"]()
    rid = _submit(client, customer["headers"], rental_payload())["id"]

    for viewer in (customer, staff):
        r = client.get(f"/api/v1/rentals/{rid}/proofs", headers=viewer["headers"])
        assert r.status_code == 200
        urls = r.json()
        assert {u["kind"] for u in urls} == {"aadhaar", "licence"}
        assert all("sig=get" in u["url"] for u in urls)


def test_upload_url_endpoint_mints_put_and_returns_key(client, auth) -> None:
    import uuid

    customer = auth["register_customer"]()
    draft_id = str(uuid.uuid4())
    r = client.post(
        "/api/v1/rentals/upload-url",
        json={
            "kind": "aadhaar",
            "filename": "aadhaar.jpg",
            "content_type": "image/jpeg",
            "size": 1024,
            "draft_id": draft_id,
        },
        headers=customer["headers"],
    )
    assert r.status_code == 200
    body = r.json()
    assert body["object_key"].startswith(f"rentals/{draft_id}/aadhaar")
    assert "sig=put" in body["upload_url"]
    assert body["expires_in_seconds"] <= 900


def test_upload_url_rejects_oversized_file(client, auth) -> None:
    import uuid

    customer = auth["register_customer"]()
    r = client.post(
        "/api/v1/rentals/upload-url",
        json={
            "kind": "aadhaar",
            "filename": "aadhaar.jpg",
            "content_type": "image/jpeg",
            "size": 10 * 1024 * 1024,
            "draft_id": str(uuid.uuid4()),
        },
        headers=customer["headers"],
    )
    assert r.status_code == 422
