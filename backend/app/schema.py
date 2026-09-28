"""Additive schema upgrades with a recoverable SQLite snapshot.

This release adds tables rather than rewriting existing health data. Future
column changes still require an explicit migration, not create_all().
"""
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from flask import current_app
from sqlalchemy import inspect

from .extensions import db


class SchemaRevision(db.Model):
    __tablename__ = "schema_revisions"
    version = db.Column(db.Integer, primary_key=True)
    applied_at = db.Column(db.DateTime, nullable=False)
    description = db.Column(db.String(200), nullable=False)


SCHEMA_VERSION = 5


def backup_sqlite(source, destination):
    """Use SQLite's online backup API, including any committed WAL content."""
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_file():
        raise ValueError("Source database does not exist.")
    if destination.exists():
        raise ValueError("Choose a new destination; existing files are never overwritten.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Reserve the path exclusively before SQLite opens it.
    with destination.open("xb"):
        pass
    try:
        with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as incoming:
            with sqlite3.connect(destination) as outgoing:
                incoming.backup(outgoing)
                if outgoing.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Database integrity verification failed.")
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return destination


def initialize_schema():
    existing = set(inspect(db.engine).get_table_names())
    missing = set(db.metadata.tables) - existing
    database = db.engine.url.database
    if existing and missing and db.engine.dialect.name == "sqlite" and database not in {None, "", ":memory:"}:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup_dir = Path(current_app.config.get("SCHEMA_BACKUP_DIR", Path(database).parent / "backups"))
        backup_sqlite(database, backup_dir / f"before-schema-{SCHEMA_VERSION}-{stamp}.db")
    db.create_all()
    if db.session.get(SchemaRevision, SCHEMA_VERSION) is None:
        db.session.add(SchemaRevision(
            version=SCHEMA_VERSION,
            applied_at=datetime.now(timezone.utc).replace(tzinfo=None),
            description="Add private cloud-advice consent/cache/leases and appointment clinician-sharing associations",
        ))
        db.session.commit()
