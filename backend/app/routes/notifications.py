from datetime import timedelta

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import or_

from ..extensions import db
from ..community_models import CommunityIdentity, CommunityConnection, CommunityMessage
from ..insight_models import MeasurementDisposition
from ..sharing_models import ShareScopeAccessEvent
from ..models import (
    AccessEvent,
    Appointment,
    AppointmentSlot,
    CommunityComment,
    CommunityBlock,
    CommunityPost,
    CommunityProfile,
    HealthAlert,
    HealthReminder,
    Notification,
    NotificationPreference,
    NotificationResolution,
    SecurityEvent,
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
            action_path=f"/insights?metric={alert.measurement.metric_type}&alert={alert.id}",
            source_name=f"Health Insights · rule {alert.rule_version}",
            created_at=alert.created_at,
        )
    overdue = HealthReminder.query.filter(
        HealthReminder.user_id == current_user.id,
        HealthReminder.completed_at.is_(None),
        HealthReminder.next_due_at < now,
    ).all()
    for reminder in overdue:
        if reminder.status == "cancelled":
            continue
        ensure_notification(
            f"health-reminder-{reminder.id}",
            category="care",
            severity="warning",
            title=f"Health task due: {reminder.title}",
            message=f"This task was due on {reminder.next_due_at.strftime('%d %b %Y at %H:%M UTC')}. {reminder.schedule_note}.",
            action_path=f"/services?tab=reminders&reminder={reminder.id}",
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
            message=f"Your appointment is confirmed for {appointment.slot.starts_at.strftime('%d %b %Y at %H:%M UTC')} with {appointment.slot.service.facility.name}.",
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
    for event in ShareScopeAccessEvent.query.filter_by(user_id=current_user.id, result="blocked").all():
        ensure_notification(
            f"scope-access-event-{event.id}", category="security", severity="warning",
            title="一次模拟共享访问已被阻止", message=f"本地模拟接收方 {event.grant.recipient.full_name} 的访问因 {event.reason} 被阻止。可在访问记录中核对。",
            action_path="/sharing", source_name="共享与访问（本地模拟）", created_at=event.occurred_at,
        )
    security_events = SecurityEvent.query.filter_by(user_id=current_user.id, important=True).all()
    for event in security_events:
        ensure_notification(
            f"account-security-event-{event.id}",
            category="security",
            severity="urgent" if event.result == "blocked" else "warning",
            title="Account security activity",
            message=event.description,
            action_path="/account",
            source_name="Account & Security",
            created_at=event.created_at,
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
            message=f"{grant.recipient.full_name}'s access to {len(grant.record_links)} selected records expires on {grant.expires_at.strftime('%d %b %Y at %H:%M UTC')}.",
            action_path="/sharing",
            source_name="Sharing & Privacy",
            created_at=now,
        )
    profile = db.session.get(CommunityProfile, current_user.id)
    identity = db.session.get(CommunityIdentity, current_user.id)
    community_since = identity.notification_since if identity else now
    if profile and profile.enabled:
        comments = CommunityComment.query.join(CommunityPost).filter(
            CommunityPost.user_id == current_user.id,
            CommunityPost.status == "published",
            CommunityComment.user_id != current_user.id,
            CommunityComment.status == "published",
            CommunityComment.created_at > community_since,
        ).all()
        blocks = CommunityBlock.query.filter(or_(CommunityBlock.user_id == current_user.id, CommunityBlock.target_id == current_user.id)).all()
        blocked = {block.target_id if block.user_id == current_user.id else block.user_id for block in blocks}
        for comment in comments:
            if comment.user_id in blocked:
                existing = Notification.query.filter_by(user_id=current_user.id, dedupe_key=f"community-comment-{comment.id}").first()
                if existing:
                    existing.archived_at = now
                continue
            author_identity = db.session.get(CommunityIdentity, comment.user_id)
            author = "An anonymous member" if comment.anonymous else author_identity.nickname if author_identity else "A community member"
            ensure_notification(
                f"community-comment-{comment.id}",
                category="community",
                severity="info",
                title="New comment on your community post",
                message=f"{author} commented: {comment.body[:180]}",
                action_path=f"/community?tab=feed&post={comment.post_id}",
                source_name=comment.post.circle.name,
                created_at=comment.created_at,
            )
        connections = CommunityConnection.query.filter(or_(CommunityConnection.first_id == current_user.id, CommunityConnection.second_id == current_user.id)).all()
        for connection in connections:
            other_id = connection.second_id if connection.first_id == current_user.id else connection.first_id
            other_profile = db.session.get(CommunityProfile, other_id)
            if other_id in blocked or not other_profile or not other_profile.enabled:
                continue
            other_identity = db.session.get(CommunityIdentity, other_id)
            nickname = other_identity.nickname if other_identity else "A community member"
            if connection.status == "pending" and connection.requester_id != current_user.id and connection.updated_at > community_since:
                ensure_notification(f"community-connection-{connection.id}-request-{connection.updated_at.isoformat()}", category="community", severity="info", title="Friend request", message=f"{nickname} would like to connect. You choose whether to accept.", action_path="/community?tab=connections", source_name="Community friends", created_at=connection.updated_at)
            if connection.status != "accepted":
                continue
            if connection.requester_id == current_user.id and connection.accepted_at and connection.accepted_at > community_since:
                ensure_notification(f"community-connection-{connection.id}-accepted-{connection.accepted_at.isoformat()}", category="community", severity="info", title="Friend request accepted", message=f"{nickname} accepted your request. You can now exchange private messages.", action_path=f"/community?tab=connections&conversation={connection.id}", source_name="Community friends", created_at=connection.accepted_at)
            for item in CommunityMessage.query.filter(CommunityMessage.connection_id == connection.id, CommunityMessage.sender_id != current_user.id, CommunityMessage.read_at.is_(None), CommunityMessage.created_at > community_since).all():
                ensure_notification(f"community-message-{connection.id}-{item.id}", category="community", severity="info", title="New private message", message=f"{nickname} sent you a private message.", action_path=f"/community?tab=connections&conversation={connection.id}", source_name="Community messages", created_at=item.created_at)
    blocks = CommunityBlock.query.filter(or_(CommunityBlock.user_id == current_user.id, CommunityBlock.target_id == current_user.id)).all()
    blocked = {block.target_id if block.user_id == current_user.id else block.user_id for block in blocks}
    for notification in Notification.query.filter_by(user_id=current_user.id, category="community", archived_at=None).all():
        if not profile or not profile.enabled or notification.created_at <= community_since:
            notification.archived_at = now
            notification.read_at = notification.read_at or now
            continue
        if notification.dedupe_key.startswith("community-comment-"):
            try:
                comment = db.session.get(CommunityComment, int(notification.dedupe_key.rsplit("-", 1)[-1]))
            except ValueError:
                continue
            if not comment or comment.status != "published" or comment.post.status != "published" or comment.user_id in blocked:
                notification.archived_at = now
        elif notification.dedupe_key.startswith(("community-connection-", "community-message-")):
            parts = notification.dedupe_key.split("-")
            try:
                connection = db.session.get(CommunityConnection, int(parts[2]))
            except (ValueError, IndexError):
                connection = None
            other = (connection.second_id if connection.first_id == current_user.id else connection.first_id) if connection else None
            if not connection or other in blocked or connection.status not in {"pending", "accepted"}:
                notification.archived_at = now
            elif parts[1] == "connection" and parts[3] == "request" and connection.status != "pending":
                notification.archived_at = now
            elif parts[1] == "message":
                item = db.session.get(CommunityMessage, int(parts[3]))
                if not item or item.read_at:
                    notification.read_at = notification.read_at or now
    for notification in Notification.query.filter_by(user_id=current_user.id).all():
        key = notification.dedupe_key
        resolved = False
        for prefix, model, predicate in [
            ("health-alert-", HealthAlert, lambda item: bool(item.acknowledged_at) or db.session.get(MeasurementDisposition, item.measurement_id) is not None),
            ("health-reminder-", HealthReminder, lambda item: item.status in {"completed", "cancelled"}),
            ("appointment-", Appointment, lambda item: item.status != "confirmed" or item.slot.starts_at <= now),
            ("share-expiry-", ShareGrant, lambda item: item.status in {"expired", "revoked"}),
            ("access-event-", AccessEvent, lambda item: bool(item.review)),
            ("scope-access-event-", ShareScopeAccessEvent, lambda item: bool(item.reviewed_at)),
        ]:
            if key.startswith(prefix):
                try:
                    item = db.session.get(model, int(key[len(prefix):]))
                    resolved = bool(item and predicate(item))
                except ValueError:
                    pass
                break
        if resolved and not notification.resolution:
            db.session.add(NotificationResolution(notification_id=notification.id))
    db.session.commit()


def summary_payload():
    active = Notification.query.filter_by(user_id=current_user.id, archived_at=None)
    profile = db.session.get(CommunityProfile, current_user.id)
    if not profile or not profile.enabled:
        active = active.filter(Notification.category != "community")
    unread = active.filter(Notification.read_at.is_(None))
    preference = db.session.get(NotificationPreference, current_user.id)
    muted = preference.muted_categories if preference else []
    unread = unread.filter(Notification.category.notin_(muted), Notification.id.notin_(db.session.query(NotificationResolution.notification_id)))
    by_category = {category: unread.filter_by(category=category).count() for category in sorted(CATEGORIES)}
    return {"unread": unread.count(), "total": active.count(), "unread_by_category": by_category, "muted_categories": muted}


@notifications_bp.put("/preferences")
@login_required
def update_preferences():
    muted = (request.get_json(silent=True) or {}).get("muted_categories")
    if not isinstance(muted, list) or any(not isinstance(item, str) or item not in {"care", "sharing", "community"} for item in muted):
        return jsonify({"message": "Health, security and system notices cannot be muted."}), 400
    preference = db.session.get(NotificationPreference, current_user.id)
    if not preference:
        preference = NotificationPreference(user_id=current_user.id)
        db.session.add(preference)
    preference.muted_categories = sorted(set(muted))
    db.session.commit()
    return jsonify({"summary": summary_payload()})


@notifications_bp.get("")
@login_required
def list_notifications():
    sync_current_notifications()
    try:
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 20))
        if page < 1 or page_size < 1 or page_size > 100:
            raise ValueError()
    except (TypeError, ValueError):
        return jsonify({"message": "Use a positive page and a page size between 1 and 100."}), 400
    query = Notification.query.filter_by(user_id=current_user.id, archived_at=None)
    status = str(request.args.get("status") or "all")
    category = str(request.args.get("category") or "all")
    keyword = str(request.args.get("q") or "").strip()
    if status == "unread":
        query = query.filter(Notification.read_at.is_(None))
    elif status == "read":
        query = query.filter(Notification.read_at.is_not(None))
    elif status == "resolved":
        query = query.filter(Notification.id.in_(db.session.query(NotificationResolution.notification_id)))
    elif status != "all":
        return jsonify({"error": "invalid_status", "message": "Select all, unread or read notifications."}), 400
    if category != "all":
        if category not in CATEGORIES:
            return jsonify({"error": "invalid_category", "message": "Select a valid notification category."}), 400
        query = query.filter_by(category=category)
    if keyword:
        term = f"%{keyword}%"
        query = query.filter(or_(Notification.title.ilike(term), Notification.message.ilike(term), Notification.source_name.ilike(term)))
    total = query.count()
    page = min(page, max(1, (total + page_size - 1) // page_size))
    notifications = query.order_by(Notification.created_at.desc(), Notification.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return jsonify({"notifications": [item.to_dict() for item in notifications], "summary": summary_payload(),
                    "total": total, "page": page, "page_size": page_size})


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
