from app import create_app


def test_health_check():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    response = app.test_client().get("/api/health")

    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


def test_authentication_and_password_reset():
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "RESET_CODE_DELIVERY": "demo",
    })
    client = app.test_client()

    registered = client.post("/api/auth/register", json={
        "full_name": "Test Patient",
        "email": "patient@example.com",
        "password": "Patient123",
    })
    assert registered.status_code == 201
    assert registered.get_json()["user"]["role"] == "patient"
    assert client.get("/api/auth/me").get_json()["user"]["email"] == "patient@example.com"

    assert client.post("/api/auth/logout").status_code == 200
    assert client.post("/api/auth/login", json={"email": "patient@example.com", "password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "patient@example.com", "password": "Patient123"}).status_code == 200

    reset = client.post("/api/auth/password-reset/request", json={"email": "patient@example.com"})
    code = reset.get_json()["demo_code"]
    confirmed = client.post("/api/auth/password-reset/confirm", json={
        "email": "patient@example.com",
        "code": code,
        "password": "Updated123",
    })
    assert confirmed.status_code == 200
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"email": "patient@example.com", "password": "Updated123"}).status_code == 200

