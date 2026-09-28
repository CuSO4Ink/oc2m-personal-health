"""Append-only application audit for personal actions and labelled simulations."""
from flask_login import current_user

from .extensions import db
from .models import utc_now


class RecordAuditEvent(db.Model):
    __tablename__ = "record_audit_events"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    record_id = db.Column(db.Integer, db.ForeignKey("health_records.id"), index=True)
    action = db.Column(db.String(60), nullable=False)
    actor_name = db.Column(db.String(100), nullable=False)
    source = db.Column(db.String(30), nullable=False, default="personal")
    result = db.Column(db.String(30), nullable=False, default="allowed")
    details = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now, index=True)

    def to_dict(self):
        return {"id": self.id, "record_id": self.record_id, "action": self.action,
                "actor_name": self.actor_name, "source": self.source, "result": self.result,
                "details": self.details, "created_at": self.created_at.isoformat() + "Z"}


def append_audit(user_id, action, record_id=None, details=None, source="personal", actor_name=None, result="allowed"):
    event = RecordAuditEvent(user_id=user_id, record_id=record_id, action=action,
                             actor_name=actor_name or (current_user.full_name if current_user and current_user.is_authenticated else "System"),
                             source=source, result=result, details=details or {})
    db.session.add(event)
    return event
