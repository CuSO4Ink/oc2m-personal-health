"""Additive community tables; account identifiers never form public identities."""
import secrets

from .extensions import db
from .models import utc_now


class CommunityIdentity(db.Model):
    __tablename__ = "community_identities"
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    public_id = db.Column(db.String(40), unique=True, nullable=False, default=lambda: secrets.token_urlsafe(18))
    nickname = db.Column(db.String(40), nullable=False, default=lambda: "Member " + secrets.token_hex(3))
    discoverable = db.Column(db.Boolean, nullable=False, default=False)
    invite_code = db.Column(db.String(40), unique=True, nullable=False, default=lambda: secrets.token_urlsafe(18))
    notification_since = db.Column(db.DateTime, nullable=False, default=utc_now)


class CommunityConnection(db.Model):
    __tablename__ = "community_connections"
    __table_args__ = (db.UniqueConstraint("first_id", "second_id", name="uq_community_connection_pair"),)
    id = db.Column(db.Integer, primary_key=True)
    first_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    second_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    requester_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    accepted_at = db.Column(db.DateTime)


class CommunityMessage(db.Model):
    __tablename__ = "community_messages"
    id = db.Column(db.Integer, primary_key=True)
    connection_id = db.Column(db.Integer, db.ForeignKey("community_connections.id"), nullable=False, index=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    body = db.Column(db.String(2000), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    read_at = db.Column(db.DateTime)
    connection = db.relationship("CommunityConnection")


class CommunityMessageReport(db.Model):
    __tablename__ = "community_message_reports"
    __table_args__ = (db.UniqueConstraint("reporter_id", "message_id"),)
    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    message_id = db.Column(db.Integer, db.ForeignKey("community_messages.id"), nullable=False)
    reason = db.Column(db.String(60), nullable=False)
    details = db.Column(db.String(500), nullable=False, default="")
    status = db.Column(db.String(30), nullable=False, default="submitted")
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)


class CommunityMessageDelivery(db.Model):
    __tablename__ = "community_message_deliveries"
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    client_nonce = db.Column(db.String(80), primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey("community_messages.id"), nullable=False, unique=True)


class CommunityReportReview(db.Model):
    __tablename__ = "community_report_reviews"
    __table_args__ = (db.UniqueConstraint("reporter_id", "target_type", "report_id"),)
    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    target_type = db.Column(db.String(20), nullable=False)
    report_id = db.Column(db.Integer, nullable=False)
    stage = db.Column(db.String(30), nullable=False, default="in_review")
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now)
