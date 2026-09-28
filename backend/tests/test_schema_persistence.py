from io import BytesIO
import base64
from pathlib import Path
import sqlite3

import pytest

from app import create_app
from app.schema import SCHEMA_VERSION, backup_sqlite


def config(path):
    return {"TESTING": True, "SECRET_KEY": "persistence-test-only", "SQLALCHEMY_DATABASE_URI": f"sqlite:///{path.as_posix()}"}


def test_additive_upgrade_preserves_existing_tables_and_takes_backup(tmp_path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE legacy_marker (value TEXT)")
        connection.execute("INSERT INTO legacy_marker VALUES ('retained')")
    create_app(config(path))
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT value FROM legacy_marker").fetchone()[0] == "retained"
        assert connection.execute("SELECT version FROM schema_revisions").fetchone()[0] == SCHEMA_VERSION
    snapshots = list((tmp_path / "backups").glob("*.db"))
    assert len(snapshots) == 1
    create_app(config(path))
    assert len(list((tmp_path / "backups").glob("*.db"))) == 1
    with sqlite3.connect(snapshots[0]) as connection:
        assert connection.execute("SELECT value FROM legacy_marker").fetchone()[0] == "retained"


def test_version_two_upgrade_adds_extraction_tables_after_backup(tmp_path):
    path = tmp_path / "version_two.db"
    app = create_app(config(path))
    with app.app_context():
        from app.extensions import db
        db.session.remove()
        db.engine.dispose()
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE measurement_sources")
        connection.execute("DROP TABLE report_extractions")
        connection.execute("UPDATE schema_revisions SET version=2")
        connection.execute("CREATE TABLE retained_marker (value TEXT)")
        connection.execute("INSERT INTO retained_marker VALUES ('untouched')")
    create_app(config(path))
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT value FROM retained_marker").fetchone()[0] == "untouched"
        assert connection.execute("SELECT version FROM schema_revisions ORDER BY version").fetchall() == [(2,), (SCHEMA_VERSION,)]
        assert connection.execute("SELECT count(*) FROM report_extractions").fetchone()[0] == 0
    snapshots = list((tmp_path / "backups").glob(f"before-schema-{SCHEMA_VERSION}-*.db"))
    assert len(snapshots) == 1
    with sqlite3.connect(snapshots[0]) as connection:
        assert connection.execute("SELECT version FROM schema_revisions").fetchone()[0] == 2
        assert connection.execute("SELECT name FROM sqlite_master WHERE name='report_extractions'").fetchone() is None


def test_restart_backup_restore_preserves_account_record_and_attachment(tmp_path):
    original = tmp_path / "health.db"
    app = create_app(config(original))
    client = app.test_client()
    credentials = {"full_name": "Persistent Owner", "email": "persistent@example.test", "password": "Patient123"}
    assert client.post("/api/auth/register", json=credentials).status_code == 201
    record = client.post("/api/records", json={"title": "Persistent record", "content": "Saved information", "record_type": "Other", "record_date": "2026-09-01"}).get_json()["record"]
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=")
    attachment = client.post(f"/api/records/{record['id']}/attachments", data={"file": (BytesIO(png), "report.png")}).get_json()["attachment"]
    saved = backup_sqlite(original, tmp_path / "backup.db")
    restored = backup_sqlite(saved, tmp_path / "restored.db")
    for path in (original, restored):
        restarted = create_app(config(path)).test_client()
        assert restarted.post("/api/auth/login", json=credentials).status_code == 200
        assert restarted.get(f"/api/records/{record['id']}").get_json()["record"]["content"] == "Saved information"
        assert restarted.get(f"/api/records/{record['id']}/attachments/{attachment['id']}").data == png
    with pytest.raises(ValueError, match="never overwritten"):
        backup_sqlite(original, restored)
    assert Path(saved).is_file()


def test_version_three_upgrade_preserves_existing_records_and_only_adds_document_tables(tmp_path):
    path = tmp_path / "version_three.db"
    app = create_app(config(path))
    client = app.test_client()
    client.post("/api/auth/register", json={"full_name": "Existing Owner", "email": "old@example.test", "password": "Patient123"})
    created = client.post("/api/records", json={"title": "Keep existing content", "content": "Private original", "record_type": "Other", "record_date": "2026-09-01"}).get_json()["record"]
    with app.app_context():
        from app.extensions import db
        db.session.remove()
        db.engine.dispose()
    tables = ["document_indexes", "extraction_facts", "profile_fact_sources", "share_scope_snapshots", "share_scope_access_events"]
    with sqlite3.connect(path) as connection:
        for table in tables:
            connection.execute(f"DROP TABLE {table}")
        connection.execute("UPDATE schema_revisions SET version=3")
    create_app(config(path))
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT content FROM health_records WHERE id=?", (created["id"],)).fetchone()[0] == "Private original"
        assert connection.execute("SELECT version FROM schema_revisions ORDER BY version").fetchall() == [(3,), (SCHEMA_VERSION,)]
        for table in tables:
            assert connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
    snapshots = list((tmp_path / "backups").glob(f"before-schema-{SCHEMA_VERSION}-*.db"))
    assert len(snapshots) == 1
    with sqlite3.connect(snapshots[0]) as connection:
        assert connection.execute("SELECT version FROM schema_revisions").fetchone()[0] == 3
        assert connection.execute("SELECT content FROM health_records WHERE id=?", (created["id"],)).fetchone()[0] == "Private original"


def test_version_four_upgrade_adds_advice_and_appointment_tables_without_reset(tmp_path):
    path = tmp_path / "version_four.db"
    app = create_app(config(path))
    with app.app_context():
        from app.extensions import db
        db.session.remove()
        db.engine.dispose()
    tables = ['advice_states', 'advice_results', 'service_clinicians', 'appointment_sharing']
    with sqlite3.connect(path) as connection:
        for table in tables:
            connection.execute(f'DROP TABLE {table}')
        connection.execute('UPDATE schema_revisions SET version=4')
        connection.execute('CREATE TABLE preserved_owner_data (value TEXT)')
        connection.execute("INSERT INTO preserved_owner_data VALUES ('keep')")
    create_app(config(path))
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT value FROM preserved_owner_data').fetchone()[0] == 'keep'
        assert connection.execute('SELECT version FROM schema_revisions ORDER BY version').fetchall() == [(4,), (SCHEMA_VERSION,)]
        for table in tables:
            assert connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0] == 0
    snapshots = list((tmp_path / 'backups').glob(f'before-schema-{SCHEMA_VERSION}-*.db'))
    assert len(snapshots) == 1
    with sqlite3.connect(snapshots[0]) as connection:
        assert connection.execute('SELECT version FROM schema_revisions').fetchone()[0] == 4
        assert connection.execute('SELECT value FROM preserved_owner_data').fetchone()[0] == 'keep'
