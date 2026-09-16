from datetime import date, datetime, timedelta, timezone
from io import BytesIO
import base64

from app import create_app
from app.extensions import db
from app.models import AccessEvent, AppointmentSlot, CommunityCircle, CommunityMembership, CommunityPost, ElderCareListing, HealthAlert, HealthMeasurement, HealthRecord, MedicalService, Notification, ServiceFacility, ShareRecipient, User


def test_health_check():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    response = app.test_client().get("/api/health")

    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


def test_record_attachment_validation_download_delete_and_isolation():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    client = app.test_client()
    client.post("/api/auth/register", json={"full_name": "Document Owner", "email": "documents@example.com", "password": "Patient123"})
    record = client.post("/api/records", json={"title": "Report", "record_type": "Lab Report", "record_date": "2026-09-16", "content": "Report details"}).get_json()["record"]
    endpoint = f"/api/records/{record['id']}/attachments"
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=")
    assert client.post(endpoint).status_code == 400
    assert client.post(endpoint, data={"file": (BytesIO(b"fake image"), "report.png")}).status_code == 400
    assert client.post(endpoint, data={"file": (BytesIO(png), "report.html")}).status_code == 400
    assert client.post(endpoint, data={"file": (BytesIO(b"x" * (10 * 1024 * 1024 + 1)), "large.pdf")}).status_code == 413
    uploaded = client.post(endpoint, data={"file": (BytesIO(png), "../report.png")})
    assert uploaded.status_code == 201
    attachment = uploaded.get_json()["attachment"]
    assert attachment["filename"] == "report.png"
    assert attachment["size"] == len(png)
    content_url = f"{endpoint}/{attachment['id']}"
    content = client.get(content_url)
    assert content.data == png
    assert content.content_type == "image/png"
    assert content.headers["Cache-Control"] == "private, no-store"
    assert "attachment;" in client.get(content_url + "?download=1").headers["Content-Disposition"]
    assert len(client.get(f"/api/records/{record['id']}").get_json()["record"]["attachments"]) == 1
    client.post("/api/auth/logout")
    assert client.get(content_url).status_code == 401
    client.post("/api/auth/register", json={"full_name": "Other Owner", "email": "documents-other@example.com", "password": "Patient123"})
    assert client.get(content_url).status_code == 404
    assert client.delete(content_url).status_code == 404
    assert client.post(endpoint, data={"file": (BytesIO(png), "report.png")}).status_code == 404
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "documents@example.com", "password": "Patient123"})
    with app.app_context():
        saved = db.session.get(HealthRecord, record["id"])
        saved.source_type = "hospital"
        db.session.commit()
    assert client.post(endpoint, data={"file": (BytesIO(png), "report.png")}).status_code == 403
    assert client.delete(content_url).status_code == 403
    with app.app_context():
        db.session.get(HealthRecord, record["id"]).source_type = "self"
        db.session.commit()
    assert client.delete(content_url).get_json()["record"]["attachments"] == []
    assert client.get(content_url).status_code == 404
    pdf = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
    pdf_upload = client.post(endpoint, data={"file": (BytesIO(pdf), "report.pdf")})
    assert pdf_upload.status_code == 201
    pdf_url = f"{endpoint}/{pdf_upload.get_json()['attachment']['id']}"
    assert client.get(pdf_url).content_type == "application/pdf"
    assert client.get(pdf_url).data == pdf
    for index in range(9):
        assert client.post(endpoint, data={"file": (BytesIO(png), f"report-{index}.png")}).status_code == 201
    assert client.post(endpoint, data={"file": (BytesIO(png), "extra.png")}).status_code == 400


def test_overview_empty_state_record_updates_and_account_isolation():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    client = app.test_client()
    assert client.get("/api/overview").status_code == 401
    client.post("/api/auth/register", json={"full_name": "Overview Owner", "email": "overview@example.com", "password": "Patient123"})
    empty = client.get("/api/overview").get_json()
    assert empty["records"]["count"] == 0
    assert all(item["reading"] is None for item in empty["readings"])
    client.post("/api/records", json={"title": "Overview note", "record_type": "Other", "record_date": date.today().isoformat(), "content": "Private note"})
    client.post("/api/services/reminders", json={"title": "Due task", "category": "general", "next_due_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(), "schedule_note": "One time"})
    populated = client.get("/api/overview").get_json()
    assert populated["records"]["count"] == 1
    assert populated["attention"]["due_task_count"] == 1
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"full_name": "Another User", "email": "overview-other@example.com", "password": "Patient123"})
    other = client.get("/api/overview").get_json()
    assert other["records"]["count"] == 0
    assert other["attention"]["due_task_count"] == 0


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
        "value": 118,
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


def test_insights_context_flags_daily_sufficiency_and_review_history():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    client = app.test_client()
    client.post("/api/auth/register", json={"full_name": "Context Owner", "email": "context@example.com", "password": "Patient123"})
    now = datetime.now(timezone.utc)

    def add(metric, value, context="", days_ago=0, secondary=None):
        return client.post("/api/insights/metrics", json={"metric_type": metric, "value": value, "secondary_value": secondary, "context": context, "measured_at": (now - timedelta(days=days_ago)).isoformat()}).get_json()

    assert add("blood_pressure", 120, secondary=78)["measurement"]["status"] == "watch"
    assert add("blood_pressure", 89, secondary=59)["measurement"]["status"] == "low"
    low = add("blood_glucose", 3.8, "random")
    assert low["measurement"]["status"] == "low"
    assert low["alert"]["rule_version"] == "1.1"
    assert add("blood_glucose", 3.9, "fasting")["measurement"]["status"] == "in_range"
    assert add("blood_glucose", 5.6, "fasting", 1)["measurement"]["status"] == "watch"
    assert add("blood_glucose", 7, "fasting", 2)["measurement"]["status"] == "high"
    random = add("blood_glucose", 6, "random")
    assert random["measurement"]["status"] == "not_assessed"
    assert random["alert"] is None
    assert add("blood_glucose", 11.1, "after_meal")["measurement"]["status"] == "high"
    assert add("heart_rate", 130, "exercise")["alert"] is None
    assert add("heart_rate", 59, "resting")["measurement"]["status"] == "watch"
    assert add("heart_rate", 60, "resting")["measurement"]["status"] == "in_range"
    trend = client.get("/api/insights/metrics?metric=blood_glucose&context=fasting").get_json()
    assert trend["summary"]["count"] == 3
    assert trend["summary"]["distinct_days"] == 3
    assert trend["data_sufficiency"]["status"] == "sufficient"
    assert all(item["context"] == "fasting" for item in trend["readings"])
    assert trend["reference"]["sources"]
    same_day = client.get("/api/insights/metrics?metric=heart_rate").get_json()
    assert same_day["data_sufficiency"]["status"] == "limited"
    assert same_day["summary"]["unassessed_count"] == 1
    assert client.get("/api/insights/metrics?metric=heart_rate&context=fasting").status_code == 400
    alert_id = low["alert"]["id"]
    reviewed = client.patch(f"/api/insights/alerts/{alert_id}/acknowledge").get_json()["alert"]
    again = client.patch(f"/api/insights/alerts/{alert_id}/acknowledge").get_json()["alert"]
    assert reviewed["acknowledged_at"] == again["acknowledged_at"]
    history = client.get("/api/insights/alerts?status=reviewed").get_json()
    assert history["count"] == 1
    assert history["alerts"][0]["id"] == alert_id
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"full_name": "Other Context", "email": "context-other@example.com", "password": "Patient123"})
    assert client.get("/api/insights/alerts?status=all").get_json()["alerts"] == []


def test_sharing_permission_preview_lifecycle_and_ownership():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    client = app.test_client()
    client.post("/api/auth/register", json={
        "full_name": "Sharing Owner",
        "email": "sharing@example.com",
        "password": "Patient123",
    })
    record_ids = []
    for title in ["Report A", "Report B"]:
        response = client.post("/api/records", json={
            "title": title,
            "record_type": "Lab Report",
            "record_date": date.today().isoformat(),
            "source_name": "Self-reported",
            "content": "Test content",
        })
        record_ids.append(response.get_json()["record"]["id"])
    with app.app_context():
        recipient = ShareRecipient(
            full_name="Dr. Verified",
            role="General Practitioner",
            organisation="Test Clinic",
            email="verified@example.test",
            verification_status="verified",
        )
        db.session.add(recipient)
        db.session.commit()
        recipient_id = recipient.id

    now = datetime.now(timezone.utc)
    created = client.post("/api/sharing/grants", json={
        "recipient_id": recipient_id,
        "record_ids": record_ids,
        "starts_at": now.isoformat(),
        "expires_at": (now + timedelta(days=7)).isoformat(),
        "allow_download": False,
        "purpose": "Review test results",
    })
    assert created.status_code == 201
    grant = created.get_json()["grant"]
    assert grant["status"] == "active"
    assert grant["allowed_actions"] == ["view"]
    assert {record["id"] for record in grant["records"]} == set(record_ids)

    with app.app_context():
        owner = User.query.filter_by(email="sharing@example.com").first()
        db.session.add(AccessEvent(
            user_id=owner.id,
            grant_id=grant["id"],
            record_id=record_ids[0],
            action="view",
            result="allowed",
            location="Test location",
        ))
        db.session.commit()
    events = client.get("/api/sharing/access-events?action=view&result=allowed").get_json()["events"]
    assert len(events) == 1
    assert events[0]["record"]["id"] == record_ids[0]

    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={
        "full_name": "Other Sharing User",
        "email": "other-sharing@example.com",
        "password": "Patient123",
    })
    assert client.get("/api/sharing/grants").get_json()["grants"] == []
    assert client.patch(f"/api/sharing/grants/{grant['id']}/revoke").status_code == 404
    invalid_scope = client.post("/api/sharing/grants", json={
        "recipient_id": recipient_id,
        "record_ids": record_ids,
        "starts_at": now.isoformat(),
        "expires_at": (now + timedelta(days=7)).isoformat(),
    })
    assert invalid_scope.status_code == 400

    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "sharing@example.com", "password": "Patient123"})
    revoked = client.patch(f"/api/sharing/grants/{grant['id']}/revoke")
    assert revoked.status_code == 200
    assert revoked.get_json()["grant"]["status"] == "revoked"


def test_care_booking_reminders_catalog_and_ownership():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    client = app.test_client()
    client.post("/api/auth/register", json={
        "full_name": "Care User",
        "email": "care@example.com",
        "password": "Patient123",
    })
    with app.app_context():
        facility = ServiceFacility(name="Test Health Centre", address="1 Test Road", phone="000", verified=True)
        service = MedicalService(facility=facility, name="GP Review", specialty="General Practice", duration_minutes=20, cost_label="Test coverage")
        start = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1)
        slot = AppointmentSlot(service=service, starts_at=start, ends_at=start + timedelta(minutes=20), capacity=1)
        listing = ElderCareListing(name="Test Day Centre", category="Day support", address="Test area", summary="Test information", services=["Day activities"], accessibility="Step free", source_name="Test directory")
        db.session.add_all([facility, service, slot, listing])
        db.session.commit()
        slot_id = slot.id

    catalog = client.get("/api/services/medical").get_json()["services"]
    assert len(catalog) == 1
    assert catalog[0]["slots"][0]["available_places"] == 1
    booked = client.post("/api/services/appointments", json={"slot_id": slot_id, "reason": "Review recent readings"})
    assert booked.status_code == 201
    appointment_id = booked.get_json()["appointment"]["id"]
    assert client.post("/api/services/appointments", json={"slot_id": slot_id, "reason": "Duplicate click"}).status_code == 409

    reminder = client.post("/api/services/reminders", json={
        "title": "Check blood pressure",
        "category": "measurement",
        "next_due_at": datetime.now(timezone.utc).isoformat(),
        "schedule_note": "One time",
    })
    assert reminder.status_code == 201
    reminder_id = reminder.get_json()["reminder"]["id"]
    assert client.patch(f"/api/services/reminders/{reminder_id}/complete").get_json()["reminder"]["status"] == "completed"
    assert client.get("/api/services/elder-care?category=Day%20support").get_json()["listings"][0]["name"] == "Test Day Centre"

    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={
        "full_name": "Other Care User",
        "email": "other-care@example.com",
        "password": "Patient123",
    })
    assert client.get("/api/services/appointments").get_json()["appointments"] == []
    assert client.get("/api/services/reminders").get_json()["reminders"] == []
    assert client.patch(f"/api/services/appointments/{appointment_id}/cancel").status_code == 404
    assert client.patch(f"/api/services/reminders/{reminder_id}/complete").status_code == 404
    assert client.post("/api/services/appointments", json={"slot_id": slot_id, "reason": "Try full slot"}).status_code == 409

    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "care@example.com", "password": "Patient123"})
    cancelled = client.patch(f"/api/services/appointments/{appointment_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.get_json()["appointment"]["status"] == "cancelled"


def test_sharing_field_projection_review_and_revocation():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    client = app.test_client()
    client.post("/api/auth/register", json={"full_name": "Field Owner", "email": "fields@example.com", "password": "Patient123"})
    record = client.post("/api/records", json={"title": "Private report", "record_type": "Other", "record_date": "2026-09-16", "content": "Sensitive detail"}).get_json()["record"]
    with app.app_context():
        recipient = ShareRecipient(full_name="Test Doctor", role="Doctor", organisation="Demo", email="test-doctor@example.com")
        db.session.add(recipient); db.session.commit(); recipient_id = recipient.id
    now = datetime.now(timezone.utc)
    payload = {"recipient_id": recipient_id, "record_ids": [record["id"]], "starts_at": (now - timedelta(minutes=1)).isoformat(), "expires_at": (now + timedelta(days=1)).isoformat(), "shared_fields": ["title", "record_date"]}
    grant = client.post("/api/sharing/grants", json=payload).get_json()["grant"]
    endpoint = f"/api/sharing/grants/{grant['id']}/preview"
    preview = client.post(endpoint, json={"action": "view"}).get_json()
    assert preview["mode"] == "owner_preview"
    assert set(preview["records"][0]) == {"title", "record_date"}
    assert client.post(endpoint, json={"action": "download"}).status_code == 403
    assert client.get("/api/sharing/access-events").get_json()["events"] == []
    assert client.post("/api/sharing/grants", json={**payload, "shared_fields": ["attachments"]}).status_code == 400
    with app.app_context():
        event = AccessEvent(user_id=1, grant_id=grant["id"], record_id=record["id"], action="download", result="blocked", unusual=True)
        db.session.add(event); db.session.commit(); event_id = event.id
    reviewed = client.patch(f"/api/sharing/access-events/{event_id}/review").get_json()["event"]
    assert reviewed["reviewed_at"]
    assert client.patch(f"/api/sharing/access-events/{event_id}/review").get_json()["event"]["reviewed_at"] == reviewed["reviewed_at"]
    client.patch(f"/api/sharing/grants/{grant['id']}/revoke")
    assert client.post(endpoint, json={"action": "view"}).status_code == 403
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"full_name": "Other Fields", "email": "other-fields@example.com", "password": "Patient123"})
    assert client.post(endpoint, json={"action": "view"}).status_code == 404
    assert client.patch(f"/api/sharing/access-events/{event_id}/review").status_code == 404


def test_rescheduling_capacity_and_repeating_reminder_idempotence():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    client = app.test_client()
    client.post("/api/auth/register", json={"full_name": "Repeat Owner", "email": "repeat@example.com", "password": "Patient123"})
    with app.app_context():
        facility = ServiceFacility(name="Repeat Centre", address="Demo")
        service = MedicalService(facility=facility, name="Review", specialty="GP")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        slots = [AppointmentSlot(service=service, starts_at=now + timedelta(days=day), ends_at=now + timedelta(days=day, minutes=20), capacity=1, booked_count=1 if day == 3 else 0) for day in [1, 2, 3]]
        db.session.add_all(slots); db.session.commit(); ids = [slot.id for slot in slots]
    appointment = client.post("/api/services/appointments", json={"slot_id": ids[0], "reason": "Routine review"}).get_json()["appointment"]
    endpoint = f"/api/services/appointments/{appointment['id']}/reschedule"
    assert client.patch(endpoint, json={"expected_slot_id": ids[0], "slot_id": ids[2]}).status_code == 409
    assert client.get("/api/services/appointments").get_json()["appointments"][0]["slot"]["id"] == ids[0]
    moved = client.patch(endpoint, json={"expected_slot_id": ids[0], "slot_id": ids[1]})
    assert moved.status_code == 200
    assert moved.get_json()["appointment"]["slot"]["id"] == ids[1]
    with app.app_context():
        assert db.session.get(AppointmentSlot, ids[0]).booked_count == 0
        assert db.session.get(AppointmentSlot, ids[1]).booked_count == 1
    assert client.patch(endpoint, json={"expected_slot_id": ids[0], "slot_id": ids[2]}).status_code == 409
    reminder = client.post("/api/services/reminders", json={"title": "Daily reading", "repeat_days": 1, "next_due_at": (datetime.now(timezone.utc) - timedelta(days=4)).isoformat()}).get_json()["reminder"]
    complete = f"/api/services/reminders/{reminder['id']}/complete"
    assert client.patch(complete).status_code == 200
    assert client.patch(complete).status_code == 200
    reminders = client.get("/api/services/reminders").get_json()["reminders"]
    assert len(reminders) == 2
    current = next(item for item in reminders if item["status"] != "completed")
    assert current["repeat_days"] == 1
    assert current["status"] == "upcoming"
    client.patch(f"/api/services/reminders/{current['id']}/stop-repeat")
    client.patch(f"/api/services/reminders/{current['id']}/complete")
    assert len(client.get("/api/services/reminders").get_json()["reminders"]) == 2
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"full_name": "Other Repeat", "email": "other-repeat@example.com", "password": "Patient123"})
    assert client.patch(endpoint, json={"expected_slot_id": ids[1], "slot_id": ids[0]}).status_code == 404
    assert client.patch(f"/api/services/reminders/{current['id']}/stop-repeat").status_code == 404


def test_community_comment_reports_blocks_anonymity_and_rate_limits():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    owner, visitor = app.test_client(), app.test_client()
    with app.app_context():
        circle = CommunityCircle(name="Interaction circle", topic="Support", description="Test")
        db.session.add(circle); db.session.commit(); circle_id = circle.id
    for client, name, email in [(owner, "Owner Identity", "community-owner-new@example.com"), (visitor, "Secret Visitor Identity", "community-visitor-new@example.com")]:
        client.post("/api/auth/register", json={"full_name": name, "email": email, "password": "Patient123"})
        client.patch("/api/community/profile", json={"enabled": True})
        client.post(f"/api/community/circles/{circle_id}/membership")
    payload = {"circle_id": circle_id, "body": "A supportive personal experience", "anonymous": True, "acknowledged": True}
    post = owner.post("/api/community/posts", json=payload).get_json()["post"]
    other = visitor.post("/api/community/posts", json=payload).get_json()["post"]
    assert owner.post("/api/community/posts", json=payload).status_code == 429
    comment = visitor.post(f"/api/community/posts/{post['id']}/comments", json={"body": "Supportive reply", "anonymous": True}).get_json()["post"]["comments"][0]
    assert visitor.post(f"/api/community/posts/{post['id']}/comments", json={"body": "Repeated reply"}).status_code == 429
    assert owner.delete(f"/api/community/comments/{comment['id']}").status_code == 404
    report_endpoint = f"/api/community/comments/{comment['id']}/reports"
    assert visitor.post(report_endpoint, json={"reason": "spam"}).status_code == 400
    assert owner.post(report_endpoint, json={"reason": "spam", "details": "Test concern"}).status_code == 201
    assert owner.post(report_endpoint, json={"reason": "spam"}).status_code == 409
    assert owner.get("/api/community").get_json()["reports"][0]["target_type"] == "comment"
    assert visitor.get("/api/community").get_json()["reports"] == []
    owner.get("/api/notifications")
    assert owner.post("/api/community/blocks", json={"target_type": "post", "target_id": other["id"]}).status_code == 201
    overview = owner.get("/api/community").get_json()
    assert len(overview["posts"]) == 1
    assert overview["posts"][0]["comments"] == []
    assert overview["blocks"][0]["label"] == "Anonymous member"
    assert "target_id" not in overview["blocks"][0]
    assert "Secret Visitor Identity" not in str(overview)
    assert visitor.get("/api/community").get_json()["posts"][0]["id"] == other["id"]
    assert visitor.post(f"/api/community/posts/{post['id']}/like").status_code == 404
    assert owner.post(f"/api/community/posts/{other['id']}/comments", json={"body": "Blocked reply"}).status_code == 404
    assert owner.get("/api/notifications").get_json()["summary"]["unread"] == 0
    block_id = overview["blocks"][0]["id"]
    assert visitor.delete(f"/api/community/blocks/{block_id}").status_code == 404
    assert owner.delete(f"/api/community/blocks/{block_id}").status_code == 200
    assert len(owner.get("/api/community").get_json()["posts"]) == 2
    assert visitor.delete(f"/api/community/comments/{comment['id']}").status_code == 200
    own = next(item for item in owner.get("/api/community").get_json()["posts"] if item["id"] == post["id"])
    assert own["comment_count"] == 0


def test_optional_community_membership_interactions_reporting_and_isolation():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    client = app.test_client()
    client.post("/api/auth/register", json={
        "full_name": "Community Owner",
        "email": "community-owner@example.com",
        "password": "Patient123",
    })
    with app.app_context():
        circle = CommunityCircle(name="Test Circle", topic="Peer support", description="A test peer-support circle.")
        db.session.add(circle)
        db.session.commit()
        circle_id = circle.id

    initial = client.get("/api/community").get_json()
    assert initial["profile"]["enabled"] is False
    assert initial["posts"] == []
    assert initial["safety"]["health_records_connected"] is False
    assert client.post(f"/api/community/circles/{circle_id}/membership").status_code == 403

    assert client.patch("/api/community/profile", json={"enabled": True}).status_code == 200
    joined = client.post(f"/api/community/circles/{circle_id}/membership")
    assert joined.status_code == 201
    assert joined.get_json()["circle"]["joined"] is True
    rejected = client.post("/api/community/posts", json={
        "circle_id": circle_id,
        "body": "My personal experience",
        "anonymous": True,
    })
    assert rejected.status_code == 400
    created = client.post("/api/community/posts", json={
        "circle_id": circle_id,
        "body": "My personal experience was that a consistent routine helped.",
        "anonymous": True,
        "acknowledged": True,
    })
    assert created.status_code == 201
    post = created.get_json()["post"]
    assert post["author_name"] == "Anonymous member"
    assert post["is_owner"] is True
    liked = client.post(f"/api/community/posts/{post['id']}/like").get_json()["post"]
    assert liked["liked"] is True and liked["like_count"] == 1
    commented = client.post(f"/api/community/posts/{post['id']}/comments", json={
        "body": "Thank you for sharing this.",
        "anonymous": True,
    })
    assert commented.status_code == 201
    assert commented.get_json()["post"]["comment_count"] == 1

    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={
        "full_name": "Other Community User",
        "email": "other-community@example.com",
        "password": "Patient123",
    })
    assert client.get("/api/community").get_json()["posts"] == []
    client.patch("/api/community/profile", json={"enabled": True})
    client.post(f"/api/community/circles/{circle_id}/membership")
    assert len(client.get("/api/community/posts").get_json()["posts"]) == 1
    assert client.delete(f"/api/community/posts/{post['id']}").status_code == 404
    report = client.post(f"/api/community/posts/{post['id']}/reports", json={"reason": "medical_advice", "details": "Please review."})
    assert report.status_code == 201
    assert report.get_json()["report"]["status"] == "submitted"
    assert client.post(f"/api/community/posts/{post['id']}/reports", json={"reason": "medical_advice"}).status_code == 409
    assert client.delete(f"/api/community/circles/{circle_id}/membership").status_code == 200
    assert client.post(f"/api/community/posts/{post['id']}/like").status_code == 404


def test_notification_sync_filters_read_state_archive_and_ownership():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    client = app.test_client()
    client.post("/api/auth/register", json={
        "full_name": "Notification Owner",
        "email": "notifications@example.com",
        "password": "Patient123",
    })
    with app.app_context():
        owner = User.query.filter_by(email="notifications@example.com").first()
        measurement = HealthMeasurement(
            user_id=owner.id,
            metric_type="blood_pressure",
            value=150,
            secondary_value=95,
            unit="mmHg",
            measured_at=datetime.now(timezone.utc).replace(tzinfo=None),
            source_type="self",
            source_name="Test monitor",
        )
        alert = HealthAlert(
            user_id=owner.id,
            measurement=measurement,
            severity="high",
            title="Test health alert",
            message="A test reading needs attention.",
            rule_name="test_rule",
            rule_version="1.0",
        )
        notification = Notification(
            user_id=owner.id,
            category="system",
            severity="info",
            title="Welcome notification",
            message="Your notification centre is ready.",
            action_path="/overview",
            dedupe_key="test-welcome",
            source_name="Test system",
        )
        db.session.add_all([measurement, alert, notification])
        db.session.commit()
        direct_id = notification.id

    listed = client.get("/api/notifications").get_json()
    assert listed["summary"]["unread"] == 2
    assert listed["summary"]["unread_by_category"]["health"] == 1
    assert len(client.get("/api/notifications?category=health&status=unread&q=attention").get_json()["notifications"]) == 1

    read = client.patch(f"/api/notifications/{direct_id}/read", json={"read": True})
    assert read.status_code == 200
    assert read.get_json()["notification"]["unread"] is False
    assert read.get_json()["summary"]["unread"] == 1
    assert client.patch(f"/api/notifications/{direct_id}/read", json={"read": "yes"}).status_code == 400
    assert client.patch(f"/api/notifications/{direct_id}/read", json={"read": False}).get_json()["notification"]["unread"] is True
    assert client.post("/api/notifications/read-all", json={"category": "all"}).get_json()["summary"]["unread"] == 0

    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={
        "full_name": "Other Notification User",
        "email": "other-notifications@example.com",
        "password": "Patient123",
    })
    assert client.get("/api/notifications").get_json()["summary"]["total"] == 0
    assert client.patch(f"/api/notifications/{direct_id}/read", json={"read": True}).status_code == 404
    assert client.delete(f"/api/notifications/{direct_id}").status_code == 404

    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "notifications@example.com", "password": "Patient123"})
    cleared = client.delete(f"/api/notifications/{direct_id}")
    assert cleared.status_code == 200
    assert cleared.get_json()["summary"]["total"] == 1


def test_account_profile_sensitive_changes_sessions_and_security_activity():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    client = app.test_client()
    second_device = app.test_client()
    client.post("/api/auth/register", json={
        "full_name": "Account Owner",
        "email": "account@example.com",
        "password": "Patient123",
    })

    initial = client.get("/api/account").get_json()
    assert initial["profile_completeness"] == 50
    assert initial["sign_in_methods"][0]["status"] == "active"
    assert initial["sign_in_methods"][1]["status"] == "planned"
    updated = client.patch("/api/account/profile", json={
        "full_name": "Account Owner Updated",
        "phone": "+44 7700 900999",
        "date_of_birth": "1980-05-10",
        "preferred_language": "简体中文",
    })
    assert updated.status_code == 200
    assert updated.get_json()["profile_completeness"] == 100
    assert updated.get_json()["profile"]["preferred_language"] == "简体中文"

    assert client.post("/api/account/change-email", json={"email": "changed@example.com", "current_password": "wrong"}).status_code == 403
    changed_email = client.post("/api/account/change-email", json={"email": "changed@example.com", "current_password": "Patient123"})
    assert changed_email.status_code == 200
    assert changed_email.get_json()["user"]["email"] == "changed@example.com"

    assert second_device.post("/api/auth/login", json={"email": "changed@example.com", "password": "Patient123"}).status_code == 200
    sessions_before = client.get("/api/account/sessions").get_json()["sessions"]
    assert len(sessions_before) == 2
    current_session_id = next(item["id"] for item in sessions_before if item["current"])
    other_session_id = next(item["id"] for item in sessions_before if not item["current"])
    assert client.delete(f"/api/account/sessions/{current_session_id}").status_code == 400

    assert client.post("/api/account/change-password", json={"current_password": "wrong", "new_password": "Updated456"}).status_code == 403
    assert client.post("/api/account/change-password", json={"current_password": "Patient123", "new_password": "short"}).status_code == 400
    changed_password = client.post("/api/account/change-password", json={"current_password": "Patient123", "new_password": "Updated456"})
    assert changed_password.status_code == 200
    assert len(client.get("/api/account/sessions").get_json()["sessions"]) == 1
    assert second_device.get("/api/account").status_code == 401
    assert client.delete(f"/api/account/sessions/{other_session_id}").status_code == 404

    events = client.get("/api/account/security-events").get_json()["events"]
    event_types = {event["event_type"] for event in events}
    assert {"account_created", "profile_updated", "email_change_failed", "email_changed", "password_change_failed", "password_changed"}.issubset(event_types)
    assert any(event["important"] for event in events)

    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"email": "changed@example.com", "password": "Patient123"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "changed@example.com", "password": "Updated456"}).status_code == 200
