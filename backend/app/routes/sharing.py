from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from ..extensions import db
from ..models import AccessEvent, AccessReview, HealthRecord, ShareFieldSettings, ShareGrant, ShareGrantRecord, ShareRecipient, utc_now


sharing_bp = Blueprint("sharing", __name__)
SHARE_FIELDS = {"title", "record_type", "record_date", "source_name", "condition", "content"}


def parse_datetime(value, label):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except (TypeError, ValueError):
        raise ValueError(f"Select a valid {label}.") from None


@sharing_bp.get("/recipients")
@login_required
def list_recipients():
    recipients = ShareRecipient.query.order_by(ShareRecipient.full_name.asc()).all()
    return jsonify({"recipients": [recipient.to_dict() for recipient in recipients]})


@sharing_bp.get("/grants")
@login_required
def list_grants():
    grants = ShareGrant.query.filter_by(user_id=current_user.id).order_by(ShareGrant.created_at.desc()).all()
    grants.sort(key=lambda grant: ({"active": 0, "scheduled": 1, "expired": 2, "revoked": 3}[grant.status], -grant.created_at.timestamp()))
    return jsonify({"grants": [grant.to_dict() for grant in grants]})


@sharing_bp.post("/grants")
@login_required
def create_grant():
    data = request.get_json(silent=True) or {}
    recipient = db.session.get(ShareRecipient, data.get("recipient_id")) if type(data.get("recipient_id")) is int else None
    if not recipient or recipient.verification_status != "verified":
        return jsonify({"error": "invalid_recipient", "message": "Select a verified healthcare recipient."}), 400
    record_ids = data.get("record_ids") or []
    if not isinstance(record_ids, list) or not record_ids:
        return jsonify({"error": "records_required", "message": "Select at least one health record to share."}), 400
    if any(type(item) is not int for item in record_ids):
        return jsonify({"message": "Select valid record IDs."}), 400
    fields = data.get("shared_fields", sorted(SHARE_FIELDS))
    if not isinstance(fields, list) or not fields or any(not isinstance(item, str) or item not in SHARE_FIELDS for item in fields):
        return jsonify({"message": "Select at least one supported field."}), 400
    if not isinstance(data.get("allow_download", False), bool):
        return jsonify({"message": "Select a valid download permission."}), 400
    unique_ids = list(dict.fromkeys(record_ids))
    records = HealthRecord.query.filter(HealthRecord.user_id == current_user.id, HealthRecord.id.in_(unique_ids)).all()
    if len(records) != len(unique_ids):
        return jsonify({"error": "invalid_records", "message": "One or more selected records are unavailable."}), 400
    try:
        starts_at = parse_datetime(data.get("starts_at"), "start time")
        expires_at = parse_datetime(data.get("expires_at"), "expiry time")
    except ValueError as error:
        return jsonify({"error": "invalid_time", "message": str(error)}), 400
    now = utc_now()
    if expires_at <= max(now, starts_at):
        return jsonify({"error": "invalid_expiry", "message": "The expiry time must be after the start time and in the future."}), 400
    if expires_at > now + timedelta(days=365):
        return jsonify({"error": "expiry_too_long", "message": "For this first version, access can be granted for up to one year."}), 400

    grant = ShareGrant(
        user_id=current_user.id,
        recipient_id=recipient.id,
        starts_at=starts_at,
        expires_at=expires_at,
        allow_download=bool(data.get("allow_download")),
        purpose=str(data.get("purpose") or "").strip()[:200],
    )
    db.session.add(grant)
    db.session.flush()
    db.session.add(ShareFieldSettings(grant_id=grant.id, fields=list(dict.fromkeys(fields))))
    for record in records:
        db.session.add(ShareGrantRecord(grant_id=grant.id, record_id=record.id))
    db.session.commit()
    return jsonify({"grant": grant.to_dict()}), 201


@sharing_bp.get("/grants/<int:grant_id>")
@login_required
def get_grant(grant_id):
    grant = ShareGrant.query.filter_by(id=grant_id, user_id=current_user.id).first()
    if not grant:
        return jsonify({"error": "not_found", "message": "Sharing permission not found."}), 404
    return jsonify({"grant": grant.to_dict()})


@sharing_bp.patch("/grants/<int:grant_id>/revoke")
@login_required
def revoke_grant(grant_id):
    grant = ShareGrant.query.filter_by(id=grant_id, user_id=current_user.id).first()
    if not grant:
        return jsonify({"error": "not_found", "message": "Sharing permission not found."}), 404
    if grant.status in {"active", "scheduled"}:
        grant.revoked_at = utc_now()
        db.session.commit()
    return jsonify({"grant": grant.to_dict()})


@sharing_bp.get("/access-events")
@login_required
def list_access_events():
    query = AccessEvent.query.filter_by(user_id=current_user.id)
    action = str(request.args.get("action") or "")
    result = str(request.args.get("result") or "")
    if action in {"view", "download"}:
        query = query.filter_by(action=action)
    if result in {"allowed", "blocked"}:
        query = query.filter_by(result=result)
    events = query.order_by(AccessEvent.occurred_at.desc()).limit(100).all()
    return jsonify({"events": [event.to_dict() for event in events]})


@sharing_bp.post("/grants/<int:grant_id>/preview")
@login_required
def preview_grant(grant_id):
    grant = ShareGrant.query.filter_by(id=grant_id, user_id=current_user.id).first()
    if not grant:
        return jsonify({"message": "Sharing permission not found."}), 404
    action = (request.get_json(silent=True) or {}).get("action", "view")
    if action not in {"view", "download"}:
        return jsonify({"message": "Select view or download."}), 400
    if grant.status != "active" or (action == "download" and not grant.allow_download):
        return jsonify({"message": "This action is blocked by the current permission.", "status": grant.status}), 403
    fields = grant.to_dict()["shared_fields"]
    return jsonify({"mode": "owner_preview", "records": [{field: link.record.to_dict()[field] for field in fields} for link in grant.record_links], "message": "Owner-only preview. No recipient request was made or logged. External recipient access is not connected."})


@sharing_bp.patch("/access-events/<int:event_id>/review")
@login_required
def review_access(event_id):
    event = AccessEvent.query.filter_by(id=event_id, user_id=current_user.id).first()
    if not event:
        return jsonify({"message": "Access event not found."}), 404
    if not event.review:
        db.session.add(AccessReview(event_id=event.id))
        db.session.commit()
    return jsonify({"event": event.to_dict()})
