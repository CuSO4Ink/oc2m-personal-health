from datetime import date, datetime, timedelta, timezone

from app import create_app
from app.extensions import db
from app.models import AccessEvent, AppointmentSlot, CommunityCircle, CommunityMembership, CommunityPost, ElderCareListing, HealthAlert, HealthMeasurement, HealthRecord, MedicalService, Notification, ServiceFacility, ShareRecipient, User


def test_health_check():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    response = app.test_client().get("/api/health")

    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


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
