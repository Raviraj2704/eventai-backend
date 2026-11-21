import uuid
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check():
    """Verify server and Neon PostgreSQL database are healthy."""
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "healthy"
    assert body["database"] == "connected"


def test_protected_route_blocks_unauthenticated():
    """Verify protected endpoints reject requests without a JWT."""
    res = client.get("/api/v1/favourites/")
    assert res.status_code in (401, 403)


def test_invalid_login_rejected():
    """Verify wrong credentials do not return a token."""
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "nonexistent_smoke_user@example.com", "password": "WrongPassword123!"},
    )
    assert res.status_code in (400, 401, 404)


def test_register_and_login_flow():
    """Verify a new user can register, log in, and access a protected route."""
    unique_email = f"smoke_{uuid.uuid4().hex[:8]}@example.com"
    password = "TestPassword123!"

    reg_res = client.post(
        "/api/v1/auth/register",
        json={
            "email": unique_email,
            "password": password,
            "first_name": "Smoke",
            "last_name": "Tester",
        },
    )
    assert reg_res.status_code in (200, 201), f"Register failed: {reg_res.text}"

    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": unique_email, "password": password},
    )
    assert login_res.status_code == 200, f"Login failed: {login_res.text}"

    data = login_res.json()
    token = data.get("access_token") or data.get("data", {}).get("access_token")
    assert token, f"No access_token in login response: {data}"

    fav_res = client.get(
        "/api/v1/favourites/",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert fav_res.status_code == 200