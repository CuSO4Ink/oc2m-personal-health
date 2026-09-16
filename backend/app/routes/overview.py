from datetime import timedelta

from flask import Blueprint, jsonify
from flask_login import current_user, login_required

from ..models import AccessEvent, Appointment, AppointmentSlot, HealthAlert, HealthMeasurement, HealthRecord, HealthReminder, ShareGrant, utc_now
from .insights import METRICS, reading_status


overview_bp = Blueprint("overview", __name__)


@overview_bp.get("")
@login_required
def overview():
    now = utc_now()
    readings = []
    for key, config in METRICS.items():
        latest = HealthMeasurement.query.filter_by(user_id=current_user.id, metric_type=key).order_by(HealthMeasurement.measured_at.desc(), HealthMeasurement.id.desc()).first()
        readings.append({
            "key": key,
            "label": config["label"],
            "reading": latest.to_dict(reading_status(key, latest.value, latest.secondary_value, latest.context)) if latest else None,
            "stale": bool(latest and latest.measured_at < now - timedelta(days=14)),
        })
    record_query = HealthRecord.query.filter_by(user_id=current_user.id)
    alerts = HealthAlert.query.filter_by(user_id=current_user.id, acknowledged_at=None).order_by(HealthAlert.created_at.desc()).all()
    reminders = HealthReminder.query.filter_by(user_id=current_user.id, completed_at=None).order_by(HealthReminder.next_due_at.asc()).all()
    due = [item for item in reminders if item.next_due_at <= now]
    appointments = Appointment.query.join(AppointmentSlot).filter(Appointment.user_id == current_user.id, Appointment.status == "confirmed", AppointmentSlot.starts_at > now).order_by(AppointmentSlot.starts_at.asc()).all()
    grants = ShareGrant.query.filter_by(user_id=current_user.id).all()
    active = [item for item in grants if item.status == "active"]
    expiring = sorted([item for item in active if item.expires_at <= now + timedelta(days=7)], key=lambda item: item.expires_at)
    unusual_query = AccessEvent.query.filter_by(user_id=current_user.id, unusual=True)
    return jsonify({
        "generated_at": now.isoformat() + "Z",
        "readings": readings,
        "records": {"count": record_query.count(), "recent": [item.to_dict() for item in record_query.order_by(HealthRecord.updated_at.desc(), HealthRecord.id.desc()).limit(4).all()]},
        "attention": {"health_alert_count": len(alerts), "alerts": [item.to_dict() for item in alerts[:3]], "due_task_count": len(due), "due_tasks": [item.to_dict() for item in due[:3]]},
        "care": {"appointment_count": len(appointments), "appointments": [item.to_dict() for item in appointments[:3]], "upcoming_tasks": [item.to_dict() for item in reminders if item.next_due_at > now][:3]},
        "sharing": {"active_count": len(active), "expiring_count": len(expiring), "expiring": [item.to_dict() for item in expiring[:3]], "unusual_count": unusual_query.count(), "recent_unusual": [item.to_dict() for item in unusual_query.order_by(AccessEvent.occurred_at.desc()).limit(3).all()]},
        "integration": {"status": "not_connected", "message": "Hospital and device integrations are not connected. Provider and device records currently use demonstration data; manual entries are saved to your account."},
    })
