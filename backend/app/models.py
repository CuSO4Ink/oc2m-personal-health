from datetime import date, datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="patient")
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        initials = "".join(part[0] for part in self.full_name.split()[:2]).upper()
        return {
            "id": self.id,
            "email": self.email,
            "full_name": self.full_name,
            "initials": initials or "PH",
            "role": self.role,
        }


class PasswordResetToken(db.Model):
    __tablename__ = "password_reset_tokens"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    code_hash = db.Column(db.String(255), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    user = db.relationship("User", backref=db.backref("password_reset_tokens", cascade="all, delete-orphan"))

    def set_code(self, code):
        self.code_hash = generate_password_hash(code)

    def check_code(self, code):
        return check_password_hash(self.code_hash, code)


class HealthRecord(db.Model):
    __tablename__ = "health_records"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.String(160), nullable=False)
    record_type = db.Column(db.String(40), nullable=False, index=True)
    condition = db.Column(db.String(120), nullable=False, default="")
    record_date = db.Column(db.Date, nullable=False, default=date.today, index=True)
    source_type = db.Column(db.String(20), nullable=False, default="self", index=True)
    source_name = db.Column(db.String(160), nullable=False, default="Self-reported")
    content = db.Column(db.Text, nullable=False)
    version = db.Column(db.Integer, nullable=False, default=1)
    synced_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    user = db.relationship("User", backref=db.backref("health_records", cascade="all, delete-orphan"))

    @property
    def is_editable(self):
        return self.source_type == "self"

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "record_type": self.record_type,
            "condition": self.condition,
            "record_date": self.record_date.isoformat(),
            "source_type": self.source_type,
            "source_name": self.source_name,
            "content": self.content,
            "version": self.version,
            "is_editable": self.is_editable,
            "synced_at": self.synced_at.isoformat() + "Z" if self.synced_at else None,
            "created_at": self.created_at.isoformat() + "Z",
            "updated_at": self.updated_at.isoformat() + "Z",
        }


class HealthRecordVersion(db.Model):
    __tablename__ = "health_record_versions"

    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.Integer, db.ForeignKey("health_records.id", ondelete="CASCADE"), nullable=False, index=True)
    version = db.Column(db.Integer, nullable=False)
    snapshot = db.Column(db.JSON, nullable=False)
    changed_by = db.Column(db.String(100), nullable=False)
    change_note = db.Column(db.String(240), nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    record = db.relationship("HealthRecord", backref=db.backref("versions", cascade="all, delete-orphan", order_by="HealthRecordVersion.version.desc()"))

    def to_dict(self):
        return {
            "id": self.id,
            "version": self.version,
            "snapshot": self.snapshot,
            "changed_by": self.changed_by,
            "change_note": self.change_note,
            "created_at": self.created_at.isoformat() + "Z",
        }
