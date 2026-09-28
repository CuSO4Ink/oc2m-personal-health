from datetime import datetime, timedelta, timezone
import pytest

from app import create_app


def test_edit_and_cancel_reminder_preserves_history_and_resolves_attention():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    client = app.test_client()
    client.post("/api/auth/register", json={"full_name": "Task Owner", "email": "tasks@example.test", "password": "Patient123"})
    payload = {"title": "Read a report", "next_due_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(), "repeat_days": 1}
    reminder = client.post("/api/services/reminders", json=payload).get_json()["reminder"]
    assert client.get("/api/notifications/summary").get_json()["summary"]["unread_by_category"]["care"] == 1
    updated = client.patch(f"/api/services/reminders/{reminder['id']}", json={**payload, "title": "Read the updated report", "next_due_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()})
    assert updated.status_code == 200
    assert client.get("/api/overview").get_json()["attention"]["due_task_count"] == 0
    assert client.patch(f"/api/services/reminders/{reminder['id']}/cancel").get_json()["reminder"]["status"] == "cancelled"
    assert client.patch(f"/api/services/reminders/{reminder['id']}/complete").status_code == 409
    assert client.patch(f"/api/services/reminders/{reminder['id']}", json=payload).status_code == 409
    assert client.get("/api/services/reminders").get_json()["reminders"][0]["cancelled_at"]
    assert client.get("/api/notifications/summary").get_json()["summary"]["unread_by_category"]["care"] == 0
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"full_name": "Other Task Owner", "email": "other-tasks@example.test", "password": "Patient123"})
    assert client.patch(f"/api/services/reminders/{reminder['id']}/cancel").status_code == 404


def test_unconnected_recovery_never_claims_delivery():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "RESET_CODE_DELIVERY": "disabled"})
    client = app.test_client()
    response = client.post("/api/auth/password-reset/request", json={"email": "anyone@example.test"})
    assert response.status_code == 503
    assert "demo_code" not in response.get_json()
    assert client.post("/api/auth/password-reset/confirm", json={}).status_code == 503


@pytest.mark.parametrize("override", [{"SECRET_KEY": "replace-with-a-random-development-secret"}, {"RESET_CODE_DELIVERY": "demo"}, {"DEMO_FEATURES_ENABLED": True}])
def test_production_rejects_demo_credentials_or_features(override):
    config = {"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "APP_ENV": "production", "SECRET_KEY": "isolated-production-configuration-test", "RESET_CODE_DELIVERY": "disabled", "DEMO_FEATURES_ENABLED": False, **override}
    with pytest.raises(ValueError, match="Production requires"):
        create_app(config)
