from datetime import timedelta

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import or_

from ..extensions import db
from ..models import (
    AccessEvent,
    Appointment,
    AppointmentSlot,
    CommunityComment,
    CommunityPost,
    CommunityProfile,
    HealthAlert,
    HealthReminder,
    Notification,
    ShareGrant,
    utc_now,
)


notifications_bp = Blueprint("notifications", __name__)
CATEGORIES = {"health", "care", "sharing", "security", "community", "system"}


def ensure_notification(dedupe_key, **values):
    existing = Notification.query.filter_by(user_id=current_user.id, dedupe_key=dedupe_key).first()
    if not existing:
        db.session.add(Notification(user_id=current_user.id, dedupe_key=dedupe_key, **values))


def sync_current_notifications():
    now = utc_now()
    for alert in HealthAlert.query.filter_by(user_id=current_user.id).all():
        ensure_notification(
            f"health-alert-{alert.id}",
            category="health",
            severity="urgent" if alert.severity == "high" else "warning",
            title=alert.title,
            message=alert.message,
            action_path="/insights",
            source_name=f"Health Insights · rule {alert.rule_version}",
            created_at=alert.created_at,
        )
    overdue = HealthReminder.query.filter(
        HealthReminder.user_id == current_user.id,
        HealthReminder.completed_at.is_(None),
        HealthReminder.next_due_at < now,
    ).all()
    for reminder in overdue:
        ensure_notification(
            f"health-reminder-{reminder.id}",
            category="care",
            severity="warning",
            title=f"Health task due: {reminder.title}",
            message=f"This task was due on {reminder.next_due_at.strftime('%d %b %Y at %H:%M')}. {reminder.schedule_note}.",
            action_path="/services",
            source_name=reminder.source_name,
            created_at=reminder.next_due_at,
        )
    upcoming = Appointment.query.join(AppointmentSlot, Appointment.slot_id == AppointmentSlot.id).filter(
        Appointment.user_id == current_user.id,
        Appointment.status == "confirmed",
        AppointmentSlot.starts_at > now,
        AppointmentSlot.starts_at <= now + timedelta(days=7),
    ).all()
    for appointment in upcoming:
        ensure_notification(
            f"appointment-{appointment.id}",
            category="care",
            severity="info",
            title=f"Upcoming appointment: {appointment.slot.service.name}",
            message=f"Your appointment is confirmed for {appointment.slot.starts_at.strftime('%d %b %Y at %H:%M')} with {appointment.slot.service.facility.name}.",
            action_path="/services",
            source_name=appointment.slot.service.facility.name,
            created_at=appointment.booked_at,
        )
    unusual_events = AccessEvent.query.filter_by(user_id=current_user.id, unusual=True).all()
    for event in unusual_events:
        ensure_notification(
            f"access-event-{event.id}",
            category="security",
            severity="urgent",
            title="Unusual health-record access activity",
            message=f"A {event.action} attempt by {event.grant.recipient.full_name} was {event.result} from {event.location}.",
            action_path="/sharing",
            source_name="Sharing & Privacy",
            created_at=event.occurred_at,
        )
    expiring_grants = ShareGrant.query.filter(
        ShareGrant.user_id == current_user.id,
        ShareGrant.revoked_at.is_(None),
        ShareGrant.expires_at > now,
        ShareGrant.expires_at <= now + timedelta(days=7),
    ).all()
    for grant in expiring_grants:
        ensure_notification(
            f"share-expiry-{grant.id}",
            category="sharing",
            severity="warning",
            title="Sharing permission expires soon",
            message=f"{grant.recipient.full_name}'s access to {len(grant.record_links)} selected records expires on {grant.expires_at.strftime('%d %b %Y at %H:%M')}.",
            action_path="/sharing",
            source_name="Sharing & Privacy",
            created_at=now,
        )
    profile = db.session.get(CommunityProfile, current_user.id)
    if profile and profile.enabled:
        comments = CommunityComment.query.join(CommunityPost).filter(
            CommunityPost.user_id == current_user.id,
            CommunityPost.status == "published",
            CommunityComment.user_id != current_user.id,
            CommunityComment.status == "published",
        ).all()
        for comment in comments:
            author = "An anonymous member" if comment.anonymous else comment.user.full_name
            ensure_notification(
                f"community-comment-{comment.id}",
                category="community",
                severity="info",
                title="New comment on your community post",
                message=f"{author} commented: {comment.body[:180]}",
                action_path="/community",
                source_name=comment.post.circle.name,
                created_at=comment.created_at,
            )
    db.session.commit()


def summary_payload():
    active = Notification.query.filter_by(user_id=current_user.id, archived_at=None)
    unread = active.filter(Notification.read_at.is_(None))
    by_category = {category: unread.filter_by(category=category).count() for category in sorted(CATEGORIES)}
    return {"unread": unread.count(), "total": active.count(), "unread_by_category": by_category}


@notifications_bp.get("")
@login_required
def list_notifications():
    sync_current_notifications()
    query = Notification.query.filter_by(user_id=current_user.id, archived_at=None)
    status = str(request.args.get("status") or "all")
    category = str(request.args.get("category") or "all")
    keyword = str(request.args.get("q") or "").strip()
    if status == "unread":
        query = query.filter(Notification.read_at.is_(None))
    elif status == "read":
        query = query.filter(Notification.read_at.is_not(None))
    elif status != "all":
        return jsonify({"error": "invalid_status", "message": "Select all, unread or read notifications."}), 400
    if category != "all":
        if category not in CATEGORIES:
            return jsonify({"error": "invalid_category", "message": "Select a valid notification category."}), 400
        query = query.filter_by(category=category)
    if keyword:
        term = f"%{keyword}%"
        query = query.filter(or_(Notification.title.ilike(term), Notification.message.ilike(term), Notification.source_name.ilike(term)))
    notifications = query.order_by(Notification.created_at.desc()).limit(100).all()
    return jsonify({"notifications": [item.to_dict() for item in notifications], "summary": summary_payload()})


@notifications_bp.get("/summary")
@login_required
def notification_summary():
    sync_current_notifications()
    return jsonify({"summary": summary_payload()})


@notifications_bp.patch("/<int:notification_id>/read")
@login_required
def set_read_state(notification_id):
    notification = Notification.query.filter_by(id=notification_id, user_id=current_user.id, archived_at=None).first()
    if not notification:
        return jsonify({"error": "not_found", "message": "Notification not found."}), 404
    data = request.get_json(silent=True) or {}
    if not isinstance(data.get("read"), bool):
        return jsonify({"error": "invalid_state", "message": "Choose whether the notification is read."}), 400
    notification.read_at = utc_now() if data["read"] else None
    db.session.commit()
    return jsonify({"notification": notification.to_dict(), "summary": summary_payload()})


@notifications_bp.post("/read-all")
@login_required
def mark_all_read():
    category = str((request.get_json(silent=True) or {}).get("category") or "all")
    query = Notification.query.filter_by(user_id=current_user.id, archived_at=None, read_at=None)
    if category != "all":
        if category not in CATEGORIES:
            return jsonify({"error": "invalid_category", "message": "Select a valid notification category."}), 400
        query = query.filter_by(category=category)
    updated_at = utc_now()
    for notification in query.all():
        notification.read_at = updated_at
    db.session.commit()
    return jsonify({"message": "Notifications marked as read.", "summary": summary_payload()})


@notifications_bp.delete("/<int:notification_id>")
@login_required
def archive_notification(notification_id):
    notification = Notification.query.filter_by(id=notification_id, user_id=current_user.id, archived_at=None).first()
    if not notification:
        return jsonify({"error": "not_found", "message": "Notification not found."}), 404
    notification.archived_at = utc_now()
    db.session.commit()
    return jsonify({"message": "Notification cleared.", "summary": summary_payload()})
