from datetime import date, datetime, timedelta, timezone
from io import BytesIO
import json

from flask import Blueprint, jsonify, request, Response, current_app, send_file
from flask_login import current_user, login_required

from ..extensions import db
from ..models import AccessEvent, AccessReview, HealthRecord, HealthMeasurement, ShareFieldSettings, ShareGrant, ShareGrantRecord, ShareRecipient, utc_now
from ..record_models import profile_payload, record_privacy_payload
from ..record_audit import append_audit, RecordAuditEvent
from ..sharing_models import SimulatedAccess, ShareScopeSnapshot, ShareScopeAccessEvent
from ..sharing_scope import build_scope, digest, integer_ids, measurement_visible, visible_scope, permitted_attachment, scope_objects

from ..sample_catalog import with_record_display

sharing_bp = Blueprint("sharing", __name__)
SHARE_FIELDS = {"title", "record_type", "record_date", "source_name", "condition", "content"}
DEFAULT_FIELDS = ["title", "record_type", "record_date", "source_name"]


def parse_datetime(value, label):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed
    except (TypeError, ValueError):
        raise ValueError(f"Select a valid {label}.") from None


def project_records(records, fields):
    """Every read rechecks privacy; a grant never bypasses a later lock/archive."""
    projected, excluded = [], []
    for record in records:
        privacy = record_privacy_payload(record.id)
        if privacy["sensitive"] or privacy["archived"]:
            excluded.append(record.id)
            continue
        allowed = SHARE_FIELDS.intersection(fields) - set(privacy["sensitive_fields"])
        if not allowed:
            excluded.append(record.id)
            continue
        values = record.to_dict()
        projected.append(with_record_display(record, {field: values[field] for field in sorted(allowed)}))
    return projected, excluded


def permission_result(grant, action, recipient_id=None):
    if recipient_id is not None and recipient_id != grant.recipient_id:
        return None, "recipient_mismatch"
    if grant.status != "active":
        return None, grant.status
    if action == "download" and not grant.allow_download:
        return None, "download_not_allowed"
    saved = db.session.get(ShareScopeSnapshot, grant.id)
    if saved:
        result = visible_scope(saved.payload, grant.user_id)
        if not any(result[key] for key in ("records", "attachments", "profile", "measurements")):
            return None, "scope_private_or_archived"
        return result, "allowed"
    records, excluded = project_records([link.record for link in grant.record_links], grant.to_dict()["shared_fields"])
    if not records:
        return None, "scope_private_or_archived"
    return {"records": records, "excluded_count": len(excluded), "attachments_included": False}, "allowed"


def owned_grant(grant_id):
    return ShareGrant.query.filter_by(id=grant_id, user_id=current_user.id).first()


def validate_grant(data):
    recipient = db.session.get(ShareRecipient, data.get("recipient_id")) if type(data.get("recipient_id")) is int else None
    if not recipient or recipient.verification_status != "verified":
        raise ValueError("Select a recipient from the demonstration directory.")
    ids = integer_ids(data, "record_ids")
    fields = data.get("shared_fields", DEFAULT_FIELDS)
    if not isinstance(fields, list) or any(not isinstance(item, str) or item not in SHARE_FIELDS for item in fields):
        raise ValueError("请选择支持的档案文字字段。")
    if type(data.get("allow_download", False)) is not bool:
        raise ValueError("Select a valid download permission.")
    records = HealthRecord.query.filter(HealthRecord.user_id == current_user.id, HealthRecord.id.in_(set(ids))).order_by(HealthRecord.id).all()
    if len(records) != len(set(ids)):
        raise ValueError("One or more selected records are unavailable.")
    scope = build_scope(current_user.id, data, records, fields)
    starts_at = parse_datetime(data.get("starts_at"), "start time")
    expires_at = parse_datetime(data.get("expires_at"), "expiry time")
    if expires_at <= max(utc_now(), starts_at) or expires_at > utc_now() + timedelta(days=365):
        raise ValueError("Expiry must be after the start time, in the future, and within one year.")
    return recipient, records, list(dict.fromkeys(fields)), starts_at, expires_at, scope


def grant_payload(grant):
    result = grant.to_dict()
    saved = db.session.get(ShareScopeSnapshot, grant.id)
    result.update({"scope_mode": "fixed_snapshot" if saved else "legacy_record_fields", "scope_summary": scope_objects(saved.payload) if saved else [],
                   "mode": "demonstration_directory"})
    return result


@sharing_bp.get("/scope-options")
@login_required
def scope_options():
    """Owner-only selection catalogue; no OCR text or report evidence in sharing payloads."""
    try:
        first = date.fromisoformat(request.args.get("from", (utc_now() - timedelta(days=30)).date().isoformat()))
        last = date.fromisoformat(request.args.get("to", utc_now().date().isoformat()))
        if last < first:
            raise ValueError()
    except ValueError:
        return jsonify({"message": "请选择有效的指标日期范围。"}), 400
    query = HealthMeasurement.query.filter(HealthMeasurement.user_id == current_user.id,
        HealthMeasurement.measured_at >= datetime.combine(first, datetime.min.time()),
        HealthMeasurement.measured_at < datetime.combine(last + timedelta(days=1), datetime.min.time()))
    rows = query.order_by(HealthMeasurement.measured_at.desc(), HealthMeasurement.id.desc()).limit(501).all()
    allowed = {"id", "metric_type", "value", "secondary_value", "unit", "context", "measured_at"}
    return jsonify({"profile": profile_payload(current_user.id),
        "measurements": [{key: value for key, value in item.to_dict().items() if key in allowed} for item in rows[:500] if measurement_visible(item, current_user.id)],
        "truncated": len(rows) > 500, "measurement_period": {"from": first.isoformat(), "to": last.isoformat(), "timezone": "UTC"}})


@sharing_bp.get("/recipients")
@login_required
def list_recipients():
    return jsonify({"recipients": [item.to_dict() for item in ShareRecipient.query.order_by(ShareRecipient.full_name).all()], "mode": "demonstration_directory"})


@sharing_bp.get("/grants")
@login_required
def list_grants():
    grants = ShareGrant.query.filter_by(user_id=current_user.id).order_by(ShareGrant.created_at.desc()).all()
    grants.sort(key=lambda item: ({"active": 0, "scheduled": 1, "expired": 2, "revoked": 3}[item.status], -item.created_at.timestamp()))
    return jsonify({"grants": [grant_payload(item) for item in grants]})


@sharing_bp.post("/grants/draft-preview")
@login_required
def preview_draft():
    try:
        *_, scope = validate_grant(request.get_json(silent=True) or {})
    except ValueError as error:
        return jsonify({"message": str(error)}), 400
    return jsonify({**visible_scope(scope, current_user.id), "preview_token": digest(scope), "mode": "owner_preview",
                    "message": "这是所选资料的实际内容。确认后固定本次范围与版本，后续新增内容不会自动开放。"})


@sharing_bp.post("/grants")
@login_required
def create_grant():
    data = request.get_json(silent=True) or {}
    try:
        recipient, records, fields, starts_at, expires_at, scope = validate_grant(data)
    except ValueError as error:
        return jsonify({"message": str(error)}), 400
    if data.get("preview_token") and data["preview_token"] != digest(scope):
        return jsonify({"message": "资料在预览后发生变化，请重新预览再授权。"}), 409
    grant = persist_grant(data, (recipient, records, fields, starts_at, expires_at, scope))
    db.session.commit()
    return jsonify({"grant": grant_payload(grant)}), 201


def persist_grant(data, validated):
    """Stage an already-reviewed grant inside the caller's transaction."""
    recipient, records, fields, starts_at, expires_at, scope = validated
    grant = ShareGrant(user_id=current_user.id, recipient_id=recipient.id, starts_at=starts_at, expires_at=expires_at,
                       allow_download=data.get("allow_download", False), purpose=str(data.get("purpose") or "").strip()[:200])
    db.session.add(grant)
    db.session.flush()
    db.session.add(ShareFieldSettings(grant_id=grant.id, fields=fields))
    db.session.add(ShareScopeSnapshot(grant_id=grant.id, payload=scope))
    for record in records:
        db.session.add(ShareGrantRecord(grant_id=grant.id, record_id=record.id))
        append_audit(current_user.id, "grant_created", record.id, {"grant_id": grant.id, "fields": fields})
    append_audit(current_user.id, "share_scope_created", details={"grant_id": grant.id, "objects": scope_objects(scope), "scope_mode": "fixed_snapshot"})
    return grant


@sharing_bp.get("/grants/<int:grant_id>")
@login_required
def get_grant(grant_id):
    grant = owned_grant(grant_id)
    if not grant:
        return jsonify({"message": "Sharing permission not found."}), 404
    return jsonify({"grant": grant_payload(grant)})


@sharing_bp.patch("/grants/<int:grant_id>/revoke")
@login_required
def revoke_grant(grant_id):
    grant = owned_grant(grant_id)
    if not grant:
        return jsonify({"message": "Sharing permission not found."}), 404
    if grant.status in {"active", "scheduled"}:
        grant.revoked_at = utc_now()
        append_audit(current_user.id, "grant_revoked", details={"grant_id": grant.id})
        db.session.commit()
    return jsonify({"grant": grant_payload(grant)})


@sharing_bp.post("/grants/<int:grant_id>/preview")
@sharing_bp.post("/grants/<int:grant_id>/simulate-access")
@login_required
def access_grant(grant_id):
    grant = owned_grant(grant_id)
    if not grant:
        return jsonify({"message": "Sharing permission not found."}), 404
    data = request.get_json(silent=True) or {}
    action = data.get("action", "view")
    if action not in {"view", "download"}:
        return jsonify({"message": "Select view or download. Editing is never permitted."}), 400
    simulation = request.path.endswith("simulate-access")
    if simulation and not current_app.config.get("DEMO_FEATURES_ENABLED", True):
        return jsonify({"error": "not_connected", "message": "Recipient simulation is disabled. External recipient access is not connected."}), 503
    result, reason = permission_result(grant, action, data.get("recipient_id") if simulation else None)
    scope = db.session.get(ShareScopeSnapshot, grant.id)
    if simulation:
        for link in grant.record_links:
            # A record excluded by current privacy is itself a denied access attempt.
            visible, _ = project_records([link.record], grant.to_dict()["shared_fields"])
            allowed = bool(result and visible)
            event = AccessEvent(user_id=current_user.id, grant_id=grant.id, record_id=link.record_id,
                                action=action, result="allowed" if allowed else "blocked",
                                location="Local simulation · no geographic location", unusual=not allowed)
            db.session.add(event)
            db.session.flush()
            db.session.add(SimulatedAccess(event_id=event.id, reason=reason if allowed or not result else "scope_private_or_archived"))
        if scope and any(scope.payload[key] for key in ("attachments", "profile", "measurements")):
            db.session.add(ShareScopeAccessEvent(user_id=current_user.id, grant_id=grant.id, action=action,
                result="allowed" if result else "blocked", reason=reason,
                objects=scope_objects({key: scope.payload[key] for key in ("attachments", "profile", "measurements")})))
        append_audit(current_user.id, "simulated_recipient_access", details={"grant_id": grant.id, "action": action, "reason": reason},
                     source="mock", actor_name="Owner-run recipient simulation", result="allowed" if result else "blocked")
        db.session.commit()
    else:
        append_audit(current_user.id, "share_owner_preview", details={"grant_id": grant.id, "action": action, "reason": reason}, result="allowed" if result else "blocked")
        db.session.commit()
    if not result:
        return jsonify({"message": "This action is blocked by the current permission.", "reason": reason,
                        "mode": "mock" if simulation else "owner_preview"}), 403
    payload = {**result, "mode": "mock" if simulation else "owner_preview",
               "message": "Local simulation only; no doctor was contacted." if simulation else "Owner-only preview. No recipient request was made or logged."}
    for attachment in payload.get("attachments", []):
        mode = "simulation" if simulation else "owner"
        attachment["preview_url"] = f"/api/sharing/grants/{grant.id}/attachments/{attachment['id']}?mode={mode}"
        attachment["download_url"] = f"/api/sharing/grants/{grant.id}/attachments/{attachment['id']}?mode={mode}&download=1" if grant.allow_download else None
    if simulation and action == "download":
        return Response(json.dumps(payload, ensure_ascii=False, indent=2), mimetype="application/json",
                        headers={"Content-Disposition": 'attachment; filename="permitted-health-fields.json"', "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})
    response = jsonify(payload)
    response.headers["Cache-Control"] = "private, no-store"
    return response


@sharing_bp.get("/grants/<int:grant_id>/attachments/<int:attachment_id>")
@login_required
def shared_attachment(grant_id, attachment_id):
    grant = owned_grant(grant_id)
    if not grant:
        return jsonify({"message": "找不到共享授权。"}), 404
    mode = request.args.get("mode", "owner")
    if mode not in {"owner", "simulation"}:
        return jsonify({"message": "请选择本人预览或本地接收方模拟。"}), 400
    simulation = mode == "simulation"
    if simulation and not current_app.config.get("DEMO_FEATURES_ENABLED", True):
        return jsonify({"error": "not_connected", "message": "此环境未启用模拟接收方，未连接真实医生。"}), 503
    recipient_id = request.args.get("recipient_id")
    if recipient_id is not None:
        try:
            recipient_id = int(recipient_id)
        except ValueError:
            return jsonify({"message": "接收方编号无效。"}), 400
    action = "download" if request.args.get("download") == "1" else "view"
    result, reason = permission_result(grant, action, recipient_id)
    snapshot = db.session.get(ShareScopeSnapshot, grant.id)
    saved = next((item for item in snapshot.payload["attachments"] if item["id"] == attachment_id), None) if snapshot else None
    attachment = None
    if result and not saved:
        reason = "attachment_not_granted"
    elif result:
        attachment, reason = permitted_attachment(saved, current_user.id)
    allowed = attachment is not None
    details = {"grant_id": grant.id, "attachment_id": attachment_id, "action": action, "reason": reason}
    if simulation:
        db.session.add(ShareScopeAccessEvent(user_id=current_user.id, grant_id=grant.id, action=action,
            result="allowed" if allowed else "blocked", reason=reason,
            objects=[{"kind": "attachment", "id": attachment_id, "label": saved["filename"] if saved else "未授权文件"}]))
    append_audit(current_user.id, "shared_file_access" if simulation else "shared_file_owner_preview",
        saved["record_id"] if saved else None, details, source="mock" if simulation else "personal",
        actor_name="Owner-run recipient simulation" if simulation else None, result="allowed" if allowed else "blocked")
    db.session.commit()
    if not allowed:
        return jsonify({"message": "当前授权不允许访问该原文件。", "reason": reason, "mode": "mock" if simulation else "owner_preview"}), 403
    response = send_file(BytesIO(attachment.data), mimetype=attachment.content_type, download_name=attachment.filename,
        as_attachment=action == "download", max_age=0)
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def paging():
    try:
        page, size = int(request.args.get("page", 1)), int(request.args.get("page_size", 20))
        if page < 1 or not 1 <= size <= 100:
            raise ValueError()
        return page, size
    except ValueError:
        raise ValueError("Select a positive page and a page size between 1 and 100.") from None


@sharing_bp.get("/access-events")
@login_required
def list_access_events():
    try:
        page, size = paging()
    except ValueError as error:
        return jsonify({"message": str(error)}), 400
    query = AccessEvent.query.filter_by(user_id=current_user.id)
    scopes = ShareScopeAccessEvent.query.filter_by(user_id=current_user.id)
    for field, options in [("action", {"view", "download"}), ("result", {"allowed", "blocked"})]:
        value = request.args.get(field)
        if value in options:
            query = query.filter(getattr(AccessEvent, field) == value)
            scopes = scopes.filter(getattr(ShareScopeAccessEvent, field) == value)
    review = request.args.get("review")
    if review == "pending":
        query = query.filter(~AccessEvent.review.has())
        scopes = scopes.filter(ShareScopeAccessEvent.reviewed_at.is_(None))
    elif review == "reviewed":
        query = query.filter(AccessEvent.review.has())
        scopes = scopes.filter(ShareScopeAccessEvent.reviewed_at.isnot(None))
    total = query.count() + scopes.count()
    events = query.order_by(AccessEvent.occurred_at.desc(), AccessEvent.id.desc()).limit(page * size).all()
    serialized = []
    for item in events:
        value = item.to_dict()
        mock = db.session.get(SimulatedAccess, item.id)
        value.update({"event_kind": "record", "source": "mock" if mock else "demo_history", "reason": mock.reason if mock else None})
        if mock:
            value["location_source"] = "Owner-run local simulation; no real recipient or location verified"
        serialized.append(value)
    serialized.extend(item.to_dict() for item in scopes.order_by(ShareScopeAccessEvent.occurred_at.desc(), ShareScopeAccessEvent.id.desc()).limit(page * size).all())
    serialized.sort(key=lambda item: (item["occurred_at"], item["event_kind"], item["id"]), reverse=True)
    return jsonify({"events": serialized[(page - 1) * size:page * size], "total": total, "page": page, "page_size": size})


@sharing_bp.get("/audit-events")
@login_required
def list_audit_events():
    try:
        page, size = paging()
    except ValueError as error:
        return jsonify({"message": str(error)}), 400
    query = RecordAuditEvent.query.filter_by(user_id=current_user.id)
    if request.args.get("record_id", "").isdigit():
        query = query.filter_by(record_id=int(request.args["record_id"]))
    return jsonify({"events": [item.to_dict() for item in query.order_by(RecordAuditEvent.created_at.desc(), RecordAuditEvent.id.desc()).offset((page - 1) * size).limit(size).all()], "total": query.count(), "page": page, "page_size": size})


@sharing_bp.patch("/access-events/<int:event_id>/review")
@login_required
def review_access(event_id):
    event = AccessEvent.query.filter_by(id=event_id, user_id=current_user.id).first()
    if not event:
        return jsonify({"message": "Access event not found."}), 404
    if not event.review:
        db.session.add(AccessReview(event_id=event.id))
        append_audit(current_user.id, "access_reviewed", details={"event_id": event.id})
        db.session.commit()
    return jsonify({"event": event.to_dict()})


@sharing_bp.patch("/scope-events/<int:event_id>/review")
@login_required
def review_scope_event(event_id):
    event = ShareScopeAccessEvent.query.filter_by(id=event_id, user_id=current_user.id).first()
    if not event:
        return jsonify({"message": "找不到访问记录。"}), 404
    if not event.reviewed_at:
        event.reviewed_at = utc_now()
        append_audit(current_user.id, "access_reviewed", details={"scope_event_id": event.id})
        db.session.commit()
    return jsonify({"event": event.to_dict()})
