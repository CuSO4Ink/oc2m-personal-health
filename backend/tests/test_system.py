from datetime import date, datetime, timezone

from app import create_app
from app.extensions import db
from app.models import HealthRecord, User


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


def test_health_record_crud_history_permissions_and_search():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    client = app.test_client()
    client.post("/api/auth/register", json={
        "full_name": "Record Owner",
        "email": "owner@example.com",
        "password": "Patient123",
    })

    created = client.post("/api/records", json={
        "title": "Migraine diary",
        "record_type": "Other",
        "condition": "Migraine",
        "record_date": "2026-09-12",
        "source_name": "Self-reported",
        "content": "Headache lasted two hours after lunch.",
    })
    assert created.status_code == 201
    record = created.get_json()["record"]
    assert record["version"] == 1
    assert record["is_editable"] is True

    results = client.get("/api/records?q=migraine&type=Other").get_json()
    assert results["count"] == 1
    assert results["records"][0]["id"] == record["id"]

    updated_payload = {
        **record,
        "content": "Headache lasted one hour after lunch and improved with rest.",
        "change_note": "Corrected the duration",
    }
    updated = client.patch(f"/api/records/{record['id']}", json=updated_payload)
    assert updated.status_code == 200
    assert updated.get_json()["record"]["version"] == 2

    stale = client.patch(f"/api/records/{record['id']}", json=updated_payload)
    assert stale.status_code == 409
    history = client.get(f"/api/records/{record['id']}/history").get_json()["versions"]
    assert [item["version"] for item in history] == [2, 1]

    with app.app_context():
        owner = User.query.filter_by(email="owner@example.com").first()
        provider_record = HealthRecord(
            user_id=owner.id,
            title="Provider result",
            record_type="Lab Report",
            record_date=date(2026, 9, 13),
            source_type="hospital",
            source_name="Test Hospital",
            content="Preserved provider content",
        )
        db.session.add(provider_record)
        db.session.commit()
        provider_record_id = provider_record.id
    provider_update = client.patch(f"/api/records/{provider_record_id}", json={
        "title": "Changed result",
        "record_type": "Lab Report",
        "record_date": "2026-09-13",
        "source_name": "Test Hospital",
        "content": "Changed content",
        "version": 1,
    })
    assert provider_update.status_code == 403

    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={
        "full_name": "Different User",
        "email": "different@example.com",
        "password": "Patient123",
    })
    assert client.get(f"/api/records/{record['id']}").status_code == 404


def test_health_measurements_trends_alerts_and_ownership():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    client = app.test_client()
    client.post("/api/auth/register", json={
        "full_name": "Insights Owner",
        "email": "insights@example.com",
        "password": "Patient123",
    })
    measured_at = datetime.now(timezone.utc).isoformat()

    normal = client.post("/api/insights/metrics", json={
        "metric_type": "blood_pressure",
        "value": 122,
        "secondary_value": 78,
        "measured_at": measured_at,
        "source_name": "Home monitor",
    })
    assert normal.status_code == 201
    assert normal.get_json()["measurement"]["status"] == "in_range"
    assert normal.get_json()["alert"] is None

    high = client.post("/api/insights/metrics", json={
        "metric_type": "blood_pressure",
        "value": 150,
        "secondary_value": 95,
        "measured_at": measured_at,
        "source_name": "Manual entry",
    })
    assert high.status_code == 201
    alert = high.get_json()["alert"]
    assert alert["severity"] == "high"

    trend = client.get("/api/insights/metrics?metric=blood_pressure&days=30").get_json()
    assert trend["summary"]["count"] == 2
    assert trend["data_sufficiency"]["status"] == "limited"
    assert len(client.get("/api/insights/alerts").get_json()["alerts"]) == 1
    assert client.patch(f"/api/insights/alerts/{alert['id']}/acknowledge").status_code == 200
    assert client.get("/api/insights/alerts").get_json()["alerts"] == []

    invalid = client.post("/api/insights/metrics", json={
        "metric_type": "blood_glucose",
        "value": 5.5,
        "measured_at": measured_at,
    })
    assert invalid.status_code == 400

    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={
        "full_name": "Other Insights User",
        "email": "other-insights@example.com",
        "password": "Patient123",
    })
    assert client.get("/api/insights/metrics?metric=blood_pressure&days=30").get_json()["summary"]["count"] == 0
    assert client.patch(f"/api/insights/alerts/{alert['id']}/acknowledge").status_code == 404
