from app import create_app
from app.extensions import db
from app.models import SecurityEvent, User


def test_security_history_beyond_100_is_paginated_and_account_scoped():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    client = app.test_client()
    client.post("/api/auth/register", json={"full_name": "History Owner", "email": "history@example.test", "password": "Patient123"})
    with app.app_context():
        owner = User.query.filter_by(email="history@example.test").one()
        db.session.add_all([SecurityEvent(user_id=owner.id, event_type="profile_updated", description=f"History item {index}") for index in range(105)])
        db.session.commit()
    first = client.get("/api/account/security-events?page_size=100").get_json()
    second = client.get("/api/account/security-events?page=2&page_size=100").get_json()
    assert first["total"] >= 105
    assert len(first["events"]) == 100
    assert len(second["events"]) == first["total"] - 100
    assert not {event["id"] for event in first["events"]} & {event["id"] for event in second["events"]}
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"full_name": "Other Owner", "email": "other-history@example.test", "password": "Patient123"})
    assert all(not event["description"].startswith("History item") for event in client.get("/api/account/security-events").get_json()["events"])
    assert client.get("/api/account/security-events?page=invalid").status_code == 400
