"""Explicit local-simulation provenance without changing existing tables."""
from .extensions import db
from .models import utc_now


class SimulatedAccess(db.Model):
    __tablename__ = "simulated_access_events"
    event_id = db.Column(db.Integer, db.ForeignKey("access_events.id"), primary_key=True)
    reason = db.Column(db.String(100), nullable=False)


class ShareScopeSnapshot(db.Model):
    """New grants opt into fixed, reviewed content; old grants never gain scopes."""
    __tablename__ = "share_scope_snapshots"
    grant_id = db.Column(db.Integer, db.ForeignKey("share_grants.id"), primary_key=True)
    payload = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)


class ShareScopeAccessEvent(db.Model):
    __tablename__ = "share_scope_access_events"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    grant_id = db.Column(db.Integer, db.ForeignKey("share_grants.id"), nullable=False, index=True)
    action = db.Column(db.String(30), nullable=False)
    result = db.Column(db.String(30), nullable=False)
    reason = db.Column(db.String(100), nullable=False)
    objects = db.Column(db.JSON, nullable=False, default=list)
    occurred_at = db.Column(db.DateTime, nullable=False, default=utc_now, index=True)
    reviewed_at = db.Column(db.DateTime)
    grant = db.relationship("ShareGrant")

    def to_dict(self):
        return {"id": self.id, "event_kind": "scope", "grant_id": self.grant_id,
                "recipient": self.grant.recipient.to_dict(), "action": self.action,
                "result": self.result, "reason": self.reason, "objects": self.objects,
                "record": {"title": "、".join(item["label"] for item in self.objects)},
                "occurred_at": self.occurred_at.isoformat() + "Z", "source": "mock",
                "location_source": "本人发起的本地接收方模拟，未连接真实医生或定位",
                "unusual": self.result == "blocked",
                "reviewed_at": self.reviewed_at.isoformat() + "Z" if self.reviewed_at else None}
