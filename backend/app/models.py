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


class HealthMeasurement(db.Model):
    __tablename__ = "health_measurements"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    metric_type = db.Column(db.String(30), nullable=False, index=True)
    value = db.Column(db.Float, nullable=False)
    secondary_value = db.Column(db.Float)
    unit = db.Column(db.String(20), nullable=False)
    context = db.Column(db.String(40), nullable=False, default="")
    measured_at = db.Column(db.DateTime, nullable=False, index=True)
    source_type = db.Column(db.String(20), nullable=False, default="self")
    source_name = db.Column(db.String(120), nullable=False, default="Manual entry")
    notes = db.Column(db.String(300), nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    user = db.relationship("User", backref=db.backref("health_measurements", cascade="all, delete-orphan"))

    def to_dict(self, status=None):
        return {
            "id": self.id,
            "metric_type": self.metric_type,
            "value": self.value,
            "secondary_value": self.secondary_value,
            "unit": self.unit,
            "context": self.context,
            "measured_at": self.measured_at.isoformat() + "Z",
            "source_type": self.source_type,
            "source_name": self.source_name,
            "notes": self.notes,
            "status": status,
        }


class HealthAlert(db.Model):
    __tablename__ = "health_alerts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    measurement_id = db.Column(db.Integer, db.ForeignKey("health_measurements.id", ondelete="CASCADE"), nullable=False, unique=True)
    severity = db.Column(db.String(20), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    message = db.Column(db.String(400), nullable=False)
    rule_name = db.Column(db.String(80), nullable=False)
    rule_version = db.Column(db.String(20), nullable=False, default="1.0")
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    acknowledged_at = db.Column(db.DateTime)

    measurement = db.relationship("HealthMeasurement", backref=db.backref("alert", uselist=False, cascade="all, delete-orphan"))

    def to_dict(self):
        return {
            "id": self.id,
            "measurement_id": self.measurement_id,
            "severity": self.severity,
            "title": self.title,
            "message": self.message,
            "rule_name": self.rule_name,
            "rule_version": self.rule_version,
            "created_at": self.created_at.isoformat() + "Z",
            "acknowledged_at": self.acknowledged_at.isoformat() + "Z" if self.acknowledged_at else None,
            "measurement": self.measurement.to_dict(status=self.severity),
        }


class ShareRecipient(db.Model):
    __tablename__ = "share_recipients"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(60), nullable=False)
    organisation = db.Column(db.String(160), nullable=False)
    email = db.Column(db.String(120), nullable=False, unique=True)
    verification_status = db.Column(db.String(20), nullable=False, default="verified")

    def to_dict(self):
        return {
            "id": self.id,
            "full_name": self.full_name,
            "role": self.role,
            "organisation": self.organisation,
            "email": self.email,
            "verification_status": self.verification_status,
        }


class ShareGrantRecord(db.Model):
    __tablename__ = "share_grant_records"

    grant_id = db.Column(db.Integer, db.ForeignKey("share_grants.id", ondelete="CASCADE"), primary_key=True)
    record_id = db.Column(db.Integer, db.ForeignKey("health_records.id", ondelete="CASCADE"), primary_key=True)
    record = db.relationship("HealthRecord", backref=db.backref("share_links", cascade="all, delete-orphan"))


class ShareGrant(db.Model):
    __tablename__ = "share_grants"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey("share_recipients.id"), nullable=False, index=True)
    starts_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    allow_download = db.Column(db.Boolean, nullable=False, default=False)
    purpose = db.Column(db.String(200), nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    revoked_at = db.Column(db.DateTime)

    user = db.relationship("User", backref=db.backref("share_grants", cascade="all, delete-orphan"))
    recipient = db.relationship("ShareRecipient", backref="share_grants")
    record_links = db.relationship("ShareGrantRecord", backref="grant", cascade="all, delete-orphan", lazy="select")

    @property
    def status(self):
        now = utc_now()
        if self.revoked_at:
            return "revoked"
        if self.starts_at > now:
            return "scheduled"
        if self.expires_at <= now:
            return "expired"
        return "active"

    def to_dict(self):
        return {
            "id": self.id,
            "recipient": self.recipient.to_dict(),
            "records": [{
                "id": link.record.id,
                "title": link.record.title,
                "record_type": link.record.record_type,
                "record_date": link.record.record_date.isoformat(),
                "source_name": link.record.source_name,
            } for link in self.record_links],
            "starts_at": self.starts_at.isoformat() + "Z",
            "expires_at": self.expires_at.isoformat() + "Z",
            "allow_download": self.allow_download,
            "allowed_actions": ["view", "download"] if self.allow_download else ["view"],
            "purpose": self.purpose,
            "created_at": self.created_at.isoformat() + "Z",
            "revoked_at": self.revoked_at.isoformat() + "Z" if self.revoked_at else None,
            "status": self.status,
        }


class AccessEvent(db.Model):
    __tablename__ = "access_events"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    grant_id = db.Column(db.Integer, db.ForeignKey("share_grants.id", ondelete="CASCADE"), nullable=False, index=True)
    record_id = db.Column(db.Integer, db.ForeignKey("health_records.id", ondelete="CASCADE"), nullable=False)
    action = db.Column(db.String(30), nullable=False)
    result = db.Column(db.String(30), nullable=False)
    location = db.Column(db.String(120), nullable=False, default="Location unavailable")
    occurred_at = db.Column(db.DateTime, nullable=False, default=utc_now, index=True)
    unusual = db.Column(db.Boolean, nullable=False, default=False)

    grant = db.relationship("ShareGrant", backref=db.backref("access_events", cascade="all, delete-orphan"))
    record = db.relationship("HealthRecord")

    def to_dict(self):
        return {
            "id": self.id,
            "grant_id": self.grant_id,
            "recipient": self.grant.recipient.to_dict(),
            "record": {"id": self.record.id, "title": self.record.title},
            "action": self.action,
            "result": self.result,
            "location": self.location,
            "occurred_at": self.occurred_at.isoformat() + "Z",
            "unusual": self.unusual,
        }
