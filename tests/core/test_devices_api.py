"""``/devices`` — pairing an edge device (RFC 8628 flow), device tokens, revoke."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session, sessionmaker

from core.devices.models import DevicePairing

ALICE = {"email": "alice@example.com", "name": "Alice", "password": "hunter2hunter"}
BOB = {"email": "bob@example.com", "name": "Bob", "password": "hunter2hunter"}


def _owner(client: TestClient, creds: dict[str, str]) -> dict[str, str]:
    """Register ``creds`` and return its Authorization header."""
    client.post("/auth/register", json=creds)
    token = client.post(
        "/auth/token", data={"username": creds["email"], "password": creds["password"]}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _start(client: TestClient, physical_id: str = "dev-1") -> dict:
    resp = client.post("/devices/pair", json={"physical_id": physical_id})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _poll(client: TestClient, device_code: str):  # type: ignore[no-untyped-def]
    return client.post("/devices/pair/token", json={"device_code": device_code})


def _pair(client: TestClient, owner: dict[str, str], physical_id: str = "dev-1") -> str:
    """Run the whole flow and return the device's bearer token."""
    started = _start(client, physical_id)
    approved = client.post(
        "/devices/pair/approve", json={"user_code": started["user_code"]}, headers=owner
    )
    assert approved.status_code == 200, approved.text
    return _poll(client, started["device_code"]).json()["access_token"]


def _as_device(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_full_pairing_flow(client: TestClient) -> None:
    alice = _owner(client, ALICE)

    started = _start(client)
    assert len(started["user_code"]) == 9 and started["user_code"][4] == "-"
    assert started["expires_in"] == 600 and started["interval"] == 5

    # the owner has not typed the code yet
    pending = _poll(client, started["device_code"])
    assert pending.status_code == 400
    assert pending.json()["detail"] == "authorization_pending"

    # typed loosely: lower case, no dash
    loose = started["user_code"].replace("-", "").lower()
    approved = client.post(
        "/devices/pair/approve", json={"user_code": loose, "name": "Kitchen"}, headers=alice
    )
    assert approved.status_code == 200
    device = approved.json()
    assert device["physical_id"] == "dev-1"
    assert device["name"] == "Kitchen"
    assert device["status"] == "active"

    issued = _poll(client, started["device_code"])
    assert issued.status_code == 200
    token = issued.json()["access_token"]
    assert token.startswith("ppd_")
    assert issued.json()["device_id"] == device["id"]

    me = client.get("/devices/me", headers=_as_device(token))
    assert me.status_code == 200
    assert me.json()["id"] == device["id"]
    assert me.json()["last_seen_at"] is not None

    # one approval, one token
    again = _poll(client, started["device_code"])
    assert again.status_code == 400 and again.json()["detail"] == "invalid_grant"


def test_revoke_stops_the_device_immediately(client: TestClient) -> None:
    alice = _owner(client, ALICE)
    token = _pair(client, alice)
    device_id = client.get("/devices", headers=alice).json()[0]["id"]

    revoked = client.post(f"/devices/{device_id}/revoke", headers=alice)
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"
    assert revoked.json()["revoked_at"] is not None

    assert client.get("/devices/me", headers=_as_device(token)).status_code == 401
    # idempotent
    assert client.post(f"/devices/{device_id}/revoke", headers=alice).status_code == 200

    # pairing again brings it back with a fresh token
    new_token = _pair(client, alice)
    assert client.get("/devices/me", headers=_as_device(new_token)).status_code == 200
    assert client.get("/devices/me", headers=_as_device(token)).status_code == 401


def test_repairing_replaces_the_token(client: TestClient) -> None:
    alice = _owner(client, ALICE)
    old = _pair(client, alice)
    new = _pair(client, alice)

    assert client.get("/devices/me", headers=_as_device(old)).status_code == 401
    assert client.get("/devices/me", headers=_as_device(new)).status_code == 200
    assert len(client.get("/devices", headers=alice).json()) == 1


def test_device_routes_reject_other_credentials(client: TestClient) -> None:
    alice = _owner(client, ALICE)
    assert client.get("/devices/me").status_code == 401
    # an owner's JWT is not a device token
    assert client.get("/devices/me", headers=alice).status_code == 401
    assert client.get("/devices/me", headers=_as_device("ppd_nope")).status_code == 401


def test_approve_requires_a_signed_in_owner(client: TestClient) -> None:
    started = _start(client)
    resp = client.post("/devices/pair/approve", json={"user_code": started["user_code"]})
    assert resp.status_code == 401


def test_unknown_or_superseded_code(client: TestClient) -> None:
    alice = _owner(client, ALICE)
    assert client.post(
        "/devices/pair/approve", json={"user_code": "AAAA-AAAA"}, headers=alice
    ).status_code == 404

    # asking again expires the code the device showed before
    first = _start(client)
    second = _start(client)
    assert client.post(
        "/devices/pair/approve", json={"user_code": first["user_code"]}, headers=alice
    ).status_code == 404
    assert _poll(client, first["device_code"]).json()["detail"] == "expired_token"
    assert client.post(
        "/devices/pair/approve", json={"user_code": second["user_code"]}, headers=alice
    ).status_code == 200

    assert _poll(client, "not-a-code").json()["detail"] == "invalid_grant"


def test_expired_code(client: TestClient, session_factory: sessionmaker[Session]) -> None:
    alice = _owner(client, ALICE)
    started = _start(client)
    with session_factory() as session:
        session.execute(
            update(DevicePairing).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        session.commit()

    assert client.post(
        "/devices/pair/approve", json={"user_code": started["user_code"]}, headers=alice
    ).status_code == 404
    assert _poll(client, started["device_code"]).json()["detail"] == "expired_token"


def test_device_active_under_someone_else(client: TestClient) -> None:
    alice = _owner(client, ALICE)
    bob = _owner(client, BOB)
    alice_token = _pair(client, alice)

    started = _start(client)
    assert client.post(
        "/devices/pair/approve", json={"user_code": started["user_code"]}, headers=bob
    ).status_code == 409

    # once alice lets go, bob can take it over
    device_id = client.get("/devices", headers=alice).json()[0]["id"]
    client.post(f"/devices/{device_id}/revoke", headers=alice)
    bob_token = _pair(client, bob)

    assert client.get("/devices/me", headers=_as_device(alice_token)).status_code == 401
    me = client.get("/devices/me", headers=_as_device(bob_token)).json()
    assert me["id"] == device_id  # same physical device, new owner
    assert client.get("/devices", headers=alice).json() == []


def test_owners_only_see_their_own_devices(client: TestClient) -> None:
    alice = _owner(client, ALICE)
    bob = _owner(client, BOB)
    _pair(client, alice)
    device_id = client.get("/devices", headers=alice).json()[0]["id"]

    assert client.get("/devices", headers=bob).json() == []
    assert client.get(f"/devices/{device_id}", headers=bob).status_code == 404
    assert client.post(f"/devices/{device_id}/revoke", headers=bob).status_code == 404
    assert client.get(f"/devices/{device_id}", headers=alice).status_code == 200
