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


class ServiceFacility(db.Model):
    __tablename__ = "service_facilities"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False, unique=True)
    address = db.Column(db.String(240), nullable=False)
    phone = db.Column(db.String(40), nullable=False, default="")
    verified = db.Column(db.Boolean, nullable=False, default=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "address": self.address,
            "phone": self.phone,
            "verified": self.verified,
            "updated_at": self.updated_at.isoformat() + "Z",
        }


class MedicalService(db.Model):
    __tablename__ = "medical_services"

    id = db.Column(db.Integer, primary_key=True)
    facility_id = db.Column(db.Integer, db.ForeignKey("service_facilities.id"), nullable=False, index=True)
    name = db.Column(db.String(140), nullable=False)
    specialty = db.Column(db.String(80), nullable=False, index=True)
    appointment_mode = db.Column(db.String(30), nullable=False, default="in_person")
    duration_minutes = db.Column(db.Integer, nullable=False, default=20)
    cost_label = db.Column(db.String(80), nullable=False, default="Contact provider")
    active = db.Column(db.Boolean, nullable=False, default=True)

    facility = db.relationship("ServiceFacility", backref="medical_services")

    def to_dict(self, include_slots=False):
        result = {
            "id": self.id,
            "name": self.name,
            "specialty": self.specialty,
            "appointment_mode": self.appointment_mode,
            "duration_minutes": self.duration_minutes,
            "cost_label": self.cost_label,
            "facility": self.facility.to_dict(),
        }
        if include_slots:
            result["slots"] = [slot.to_dict() for slot in self.slots if slot.starts_at > utc_now()]
        return result


class AppointmentSlot(db.Model):
    __tablename__ = "appointment_slots"

    id = db.Column(db.Integer, primary_key=True)
    service_id = db.Column(db.Integer, db.ForeignKey("medical_services.id"), nullable=False, index=True)
    starts_at = db.Column(db.DateTime, nullable=False, index=True)
    ends_at = db.Column(db.DateTime, nullable=False)
    capacity = db.Column(db.Integer, nullable=False, default=1)
    booked_count = db.Column(db.Integer, nullable=False, default=0)

    service = db.relationship("MedicalService", backref=db.backref("slots", order_by="AppointmentSlot.starts_at.asc()"))

    @property
    def available_places(self):
        return max(0, self.capacity - self.booked_count)

    def to_dict(self):
        return {
            "id": self.id,
            "starts_at": self.starts_at.isoformat() + "Z",
            "ends_at": self.ends_at.isoformat() + "Z",
            "capacity": self.capacity,
            "available_places": self.available_places,
            "available": self.starts_at > utc_now() and self.available_places > 0,
        }


class Appointment(db.Model):
    __tablename__ = "appointments"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    slot_id = db.Column(db.Integer, db.ForeignKey("appointment_slots.id"), nullable=False, index=True)
    reason = db.Column(db.String(300), nullable=False, default="")
    status = db.Column(db.String(30), nullable=False, default="confirmed", index=True)
    booked_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    cancelled_at = db.Column(db.DateTime)

    user = db.relationship("User", backref=db.backref("appointments", cascade="all, delete-orphan"))
    slot = db.relationship("AppointmentSlot", backref="appointments")

    def to_dict(self):
        return {
            "id": self.id,
            "reason": self.reason,
            "status": self.status,
            "booked_at": self.booked_at.isoformat() + "Z",
            "cancelled_at": self.cancelled_at.isoformat() + "Z" if self.cancelled_at else None,
            "slot": self.slot.to_dict(),
            "service": self.slot.service.to_dict(),
        }


class HealthReminder(db.Model):
    __tablename__ = "health_reminders"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.String(160), nullable=False)
    category = db.Column(db.String(40), nullable=False, default="general")
    next_due_at = db.Column(db.DateTime, nullable=False, index=True)
    schedule_note = db.Column(db.String(160), nullable=False, default="One time")
    source_name = db.Column(db.String(120), nullable=False, default="Personal reminder")
    notes = db.Column(db.String(300), nullable=False, default="")
    completed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    user = db.relationship("User", backref=db.backref("health_reminders", cascade="all, delete-orphan"))

    @property
    def status(self):
        if self.completed_at:
            return "completed"
        if self.next_due_at < utc_now():
            return "overdue"
        return "upcoming"

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "next_due_at": self.next_due_at.isoformat() + "Z",
            "schedule_note": self.schedule_note,
            "source_name": self.source_name,
            "notes": self.notes,
            "completed_at": self.completed_at.isoformat() + "Z" if self.completed_at else None,
            "status": self.status,
        }


class ElderCareListing(db.Model):
    __tablename__ = "elder_care_listings"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(180), nullable=False, unique=True)
    category = db.Column(db.String(60), nullable=False, index=True)
    address = db.Column(db.String(240), nullable=False)
    summary = db.Column(db.String(500), nullable=False)
    services = db.Column(db.JSON, nullable=False)
    accessibility = db.Column(db.String(240), nullable=False, default="")
    source_name = db.Column(db.String(140), nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    active = db.Column(db.Boolean, nullable=False, default=True)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "address": self.address,
            "summary": self.summary,
            "services": self.services,
            "accessibility": self.accessibility,
            "source_name": self.source_name,
            "updated_at": self.updated_at.isoformat() + "Z",
        }


class CommunityProfile(db.Model):
    __tablename__ = "community_profiles"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    enabled = db.Column(db.Boolean, nullable=False, default=False)
    joined_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    user = db.relationship("User", backref=db.backref("community_profile", uselist=False, cascade="all, delete-orphan"))

    def to_dict(self):
        return {
            "enabled": self.enabled,
            "joined_at": self.joined_at.isoformat() + "Z" if self.joined_at else None,
            "updated_at": self.updated_at.isoformat() + "Z",
        }


class CommunityCircle(db.Model):
    __tablename__ = "community_circles"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    topic = db.Column(db.String(80), nullable=False, index=True)
    description = db.Column(db.String(400), nullable=False)
    guidance = db.Column(db.String(240), nullable=False, default="Share personal experience and seek professional care for medical advice.")
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    def to_dict(self, user_id=None):
        memberships = [membership for membership in self.memberships if membership.left_at is None]
        return {
            "id": self.id,
            "name": self.name,
            "topic": self.topic,
            "description": self.description,
            "guidance": self.guidance,
            "member_count": len(memberships),
            "joined": any(membership.user_id == user_id for membership in memberships) if user_id else False,
        }


class CommunityMembership(db.Model):
    __tablename__ = "community_memberships"
    __table_args__ = (db.UniqueConstraint("user_id", "circle_id", name="uq_community_membership"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    circle_id = db.Column(db.Integer, db.ForeignKey("community_circles.id", ondelete="CASCADE"), nullable=False, index=True)
    joined_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    left_at = db.Column(db.DateTime)

    user = db.relationship("User", backref=db.backref("community_memberships", cascade="all, delete-orphan"))
    circle = db.relationship("CommunityCircle", backref=db.backref("memberships", cascade="all, delete-orphan"))


class CommunityPost(db.Model):
    __tablename__ = "community_posts"

    id = db.Column(db.Integer, primary_key=True)
    circle_id = db.Column(db.Integer, db.ForeignKey("community_circles.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    body = db.Column(db.String(1200), nullable=False)
    anonymous = db.Column(db.Boolean, nullable=False, default=True)
    status = db.Column(db.String(30), nullable=False, default="published", index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now, index=True)

    user = db.relationship("User", backref=db.backref("community_posts", cascade="all, delete-orphan"))
    circle = db.relationship("CommunityCircle", backref=db.backref("posts", cascade="all, delete-orphan"))

    def to_dict(self, viewer_id=None):
        active_comments = [comment for comment in self.comments if comment.status == "published"]
        return {
            "id": self.id,
            "circle": {"id": self.circle.id, "name": self.circle.name, "topic": self.circle.topic},
            "body": self.body,
            "anonymous": self.anonymous,
            "author_name": "Anonymous member" if self.anonymous else self.user.full_name,
            "is_owner": self.user_id == viewer_id,
            "liked": any(like.user_id == viewer_id for like in self.likes),
            "like_count": len(self.likes),
            "comment_count": len(active_comments),
            "comments": [comment.to_dict(viewer_id) for comment in active_comments],
            "created_at": self.created_at.isoformat() + "Z",
        }


class CommunityLike(db.Model):
    __tablename__ = "community_likes"
    __table_args__ = (db.UniqueConstraint("user_id", "post_id", name="uq_community_like"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    post_id = db.Column(db.Integer, db.ForeignKey("community_posts.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    user = db.relationship("User")
    post = db.relationship("CommunityPost", backref=db.backref("likes", cascade="all, delete-orphan"))


class CommunityComment(db.Model):
    __tablename__ = "community_comments"

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("community_posts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    body = db.Column(db.String(500), nullable=False)
    anonymous = db.Column(db.Boolean, nullable=False, default=True)
    status = db.Column(db.String(30), nullable=False, default="published", index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    user = db.relationship("User")
    post = db.relationship("CommunityPost", backref=db.backref("comments", cascade="all, delete-orphan", order_by="CommunityComment.created_at.asc()"))

    def to_dict(self, viewer_id=None):
        return {
            "id": self.id,
            "body": self.body,
            "anonymous": self.anonymous,
            "author_name": "Anonymous member" if self.anonymous else self.user.full_name,
            "is_owner": self.user_id == viewer_id,
            "created_at": self.created_at.isoformat() + "Z",
        }


class CommunityReport(db.Model):
    __tablename__ = "community_reports"
    __table_args__ = (db.UniqueConstraint("reporter_id", "post_id", name="uq_community_report"),)

    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    post_id = db.Column(db.Integer, db.ForeignKey("community_posts.id", ondelete="CASCADE"), nullable=False, index=True)
    reason = db.Column(db.String(60), nullable=False)
    details = db.Column(db.String(500), nullable=False, default="")
    status = db.Column(db.String(30), nullable=False, default="submitted", index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    reporter = db.relationship("User")
    post = db.relationship("CommunityPost", backref=db.backref("reports", cascade="all, delete-orphan"))


class Notification(db.Model):
    __tablename__ = "notifications"
    __table_args__ = (db.UniqueConstraint("user_id", "dedupe_key", name="uq_user_notification_key"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    category = db.Column(db.String(30), nullable=False, index=True)
    severity = db.Column(db.String(20), nullable=False, default="info", index=True)
    title = db.Column(db.String(180), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    action_path = db.Column(db.String(160), nullable=False, default="")
    dedupe_key = db.Column(db.String(120), nullable=False)
    source_name = db.Column(db.String(140), nullable=False, default="Personal Health")
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now, index=True)
    read_at = db.Column(db.DateTime, index=True)
    archived_at = db.Column(db.DateTime, index=True)

    user = db.relationship("User", backref=db.backref("notifications", cascade="all, delete-orphan"))

    def to_dict(self):
        return {
            "id": self.id,
            "category": self.category,
            "severity": self.severity,
            "title": self.title,
            "message": self.message,
            "action_path": self.action_path,
            "source_name": self.source_name,
            "created_at": self.created_at.isoformat() + "Z",
            "read_at": self.read_at.isoformat() + "Z" if self.read_at else None,
            "unread": self.read_at is None,
        }


class AccountProfile(db.Model):
    __tablename__ = "account_profiles"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    phone = db.Column(db.String(40), nullable=False, default="")
    date_of_birth = db.Column(db.Date)
    preferred_language = db.Column(db.String(40), nullable=False, default="English")
    password_changed_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    user = db.relationship("User", backref=db.backref("account_profile", uselist=False, cascade="all, delete-orphan"))

    def to_dict(self):
        return {
            "phone": self.phone,
            "date_of_birth": self.date_of_birth.isoformat() if self.date_of_birth else None,
            "preferred_language": self.preferred_language,
            "password_changed_at": self.password_changed_at.isoformat() + "Z" if self.password_changed_at else None,
            "updated_at": self.updated_at.isoformat() + "Z",
        }


class AccountSession(db.Model):
    __tablename__ = "account_sessions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token = db.Column(db.String(100), nullable=False, unique=True, index=True)
    device_name = db.Column(db.String(120), nullable=False)
    ip_address = db.Column(db.String(80), nullable=False, default="Unavailable")
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    last_seen_at = db.Column(db.DateTime, nullable=False, default=utc_now, index=True)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    revoked_at = db.Column(db.DateTime, index=True)

    user = db.relationship("User", backref=db.backref("account_sessions", cascade="all, delete-orphan"))

    @property
    def active(self):
        return self.revoked_at is None and self.expires_at > utc_now()

    def to_dict(self, current_token=None):
        return {
            "id": self.id,
            "device_name": self.device_name,
            "ip_address": self.ip_address,
            "created_at": self.created_at.isoformat() + "Z",
            "last_seen_at": self.last_seen_at.isoformat() + "Z",
            "expires_at": self.expires_at.isoformat() + "Z",
            "active": self.active,
            "current": self.token == current_token,
        }


class SecurityEvent(db.Model):
    __tablename__ = "security_events"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = db.Column(db.String(50), nullable=False, index=True)
    description = db.Column(db.String(300), nullable=False)
    result = db.Column(db.String(30), nullable=False, default="success", index=True)
    ip_address = db.Column(db.String(80), nullable=False, default="Unavailable")
    device_name = db.Column(db.String(120), nullable=False, default="Unknown device")
    important = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now, index=True)

    user = db.relationship("User", backref=db.backref("security_events", cascade="all, delete-orphan"))

    def to_dict(self):
        return {
            "id": self.id,
            "event_type": self.event_type,
            "description": self.description,
            "result": self.result,
            "ip_address": self.ip_address,
            "device_name": self.device_name,
            "important": self.important,
            "created_at": self.created_at.isoformat() + "Z",
        }
