from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from ..extensions import db
from ..models import HealthAlert, HealthMeasurement, utc_now


insights_bp = Blueprint("insights", __name__)

METRICS = {
    "blood_pressure": {
        "label": "Blood Pressure",
        "unit": "mmHg",
        "min": 50,
        "max": 260,
        "secondary_min": 30,
        "secondary_max": 160,
    },
    "blood_glucose": {"label": "Blood Glucose", "unit": "mmol/L", "min": 1, "max": 35},
    "heart_rate": {"label": "Heart Rate", "unit": "bpm", "min": 25, "max": 240},
}


def parse_datetime(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except (TypeError, ValueError):
        raise ValueError("Enter a valid measurement date and time.") from None


def reading_status(metric_type, value, secondary_value=None, context=""):
    if metric_type == "blood_pressure":
        if value >= 140 or secondary_value >= 90:
            return "high"
        if value >= 130 or secondary_value >= 80:
            return "watch"
    elif metric_type == "blood_glucose":
        if context == "fasting" and value >= 7:
            return "high"
        if context == "fasting" and value >= 5.6:
            return "watch"
        if value >= 11.1:
            return "high"
    elif metric_type == "heart_rate":
        if value < 50 or value > 100:
            return "watch"
    return "in_range"


def alert_for(measurement):
    status = reading_status(measurement.metric_type, measurement.value, measurement.secondary_value, measurement.context)
    if status == "in_range":
        return None
    label = METRICS[measurement.metric_type]["label"]
    value = f"{measurement.value:g}"
    if measurement.secondary_value is not None:
        value += f"/{measurement.secondary_value:g}"
    return HealthAlert(
        user_id=measurement.user_id,
        measurement=measurement,
        severity=status,
        title=f"{label} reading needs attention",
        message=f"A {value} {measurement.unit} reading matched the current {status} threshold. Review the context and seek professional advice if you are concerned.",
        rule_name=f"{measurement.metric_type}_reference_threshold",
        rule_version="1.0",
    )


def validate_measurement(data):
    metric_type = str(data.get("metric_type") or "")
    config = METRICS.get(metric_type)
    if not config:
        return None, "Select a supported health metric."
    try:
        value = float(data.get("value"))
    except (TypeError, ValueError):
        return None, "Enter a numeric reading."
    if not config["min"] <= value <= config["max"]:
        return None, f"Enter a plausible {config['label'].lower()} reading."
    secondary_value = None
    if metric_type == "blood_pressure":
        try:
            secondary_value = float(data.get("secondary_value"))
        except (TypeError, ValueError):
            return None, "Enter both systolic and diastolic values."
        if not config["secondary_min"] <= secondary_value <= config["secondary_max"] or secondary_value >= value:
            return None, "Enter a plausible diastolic value below the systolic value."
    try:
        measured_at = parse_datetime(data.get("measured_at"))
    except ValueError as error:
        return None, str(error)
    if measured_at > utc_now() + timedelta(minutes=5):
        return None, "Measurement time cannot be in the future."
    context = str(data.get("context") or "").strip()
    if metric_type == "blood_glucose" and context not in {"fasting", "after_meal", "random"}:
        return None, "Select when the blood glucose reading was taken."
    return {
        "metric_type": metric_type,
        "value": value,
        "secondary_value": secondary_value,
        "unit": config["unit"],
        "context": context,
        "measured_at": measured_at,
        "source_type": "self",
        "source_name": str(data.get("source_name") or "Manual entry").strip() or "Manual entry",
        "notes": str(data.get("notes") or "").strip()[:300],
    }, None


@insights_bp.get("/metrics")
@login_required
def list_metrics():
    metric_type = str(request.args.get("metric") or "blood_pressure")
    if metric_type not in METRICS:
        return jsonify({"error": "invalid_metric", "message": "Select a supported health metric."}), 400
    try:
        days = int(request.args.get("days", 30))
    except ValueError:
        return jsonify({"error": "invalid_range", "message": "Select a valid time range."}), 400
    if days not in {7, 30, 90, 365}:
        return jsonify({"error": "invalid_range", "message": "Select a valid time range."}), 400

    cutoff = utc_now() - timedelta(days=days)
    readings = HealthMeasurement.query.filter(
        HealthMeasurement.user_id == current_user.id,
        HealthMeasurement.metric_type == metric_type,
        HealthMeasurement.measured_at >= cutoff,
    ).order_by(HealthMeasurement.measured_at.asc()).all()
    serialized = [item.to_dict(reading_status(item.metric_type, item.value, item.secondary_value, item.context)) for item in readings]
    latest = serialized[-1] if serialized else None
    values = [item.value for item in readings]
    data_age_days = (utc_now() - readings[-1].measured_at).days if readings else None
    if len(readings) < 3:
        sufficiency = {"status": "limited", "message": "At least three readings are needed to show a useful pattern."}
    elif data_age_days is not None and data_age_days > 14:
        sufficiency = {"status": "stale", "message": "The latest reading is over 14 days old. Add a newer reading before relying on this trend."}
    else:
        sufficiency = {"status": "sufficient", "message": f"This view is based on {len(readings)} readings from the selected period."}
    return jsonify({
        "metric": {"key": metric_type, **METRICS[metric_type]},
        "readings": serialized,
        "latest": latest,
        "summary": {
            "count": len(readings),
            "average": round(sum(values) / len(values), 1) if values else None,
            "minimum": min(values) if values else None,
            "maximum": max(values) if values else None,
        },
        "data_sufficiency": sufficiency,
        "generated_at": utc_now().isoformat() + "Z",
    })


@insights_bp.post("/metrics")
@login_required
def create_metric():
    values, error = validate_measurement(request.get_json(silent=True) or {})
    if error:
        return jsonify({"error": "invalid_measurement", "message": error}), 400
    measurement = HealthMeasurement(user_id=current_user.id, **values)
    db.session.add(measurement)
    alert = alert_for(measurement)
    if alert:
        db.session.add(alert)
    db.session.commit()
    status = reading_status(measurement.metric_type, measurement.value, measurement.secondary_value, measurement.context)
    return jsonify({"measurement": measurement.to_dict(status), "alert": alert.to_dict() if alert else None}), 201


@insights_bp.get("/alerts")
@login_required
def list_alerts():
    alerts = HealthAlert.query.filter_by(user_id=current_user.id, acknowledged_at=None).order_by(HealthAlert.created_at.desc()).limit(10).all()
    return jsonify({"alerts": [alert.to_dict() for alert in alerts]})


@insights_bp.patch("/alerts/<int:alert_id>/acknowledge")
@login_required
def acknowledge_alert(alert_id):
    alert = HealthAlert.query.filter_by(id=alert_id, user_id=current_user.id).first()
    if not alert:
        return jsonify({"error": "not_found", "message": "Health alert not found."}), 404
    alert.acknowledged_at = utc_now()
    db.session.commit()
    return jsonify({"alert": alert.to_dict()})
