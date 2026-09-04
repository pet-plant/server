from fastapi.testclient import TestClient

REGISTER = "/auth/register"
TOKEN = "/auth/token"
ME = "/auth/me"

CREDS = {"email": "owner@example.com", "name": "Plant Owner", "password": "hunter2hunter"}


def _register(client: TestClient, **overrides: object) -> dict:
    payload = {**CREDS, **overrides}
    return client.post(REGISTER, json=payload).json()


def _login(
    client: TestClient,
    email: str = CREDS["email"],
    password: str = CREDS["password"],
) -> str:
    resp = client.post(TOKEN, data={"username": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def test_register_returns_user_without_password(client: TestClient) -> None:
    resp = client.post(REGISTER, json=CREDS)

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["email"] == CREDS["email"]
    assert body["name"] == CREDS["name"]
    assert body["is_active"] is True
    assert body["is_superuser"] is False
    assert "password" not in body
    assert "hashed_password" not in body


def test_register_duplicate_email_conflicts(client: TestClient) -> None:
    client.post(REGISTER, json=CREDS)
    resp = client.post(REGISTER, json=CREDS)

    assert resp.status_code == 409


def test_register_rejects_bad_email_and_short_password(client: TestClient) -> None:
    assert client.post(REGISTER, json={**CREDS, "email": "not-an-email"}).status_code == 422
    assert client.post(REGISTER, json={**CREDS, "password": "short"}).status_code == 422


def test_login_and_access_me(client: TestClient) -> None:
    client.post(REGISTER, json=CREDS)
    token = _login(client)

    resp = client.get(ME, headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["email"] == CREDS["email"]


def test_login_with_wrong_password_is_unauthorized(client: TestClient) -> None:
    client.post(REGISTER, json=CREDS)
    resp = client.post(TOKEN, data={"username": CREDS["email"], "password": "nope"})

    assert resp.status_code == 401


def test_me_requires_token(client: TestClient) -> None:
    assert client.get(ME).status_code == 401
    assert client.get(ME, headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_email_is_normalised_to_lowercase(client: TestClient) -> None:
    client.post(REGISTER, json={**CREDS, "email": "Owner@Example.com"})
    token = _login(client, email="owner@example.com")

    resp = client.get(ME, headers={"Authorization": f"Bearer {token}"})
    assert resp.json()["email"] == "owner@example.com"
