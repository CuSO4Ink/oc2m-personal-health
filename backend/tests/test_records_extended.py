from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

import pytest

import app as application
from app.extensions import db
from app.models import HealthRecord, HealthRecordVersion
from app.record_models import empty_sections


@pytest.fixture
def app_factory(monkeypatch):
    monkeypatch.setattr(application, "load_dotenv", lambda: None)

    def make(uri="sqlite:///:memory:", **extra):
        return application.create_app({"TESTING": True, "SECRET_KEY": "record-test-only",
            "SQLALCHEMY_DATABASE_URI": uri, "DEMO_FEATURES_ENABLED": True, **extra})
    return make


def register(app, email="records@example.invalid"):
    client = app.test_client()
    assert client.post("/api/auth/register", json={"full_name": "Record Test", "email": email, "password": "RecordTest123"}).status_code == 201
    return client


def create(client, **values):
    payload = {"title": "Blood pressure review", "record_type": "Visit Summary",
        "record_date": "2026-09-10", "condition": "Hypertension", "source_name": "Self-reported", "content": "Original personal note"}
    response = client.post("/api/records", json={**payload, **values})
    assert response.status_code == 201
    return response.get_json()["record"]


def test_profile_unknown_none_validation_isolation_and_revision(app_factory):
    app = app_factory()
    client = register(app)
    initial = client.get("/api/records/profile").get_json()["profile"]
    assert initial["revision"] == 0
    assert all(section["status"] == "unknown" for section in initial["sections"].values())
    sections = empty_sections()
    sections["allergies"] = {"status": "none", "items": []}
    sections["family_history"] = {"status": "recorded", "items": [{"name": "Example condition", "relationship": "Parent", "sensitive": True}]}
    result = client.put("/api/records/profile", json={"revision": 0, "sections": sections})
    assert result.status_code == 200
    profile = result.get_json()["profile"]
    assert profile["sections"]["allergies"]["status"] == "none"
    assert profile["sections"]["family_history"]["items"][0]["id"]
    assert client.put("/api/records/profile", json={"revision": 0, "sections": sections}).status_code == 409
    sections["medications"] = {"status": "none", "items": [{"name": "Must not disappear"}]}
    assert client.put("/api/records/profile", json={"revision": 1, "sections": sections}).status_code == 400
    other = register(app, "other@example.invalid")
    assert other.get("/api/records/profile").get_json()["profile"]["revision"] == 0
    assert other.get("/api/records/audit").get_json()["events"] == []


def test_archive_restore_privacy_notes_and_original_preserved(app_factory):
    app = app_factory()
    client = register(app)
    record = create(client)
    rid = record["id"]
    response = client.patch(f"/api/records/{rid}/privacy", json={"version": 1, "sensitive": True, "sensitive_fields": ["content"]})
    assert response.get_json()["record"]["sensitive"] is True
    archived = client.patch(f"/api/records/{rid}/archive", json={"version": 2, "archived": True}).get_json()["record"]
    assert archived["archived"] and not archived["is_editable"]
    assert client.get("/api/records").get_json()["records"] == []
    assert client.get("/api/records?archived=archived").get_json()["count"] == 1
    assert client.patch(f"/api/records/{rid}", json={**record, "version": 3, "content": "Should not overwrite"}).status_code == 403
    assert client.patch(f"/api/records/{rid}/archive", json={"version": 3, "archived": False}).status_code == 200
    with app.app_context():
        db.session.get(HealthRecord, rid).source_type = "hospital"
        db.session.commit()
    correction = client.post(f"/api/records/{rid}/annotations", json={"kind": "correction", "content": "Please review this source detail"}).get_json()["record"]
    annotation = correction["annotations"][0]
    assert annotation["delivery"] == "local_only"
    assert annotation["status"] == "awaiting_review"
    result = client.post(f"/api/records/{rid}/annotations/{annotation['id']}/simulate-response").get_json()["record"]
    assert result["content"] == record["content"]
    assert result["annotations"][0]["status"] == "simulated_response"
    other = register(app, "other@example.invalid")
    assert other.post(f"/api/records/{rid}/annotations", json={"kind": "note", "content": "Private"}).status_code == 404
    assert other.patch(f"/api/records/{rid}/archive", json={"version": 4, "archived": True}).status_code == 404


def test_attachment_versions_and_audit_survive_file_removal(app_factory):
    client = register(app_factory())
    record = create(client)
    rid = record["id"]
    uploaded = client.post(f"/api/records/{rid}/attachments", data={"version": "1", "file": (BytesIO(b"%PDF-1.4\nsmall test\n%%EOF"), "report.pdf")}, content_type="multipart/form-data")
    assert uploaded.status_code == 201
    item = uploaded.get_json()
    assert item["record"]["version"] == 2
    aid = item["attachment"]["id"]
    assert client.delete(f"/api/records/{rid}/attachments/{aid}", json={"version": 1}).status_code == 409
    assert client.get(f"/api/records/{rid}/attachments/{aid}?download=1").status_code == 200
    assert client.delete(f"/api/records/{rid}/attachments/{aid}", json={"version": 2}).status_code == 200
    history = client.get(f"/api/records/{rid}/history").get_json()
    assert [version["version"] for version in history["versions"]] == [3, 2, 1]
    assert {"attachment_added", "attachment_deleted", "download"} <= {event["action"] for event in history["events"]}
    assert next(event for event in history["events"] if event["action"] == "attachment_deleted")["details"]["filename"] == "report.pdf"
    assert client.get(f"/api/records/{rid}/attachments/{aid}").status_code == 404


def test_atomic_concurrent_updates_preserve_winner_and_history(app_factory, tmp_path):
    uri = "sqlite:///" + (tmp_path / "concurrency.db").as_posix()
    app = app_factory(uri)
    first = register(app)
    second = app.test_client()
    assert second.post("/api/auth/login", json={"email": "records@example.invalid", "password": "RecordTest123"}).status_code == 200
    record = create(first)
    def edit(args):
        client, content = args
        return client.patch(f"/api/records/{record['id']}", json={**record, "content": content, "version": 1})
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(edit, [(first, "First draft"), (second, "Second draft")]))
    assert sorted(response.status_code for response in responses) == [200, 409]
    winner = next(response.get_json()["record"] for response in responses if response.status_code == 200)
    loser = next(response.get_json()["record"] for response in responses if response.status_code == 409)
    assert winner["content"] == loser["content"]
    with app.app_context():
        assert HealthRecordVersion.query.filter_by(record_id=record["id"], version=2).count() == 1
    assert second.patch(f"/api/records/{record['id']}", json={**record, "content": "Repeated stale overwrite", "version": 1}).status_code == 409


def test_import_classification_partial_retry_deduplication_and_restart(app_factory, tmp_path):
    uri = "sqlite:///" + (tmp_path / "restart.db").as_posix()
    app = app_factory(uri)
    client = register(app)
    job = client.post("/api/records/imports").get_json()["job"]
    selections = {item["external_id"]: item["selected_type"] for item in job["items"]}
    result = client.post(f"/api/records/imports/{job['id']}/confirm", json={"revision": job["revision"], "selections": selections, "simulate_failure_once": True})
    assert result.status_code == 200
    partial = result.get_json()["job"]
    assert partial["counts"]["imported"] == 7 and partial["counts"]["failed"] == 1
    # Recreate the application and sessions against a test-only file to verify durability.
    restarted = app_factory(uri)
    client = restarted.test_client()
    assert client.post("/api/auth/login", json={"email": "records@example.invalid", "password": "RecordTest123"}).status_code == 200
    persisted = client.get("/api/records/imports").get_json()["jobs"][0]
    assert persisted["counts"] == partial["counts"]
    retried = client.post(f"/api/records/imports/{job['id']}/retry", json={"revision": persisted["revision"]}).get_json()["job"]
    assert retried["counts"]["imported"] == 8
    repeated = client.post("/api/records/imports").get_json()["job"]
    deduped = client.post(f"/api/records/imports/{repeated['id']}/confirm", json={"revision": repeated["revision"], "selections": selections}).get_json()["job"]
    assert deduped["counts"]["duplicate"] == 8
    assert client.get("/api/records").get_json()["count"] == 8
    other = register(restarted, "other@example.invalid")
    assert other.post(f"/api/records/imports/{job['id']}/retry", json={"revision": retried["revision"]}).status_code == 404
    assert other.get("/api/records/imports").get_json()["jobs"] == []


def test_search_alias_typo_disease_filter_and_demo_guard(app_factory):
    app = app_factory()
    client = register(app)
    record = create(client)
    assert client.get("/api/records?q=高血压").get_json()["count"] == 1
    approximate = client.get("/api/records?q=hypertensoin").get_json()["records"]
    assert approximate[0]["search_match"] == "approximate"
    assert client.get("/api/records?condition=Hypertension").get_json()["count"] == 1
    assert client.get("/api/records?condition=Other").get_json()["count"] == 0
    assert client.post("/api/records/classify", json={"title": "Prescription", "content": "Existing medication list"}).get_json()["record_type"] == "Medication"
    app.config["DEMO_FEATURES_ENABLED"] = False
    assert client.post("/api/records/imports").status_code == 503
    annotation = client.post(f"/api/records/{record['id']}/annotations", json={"kind": "correction", "content": "Local request remains available"}).get_json()["record"]["annotations"][0]
    assert client.post(f"/api/records/{record['id']}/annotations/{annotation['id']}/simulate-response").status_code == 503


def test_record_pagination_search_total_filters_and_user_isolation(app_factory):
    from datetime import date
    app = app_factory()
    client = register(app)
    owner_id = client.get("/api/auth/me").get_json()["user"]["id"]
    other = register(app, "other@example.invalid")
    other_id = other.get("/api/auth/me").get_json()["user"]["id"]
    with app.app_context():
        for index in range(35):
            db.session.add(HealthRecord(user_id=owner_id, title=f"Record {index:02}",
                condition="Hypertension" if index < 31 else "Unrelated condition", record_type="Visit Summary",
                content="Personal note", record_date=date(2026, 9, 10)))
        db.session.add(HealthRecord(user_id=other_id, title="Private record", condition="Private other disease",
            record_type="Visit Summary", content="Hypertension", record_date=date(2026, 9, 10)))
        db.session.commit()
    first = client.get("/api/records").get_json()
    second = client.get("/api/records?page=2&page_size=20").get_json()
    assert (first["count"], first["total"], first["page"], first["page_size"]) == (20, 35, 1, 20)
    assert second["count"] == 15 and second["total"] == 35
    assert not {row["id"] for row in first["records"]} & {row["id"] for row in second["records"]}
    assert "Private other disease" not in first["conditions"]
    assert set(first["conditions"]) == {"Hypertension", "Unrelated condition"}
    for query in ("q=高血压", "q=hypertensoin", "condition=Hypertension&type=Visit%20Summary&source=self&from=2026-09-01&to=2026-09-30"):
        result = client.get(f"/api/records?{query}&page=4&page_size=7").get_json()
        assert result["total"] == 31 and result["count"] == 7
        if "hypertensoin" in query:
            assert all(row["search_match"] == "approximate" for row in result["records"])
    assert client.get("/api/records?page=10&page_size=20").get_json()["records"] == []
    assert other.get("/api/records").get_json()["total"] == 1
    for query in ("page=0", "page=-1", "page_size=201", "page_size=0", "page=x"):
        assert client.get(f"/api/records?{query}").status_code == 400


def test_profile_revision_snapshots_survive_removal_restart_and_are_private(app_factory, tmp_path):
    uri = "sqlite:///" + (tmp_path / "profile-history.db").as_posix()
    app = app_factory(uri)
    client = register(app)
    sections = empty_sections()
    sections["medications"] = {"status": "recorded", "items": [{"name": "Previously recorded medicine", "dose": "Existing instructions", "sensitive": True}]}
    saved = client.put("/api/records/profile", json={"revision": 0, "sections": sections}).get_json()["profile"]
    sections["medications"] = {"status": "none", "items": []}
    assert client.put("/api/records/profile", json={"revision": saved["revision"], "sections": sections}).status_code == 200
    restarted = app_factory(uri)
    reader = restarted.test_client()
    reader.post("/api/auth/login", json={"email": "records@example.invalid", "password": "RecordTest123"})
    revisions = reader.get("/api/records/profile/history").get_json()["revisions"]
    assert [revision["revision"] for revision in revisions] == [2, 1]
    assert revisions[0]["snapshot"]["medications"]["status"] == "none"
    assert revisions[1]["snapshot"]["medications"]["items"][0]["name"] == "Previously recorded medicine"
    other = register(restarted, "other@example.invalid")
    assert other.get("/api/records/profile/history").get_json()["revisions"] == []
