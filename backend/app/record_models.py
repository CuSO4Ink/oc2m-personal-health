"""Additive personal-record tables: existing records remain readable on upgrade."""
from .extensions import db
from .models import utc_now


PROFILE_SECTIONS = ("past_history", "family_history", "medications", "allergies")


def empty_sections():
    return {key: {"status": "unknown", "items": []} for key in PROFILE_SECTIONS}


class PersonalHealthProfile(db.Model):
    __tablename__ = "personal_health_profiles"
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    revision = db.Column(db.Integer, nullable=False, default=1)
    sections = db.Column(db.JSON, nullable=False, default=empty_sections)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now)


def profile_payload(user_id):
    profile = db.session.get(PersonalHealthProfile, user_id)
    return {"revision": profile.revision if profile else 0,
            "sections": profile.sections if profile else empty_sections(),
            "updated_at": profile.updated_at.isoformat() + "Z" if profile else None}


class RecordLifecycle(db.Model):
    __tablename__ = "record_lifecycles"
    record_id = db.Column(db.Integer, db.ForeignKey("health_records.id"), primary_key=True)
    archived_at = db.Column(db.DateTime)
    archive_reason = db.Column(db.String(240), nullable=False, default="")


class RecordPrivacy(db.Model):
    __tablename__ = "record_privacy"
    record_id = db.Column(db.Integer, db.ForeignKey("health_records.id"), primary_key=True)
    sensitive = db.Column(db.Boolean, nullable=False, default=False)
    sensitive_fields = db.Column(db.JSON, nullable=False, default=list)


def record_privacy_payload(record_id):
    privacy = db.session.get(RecordPrivacy, record_id)
    lifecycle = db.session.get(RecordLifecycle, record_id)
    return {"sensitive": privacy.sensitive if privacy else False,
            "sensitive_fields": privacy.sensitive_fields if privacy else [],
            "archived": bool(lifecycle and lifecycle.archived_at)}


class RecordAnnotation(db.Model):
    __tablename__ = "record_annotations"
    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.Integer, db.ForeignKey("health_records.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    kind = db.Column(db.String(20), nullable=False)
    content = db.Column(db.String(2000), nullable=False)
    status = db.Column(db.String(30), nullable=False, default="saved")
    response = db.Column(db.String(1000), nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    def to_dict(self):
        return {"id": self.id, "kind": self.kind, "content": self.content,
                "status": self.status, "response": self.response,
                "created_at": self.created_at.isoformat() + "Z",
                "updated_at": self.updated_at.isoformat() + "Z",
                "delivery": "local_only"}


class RecordImportJob(db.Model):
    __tablename__ = "record_import_jobs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    revision = db.Column(db.Integer, nullable=False, default=1)
    items = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    def to_dict(self):
        return {"id": self.id, "revision": self.revision, "items": self.items,
                "created_at": self.created_at.isoformat() + "Z",
                "updated_at": self.updated_at.isoformat() + "Z", "mode": "simulation",
                "counts": {status: sum(item["status"] == status for item in self.items)
                           for status in ("ready", "imported", "duplicate", "failed")}}


class ProviderImportReference(db.Model):
    __tablename__ = "provider_import_references"
    __table_args__ = (db.UniqueConstraint("user_id", "provider", "external_id", name="uq_provider_import_identity"),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    record_id = db.Column(db.Integer, db.ForeignKey("health_records.id"), nullable=False, unique=True)
    provider = db.Column(db.String(100), nullable=False)
    external_id = db.Column(db.String(120), nullable=False)
    imported_at = db.Column(db.DateTime, nullable=False, default=utc_now)
