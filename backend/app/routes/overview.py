from datetime import timedelta

from flask import Blueprint, jsonify
from flask_login import current_user, login_required

from ..extensions import db
from ..models import AccessEvent, AccessReview, Appointment, AppointmentSlot, HealthAlert, HealthMeasurement, HealthRecord, HealthReminder, ShareGrant, utc_now
from ..record_models import RecordLifecycle, profile_payload
from ..service_models import ReminderCancellation
from ..insight_models import MeasurementDisposition
from ..sharing_models import ShareScopeAccessEvent
from .records import record_payload, pending_review_records
from .insights import METRICS, active_measurements, serialize_measurement, serialize_alert


overview_bp = Blueprint("overview", __name__)


@overview_bp.get("")
@login_required
def overview():
    now = utc_now()
    readings = []
    for key, config in METRICS.items():
        latest = active_measurements(HealthMeasurement.query.filter_by(user_id=current_user.id, metric_type=key)).order_by(HealthMeasurement.measured_at.desc(), HealthMeasurement.id.desc()).first()
        readings.append({
            "key": key,
            "label": config["label"],
            "reading": serialize_measurement(latest) if latest else None,
            "stale": bool(latest and latest.measured_at < now - timedelta(days=14)),
        })
    record_query = HealthRecord.query.filter_by(user_id=current_user.id).filter(~HealthRecord.id.in_(db.session.query(RecordLifecycle.record_id).filter(RecordLifecycle.archived_at.is_not(None))))
    alerts = HealthAlert.query.filter_by(user_id=current_user.id, acknowledged_at=None).filter(~HealthAlert.measurement_id.in_(db.session.query(MeasurementDisposition.measurement_id))).order_by(HealthAlert.created_at.desc()).all()
    reminders = HealthReminder.query.filter_by(user_id=current_user.id, completed_at=None).filter(~HealthReminder.id.in_(db.session.query(ReminderCancellation.reminder_id))).order_by(HealthReminder.next_due_at.asc()).all()
    due = [item for item in reminders if item.next_due_at <= now]
    appointments = Appointment.query.join(AppointmentSlot).filter(Appointment.user_id == current_user.id, Appointment.status == "confirmed", AppointmentSlot.starts_at > now).order_by(AppointmentSlot.starts_at.asc()).all()
    grants = ShareGrant.query.filter_by(user_id=current_user.id).all()
    active = [item for item in grants if item.status == "active"]
    expiring = sorted([item for item in active if item.expires_at <= now + timedelta(days=7)], key=lambda item: item.expires_at)
    unusual_query = AccessEvent.query.filter_by(user_id=current_user.id, unusual=True)
    scope_unusual = ShareScopeAccessEvent.query.filter_by(user_id=current_user.id, result="blocked")
    pending_records = pending_review_records()
    pending_reviews = [{"record_id": item["record_id"], "title": item["title"], "id": item["extractions"][0]["id"]} for item in pending_records]
    return jsonify({
        "generated_at": now.isoformat() + "Z",
        "readings": readings,
        "profile": profile_payload(current_user.id),
        "records": {"count": record_query.count(), "recent": [record_payload(item) for item in record_query.order_by(HealthRecord.updated_at.desc(), HealthRecord.id.desc()).limit(4).all()], "pending_review_count": len(pending_reviews), "pending_reviews": pending_reviews[:3]},
        "attention": {"health_alert_count": len(alerts), "alerts": [serialize_alert(item) for item in alerts[:3]], "due_task_count": len(due), "due_tasks": [item.to_dict() for item in due[:3]]},
        "care": {"appointment_count": len(appointments), "appointments": [item.to_dict() for item in appointments[:3]], "upcoming_tasks": [item.to_dict() for item in reminders if item.next_due_at > now][:3]},
        "sharing": {"active_count": len(active), "expiring_count": len(expiring), "expiring": [item.to_dict() for item in expiring[:3]], "unusual_count": unusual_query.count() + scope_unusual.count(), "pending_unusual_count": unusual_query.filter(~AccessEvent.id.in_(db.session.query(AccessReview.event_id))).count() + scope_unusual.filter_by(reviewed_at=None).count(), "recent_unusual": [item.to_dict() for item in unusual_query.order_by(AccessEvent.occurred_at.desc()).limit(3).all()]},
        "integration": {"status": "not_connected", "message": "Hospital and device integrations are not connected. Provider and device records currently use demonstration data; manual entries are saved to your account."},
    })
