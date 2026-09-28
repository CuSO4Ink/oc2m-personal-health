from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from ..extensions import db
from ..extraction_models import measurement_source_payload
from ..models import AccountProfile, HealthAlert, HealthMeasurement, utc_now
from ..insight_models import MeasurementContext, MeasurementDisposition
from ..record_models import profile_payload
from ..record_audit import append_audit
from ..health_facts import fact_sources_payload


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

RULE_VERSION = "1.2"
GUIDES = {
    "blood_pressure": {"text": "Adult reference flags: low below 90 systolic or 60 diastolic; review from 120 systolic or 80 diastolic; high from 140 systolic or 90 diastolic. These flags do not diagnose hypertension.", "sources": [{"title": "American Heart Association: low blood pressure", "url": "https://www.heart.org/en/health-topics/high-blood-pressure/the-facts-about-high-blood-pressure/low-blood-pressure-when-blood-pressure-is-too-low"}, {"title": "American Heart Association: blood pressure", "url": "https://www.heart.org/en/health-topics/high-blood-pressure/understanding-blood-pressure-readings"}], "limitations": "Home readings and a single measurement cannot establish a diagnosis. Pregnancy, symptoms and individual treatment targets require professional assessment."},
    "blood_glucose": {"text": "Low below 3.9 mmol/L in any context. Fasting: review from 5.6 and high from 7.0 mmol/L. Non-fasting: high flag from 11.1 mmol/L; lower non-fasting values are not classified as normal.", "sources": [{"title": "NIDDK: diabetes tests", "url": "https://www.niddk.nih.gov/health-information/diabetes/overview/tests-diagnosis"}, {"title": "ADA: low glucose reference", "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC12690178/"}], "limitations": "Lab diagnostic cutoffs are used only as review prompts for home readings. After-meal readings are not an oral glucose tolerance test. Fasting means at least eight hours without food."},
    "heart_rate": {"text": "Adult resting reference: review below 60 or above 100 bpm. Exercise and unknown-context readings are not classified using resting thresholds.", "sources": [{"title": "American Heart Association: heart rate", "url": "https://www.heart.org/en/health-topics/high-blood-pressure/the-facts-about-high-blood-pressure/all-about-heart-rate-pulse"}], "limitations": "Fitness, medication, illness and activity affect heart rate. A lower resting pulse may be expected for some people; a flag is not a diagnosis."},
}

FOCUS_RULE_VERSION = "personal-focus-1.0"
# Only complete condition names are recognised; free-text notes and negated phrases
# are deliberately not interpreted. Sources reviewed on 2026-09-27.
FOCUS_TOPICS = {
    "blood_pressure": {
        "label": "blood pressure",
        "names": {"hypertension", "high blood pressure", "essential hypertension", "高血压", "高血压病", "原发性高血压"},
        "family_source": {"title": "AHA: blood pressure family history", "url": "https://www.heart.org/en/health-topics/high-blood-pressure/know-your-risk-factors-for-high-blood-pressure"},
        "daily_source": {"title": "AHA: managing blood pressure", "url": "https://www.heart.org/en/health-topics/high-blood-pressure/changes-you-can-make-to-manage-high-blood-pressure"},
        "daily": "Plan balanced meals and regular physical activity that suits your abilities. Discuss sustainable habits and your own monitoring schedule with your healthcare professional.",
    },
    "blood_glucose": {
        "label": "blood glucose",
        "names": {"diabetes", "diabetes mellitus", "type 2 diabetes", "type ii diabetes", "糖尿病", "2型糖尿病", "二型糖尿病", "二型糖尿病史"},
        "family_source": {"title": "NIDDK: diabetes family history", "url": "https://www.niddk.nih.gov/health-information/diabetes/overview/risk-factors-type-2-diabetes"},
        "daily_source": {"title": "NIDDK: healthy living with diabetes", "url": "https://www.niddk.nih.gov/health-information/diabetes/overview/healthy-living-with-diabetes"},
        "prevention_source": {"title": "NIDDK: preventing type 2 diabetes", "url": "https://www.niddk.nih.gov/health-information/diabetes/overview/preventing-type-2-diabetes"},
        "daily": "Choose varied meals with vegetables and whole grains and drinks with little added sugar. Build activity gradually; discuss changes with your care team when you have a health condition or take medicines.",
    },
}


def parse_datetime(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except (TypeError, ValueError):
        raise ValueError("Enter a valid measurement date and time.") from None


def reading_flags(metric_type, value, secondary_value=None, context=""):
    flags = []
    if metric_type == "blood_pressure":
        if value < 90 or secondary_value < 60:
            flags.append("low")
        if value >= 140 or secondary_value >= 90:
            flags.append("high")
        elif value >= 120 or secondary_value >= 80:
            flags.append("watch")
        return flags
    elif metric_type == "blood_glucose":
        if value < 3.9:
            return ["low"]
        if context == "fasting" and value >= 7:
            return ["high"]
        if context == "fasting" and value >= 5.6:
            return ["watch"]
        if value >= 11.1:
            return ["high"]
        if context != "fasting":
            return ["not_assessed"]
    elif metric_type == "heart_rate":
        if context != "resting":
            return ["not_assessed"]
        if value < 60 or value > 100:
            return ["watch"]
    return []


def reading_status(metric_type, value, secondary_value=None, context=""):
    flags = reading_flags(metric_type, value, secondary_value, context)
    return next((status for status in ["high", "low", "watch", "not_assessed"] if status in flags), "in_range")


def active_measurements(query):
    return query.filter(~HealthMeasurement.id.in_(db.session.query(MeasurementDisposition.measurement_id)))


def measurement_disposition(identifier):
    item = db.session.get(MeasurementDisposition, identifier)
    return {"status": "corrected" if item.replacement_id else "voided", "replacement_id": item.replacement_id,
            "reason": item.reason, "changed_at": item.changed_at.isoformat() + "Z"} if item else None


def assess_measurement(item, special_context=None):
    profile = AccountProfile.query.filter_by(user_id=item.user_id).first()
    birth = profile.date_of_birth if profile else None
    measured = item.measured_at.date()
    age = measured.year - birth.year - ((measured.month, measured.day) < (birth.month, birth.day)) if birth else None
    context_record = db.session.get(MeasurementContext, item.id) if item.id else None
    special = special_context or (context_record.special_context if context_record else "general")
    reason = "adult_reference" if age is not None and age >= 18 else "age_unknown" if age is None else "under_18_at_measurement"
    if special != "general":
        reason = "special_context_requires_professional_review"
    flags = reading_flags(item.metric_type, item.value, item.secondary_value, item.context) if reason == "adult_reference" else ["not_assessed"]
    status = next((value for value in ["high", "low", "watch", "not_assessed"] if value in flags), "in_range")
    return {"status": status, "flags": flags, "assessment": {"reason": reason, "age_at_measurement": age, "rule_version": RULE_VERSION}, "special_context": special}


def serialize_measurement(item):
    return {**item.to_dict(), **assess_measurement(item), "disposition": measurement_disposition(item.id), "report_source": measurement_source_payload(item.id), "is_editable": item.source_type == "self" and not measurement_disposition(item.id)}


def serialize_alert(alert):
    return {**alert.to_dict(), "disposition": measurement_disposition(alert.measurement_id)}


def alert_for(measurement, special_context=None):
    assessment = assess_measurement(measurement, special_context)
    status = assessment["status"]
    if status in {"in_range", "not_assessed"}:
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
        message=f"A {value} {measurement.unit} reading matched these reference flags: {', '.join(assessment['flags'])}. Review the context and seek professional advice if you are concerned.",
        rule_name=f"{measurement.metric_type}_reference_threshold",
        rule_version=RULE_VERSION,
    )


def validate_measurement(data):
    metric_type = str(data.get("metric_type") or "")
    config = METRICS.get(metric_type)
    if not config:
        return None, "Select a supported health metric."
    if type(data.get("value")) is bool or type(data.get("secondary_value")) is bool:
        return None, "Enter numeric readings."
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
    if metric_type == "heart_rate" and context not in {"resting", "exercise", "unknown", ""}:
        return None, "Select the heart-rate measurement context."
    if metric_type == "blood_pressure":
        context = ""
    return {
        "metric_type": metric_type,
        "value": value,
        "secondary_value": secondary_value,
        "unit": config["unit"],
        "context": context,
        "measured_at": measured_at,
        "source_type": "self",
        "source_name": (str(data.get("source_name") or "Manual entry").strip() or "Manual entry")[:120],
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
    focused_reading = None
    if request.args.get("reading_id") is not None:
        try:
            reading_id = int(request.args["reading_id"])
            if not 1 <= reading_id <= 9223372036854775807:
                raise ValueError()
        except ValueError:
            return jsonify({"message": "Select a valid reading."}), 400
        focused_reading = HealthMeasurement.query.filter_by(id=reading_id, user_id=current_user.id, metric_type=metric_type).first()
        if not focused_reading:
            return jsonify({"message": "Reading not found."}), 404
    query = active_measurements(HealthMeasurement.query).filter(
        HealthMeasurement.user_id == current_user.id,
        HealthMeasurement.metric_type == metric_type,
        HealthMeasurement.measured_at >= cutoff,
    )
    context_filter = str(request.args.get("context") or "")
    allowed_contexts = {"blood_glucose": {"fasting", "after_meal", "random"}, "heart_rate": {"resting", "exercise", "unknown"}}
    if context_filter:
        if context_filter not in allowed_contexts.get(metric_type, set()):
            return jsonify({"message": "Select a valid measurement context."}), 400
        if context_filter == "unknown":
            query = query.filter(HealthMeasurement.context.in_(["unknown", ""]))
        else:
            query = query.filter_by(context=context_filter)
    readings = query.order_by(HealthMeasurement.measured_at.asc(), HealthMeasurement.id.asc()).all()
    serialized = [serialize_measurement(item) for item in readings]
    latest = serialized[-1] if serialized else None
    values = [item.value for item in readings]
    data_age_days = (utc_now() - readings[-1].measured_at).days if readings else None
    try:
        offset = int(request.args.get("timezone_offset_minutes", 0))
        if not -840 <= offset <= 840:
            raise ValueError()
    except ValueError:
        return jsonify({"message": "Invalid timezone offset."}), 400
    distinct_days = len({(item.measured_at - timedelta(minutes=offset)).date() for item in readings})
    if len(readings) < 3 or distinct_days < 3:
        sufficiency = {"status": "limited", "message": "At least three readings across three different dates in your selected timezone are needed for a descriptive trend summary."}
    elif data_age_days is not None and data_age_days > 14:
        sufficiency = {"status": "stale", "message": "The latest reading is over 14 days old. Add a newer reading before relying on this trend."}
    else:
        sufficiency = {"status": "sufficient", "message": f"This view is based on {len(readings)} readings from the selected period."}
    comparable = metric_type == "blood_pressure" or len({item.context for item in readings}) <= 1
    if not comparable:
        sufficiency = {"status": "mixed_context", "message": "Choose one measurement context before comparing readings or generating a trend summary."}
    trend = None
    if sufficiency["status"] == "sufficient":
        delta = round(readings[-1].value - readings[0].value, 2)
        trend = {"direction": "increased" if delta > 0 else "decreased" if delta < 0 else "unchanged", "change": delta,
                 "first_reading_id": readings[0].id, "last_reading_id": readings[-1].id,
                 "message": "First-to-last difference only; this does not predict future health or establish a diagnosis.",
                 "secondary_change": round(readings[-1].secondary_value - readings[0].secondary_value, 2) if metric_type == "blood_pressure" else None}
    history = HealthMeasurement.query.filter(HealthMeasurement.user_id == current_user.id, HealthMeasurement.metric_type == metric_type,
                                             HealthMeasurement.measured_at >= cutoff, HealthMeasurement.id.in_(db.session.query(MeasurementDisposition.measurement_id))).order_by(HealthMeasurement.measured_at.desc()).all()
    focus, focus_eligibility = health_focus(current_user.id, offset)
    return jsonify({
        "metric": {"key": metric_type, **METRICS[metric_type]},
        "readings": serialized,
        "focused_reading": serialize_measurement(focused_reading) if focused_reading else None,
        "focused_reading_outside_period": bool(focused_reading and focused_reading.measured_at < cutoff),
        "latest": latest,
        "summary": {
            "count": len(readings),
            "average": round(sum(values) / len(values), 1) if values and comparable else None,
            "minimum": min(values) if values else None,
            "maximum": max(values) if values else None,
            "secondary_average": round(sum(item.secondary_value for item in readings) / len(readings), 1) if readings and metric_type == "blood_pressure" else None,
            "distinct_days": distinct_days,
            "attention_count": sum(item["status"] in {"low", "watch", "high"} for item in serialized),
            "unassessed_count": sum(item["status"] == "not_assessed" for item in serialized),
            "context_counts": {context or "unknown": sum(item.context == context for item in readings) for context in sorted({item.context for item in readings})},
        },
        "reference": {"version": RULE_VERSION, **GUIDES[metric_type]},
        "data_sufficiency": sufficiency,
        "trend": trend,
        "superseded_readings": [serialize_measurement(item) for item in history],
        "profile_points": profile_points(current_user.id),
        "health_focus": focus,
        "health_focus_eligibility": focus_eligibility,
        "timezone_offset_minutes": offset,
        "generated_at": utc_now().isoformat() + "Z",
    })


@insights_bp.post("/metrics")
@login_required
def create_metric():
    data = request.get_json(silent=True) or {}
    values, error = validate_measurement(data)
    if error:
        return jsonify({"error": "invalid_measurement", "message": error}), 400
    special = data.get("special_context", "general")
    if special not in {"general", "pregnancy", "individual_target", "unknown"}:
        return jsonify({"message": "Select a valid reference context."}), 400
    measurement = HealthMeasurement(user_id=current_user.id, **values)
    db.session.add(measurement)
    db.session.flush()
    db.session.add(MeasurementContext(measurement_id=measurement.id, special_context=special))
    alert = alert_for(measurement, special)
    if alert:
        db.session.add(alert)
    append_audit(current_user.id, "measurement_created", details={"measurement_id": measurement.id})
    db.session.commit()
    return jsonify({"measurement": serialize_measurement(measurement), "alert": serialize_alert(alert) if alert else None}), 201


@insights_bp.get("/alerts")
@login_required
def list_alerts():
    status = request.args.get("status", "pending")
    if status not in {"pending", "reviewed", "all"}:
        return jsonify({"message": "Select a valid alert status."}), 400
    query = HealthAlert.query.filter_by(user_id=current_user.id)
    if status == "pending":
        query = query.filter(HealthAlert.acknowledged_at.is_(None), ~HealthAlert.measurement_id.in_(db.session.query(MeasurementDisposition.measurement_id)))
    elif status == "reviewed":
        query = query.filter(HealthAlert.acknowledged_at.is_not(None))
    alerts = query.order_by(HealthAlert.created_at.desc(), HealthAlert.id.desc()).all()
    return jsonify({"alerts": [serialize_alert(alert) for alert in alerts], "count": len(alerts)})


@insights_bp.patch("/alerts/<int:alert_id>/acknowledge")
@login_required
def acknowledge_alert(alert_id):
    alert = HealthAlert.query.filter_by(id=alert_id, user_id=current_user.id).first()
    if not alert:
        return jsonify({"error": "not_found", "message": "Health alert not found."}), 404
    if not alert.acknowledged_at:
        alert.acknowledged_at = utc_now()
    db.session.commit()
    return jsonify({"alert": serialize_alert(alert)})


def profile_points(user_id):
    """Descriptive organisation prompts, not a clinical risk or treatment engine."""
    profile = profile_payload(user_id)
    sections = profile.get("sections", {})
    suggestions = {
        "past_history": "Keep relevant history and dates available for your next professional review.",
        "family_history": "Check the recorded relationships and discuss relevant family history with a professional.",
        "medications": "Keep the medication list current and confirm it with your clinician or pharmacist; do not change doses based on this page.",
        "allergies": "Check that recorded allergies and reactions are accurate before a consultation.",
    }
    return [{"section": name, "status": section.get("status", "unknown"), "item_count": len(section.get("items", [])),
             "evidence": f"Personal health profile revision {profile.get('revision', 0)}; self-reported {name.replace('_', ' ')}",
             "rule_version": "profile-organisation-1.0",
             "message": "This section has not been recorded; missing information does not mean no history." if section.get("status", "unknown") == "unknown" else suggestions[name]}
            for name, section in sections.items() if name in suggestions]


@insights_bp.patch("/metrics/<int:measurement_id>")
@insights_bp.post("/metrics/<int:measurement_id>/void")
@login_required
def correct_measurement(measurement_id):
    original = HealthMeasurement.query.filter_by(id=measurement_id, user_id=current_user.id).first()
    if not original:
        return jsonify({"message": "Reading not found."}), 404
    if original.source_type != "self":
        return jsonify({"message": "Provider and device readings are read-only."}), 403
    if measurement_disposition(original.id):
        return jsonify({"message": "This reading was already corrected or voided. Refresh the history."}), 409
    data = request.get_json(silent=True) or {}
    reason = str(data.get("reason") or "").strip()
    if not reason or len(reason) > 300:
        return jsonify({"message": "Enter a correction reason of 1–300 characters."}), 400
    replacement = alert = None
    if not request.path.endswith("/void"):
        values, error = validate_measurement({**original.to_dict(), **data, "metric_type": original.metric_type})
        if error:
            return jsonify({"message": error}), 400
        previous_context = db.session.get(MeasurementContext, original.id)
        special = data.get("special_context", previous_context.special_context if previous_context else "general")
        if special not in {"general", "pregnancy", "individual_target", "unknown"}:
            return jsonify({"message": "Select a valid reference context."}), 400
        replacement = HealthMeasurement(user_id=current_user.id, **values)
        db.session.add(replacement)
        db.session.flush()
        db.session.add(MeasurementContext(measurement_id=replacement.id, special_context=special))
        alert = alert_for(replacement, special)
        if alert:
            db.session.add(alert)
    db.session.add(MeasurementDisposition(measurement_id=original.id, replacement_id=replacement.id if replacement else None, reason=reason))
    append_audit(current_user.id, "measurement_corrected" if replacement else "measurement_voided",
                 details={"measurement_id": original.id, "replacement_id": replacement.id if replacement else None, "reason": reason})
    from sqlalchemy.exc import IntegrityError
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"message": "Another request already changed this reading. Refresh the history."}), 409
    return jsonify({"original": serialize_measurement(original), "measurement": serialize_measurement(replacement) if replacement else None,
                    "alert": serialize_alert(alert) if alert else None})


def health_focus(user_id, timezone_offset_minutes=0):
    """Small, explicit preparation rules. No text inference, risk score or diagnosis."""
    today = utc_now().date()
    account = db.session.get(AccountProfile, user_id)
    birth = account.date_of_birth if account else None
    age = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day)) if birth else None
    if age is None or age < 18:
        return [], {"status": "not_assessed", "reason": "Record an adult date of birth before using these adult discussion prompts." if age is None else "These adult discussion prompts are not applied to people under 18."}
    recent = active_measurements(HealthMeasurement.query).filter(HealthMeasurement.user_id == user_id,
                 HealthMeasurement.measured_at >= utc_now() - timedelta(days=30)).order_by(HealthMeasurement.measured_at.desc(), HealthMeasurement.id.desc()).all()
    assessed = [(item, assess_measurement(item)) for item in recent]
    latest_by_metric = {}
    for item, assessment in assessed:
        latest_by_metric.setdefault(item.metric_type, assessment)
    if any(item["special_context"] != "general" for item in latest_by_metric.values()):
        return [], {"status": "not_assessed", "reason": "A latest reading in the past 30 days records pregnancy, an individual clinical target or an uncertain context. Personal advice requires professional review."}

    profile = profile_payload(user_id)
    matches = {metric: [] for metric in FOCUS_TOPICS}
    cards = []
    for section_name in ("family_history", "past_history"):
        section = profile.get("sections", {}).get(section_name, {})
        if section.get("status") != "recorded":
            continue
        for index, entry in enumerate(section.get("items", [])):
            name = " ".join(str(entry.get("name") or "").strip().casefold().split())
            for metric, topic in FOCUS_TOPICS.items():
                if name not in topic["names"]:
                    continue
                evidence = {"type": "profile_item", "section": section_name, "item_id": entry.get("id"),
                            "locator": f"sections.{section_name}.items[{index}]", "profile_revision": profile.get("revision", 0),
                            "name": entry["name"], "match": "exact_condition_name"}
                matches[metric].append(evidence)
        for metric, topic in FOCUS_TOPICS.items():
            evidence = [entry for entry in matches[metric] if entry["section"] == section_name]
            if not evidence:
                continue
            family = section_name == "family_history"
            cards.append({
                "key": f"{section_name}-{metric}", "title": f"{'Family history' if family else 'Recorded personal history'}: {topic['label']}",
                "message": f"Your recorded family history includes a recognised {topic['label']} condition. Discuss your relatives' diagnoses and whether monitoring or screening is appropriate for you." if family else f"You have explicitly recorded a {topic['label']} condition. Bring this history and any measurements to review the monitoring plan already agreed with your healthcare professional.",
                "daily_prevention": topic["daily"], "evidence": evidence, "rule_version": FOCUS_RULE_VERSION,
                "applicability": "Known adult age; section explicitly marked recorded; complete condition name matches the published English/Chinese vocabulary. No details or family relationships are inferred.",
                "sources": ([topic["family_source"]] if family else []) + [topic["daily_source"]] + ([topic["prevention_source"]] if family and "prevention_source" in topic else []),
            })

    groups = {}
    for item, assessment in assessed:
        if assessment["assessment"]["reason"] != "adult_reference":
            continue
        for flag in assessment["flags"]:
            if flag in {"low", "watch", "high"}:
                groups.setdefault((item.metric_type, item.context, flag), []).append(item)
    for (metric, context, flag), items in groups.items():
        dates = {(item.measured_at - timedelta(minutes=timezone_offset_minutes)).date() for item in items}
        if len(dates) < 2:
            continue
        evidence = [{"type": "measurement", "reading_id": item.id, "measured_at": item.measured_at.isoformat() + "Z",
                     "metric": metric, "context": context or "not_recorded", "flag": flag, "value": item.value,
                     "secondary_value": item.secondary_value, "unit": item.unit, "source_type": item.source_type, "source_name": item.source_name} for item in reversed(items)]
        related_history = matches.get(metric, [])
        cards.append({"key": f"repeated-{metric}-{context}-{flag}", "title": f"Repeated {flag} reference flags: {METRICS[metric]['label'].lower()}",
                      "message": f"{len(items)} current readings on {len(dates)} local dates in the past 30 days crossed the same configured reference flag. Check the entries, measurement technique and context, and discuss the timestamped readings with a healthcare professional." + (" The related history entries below can help prepare that discussion." if related_history else ""),
                      "daily_prevention": None, "evidence": evidence + related_history, "rule_version": FOCUS_RULE_VERSION,
                      "measurement_rule_version": RULE_VERSION,
                      "applicability": f"Adult age at each measurement; general reference context; same metric, collection context and flag on at least two local dates within 30 days. Corrected, voided and inapplicable readings are excluded. Context: {context or 'blood pressure'}.",
                      "sources": GUIDES[metric]["sources"]})
    # One card per topic: the same record can support several rules without
    # creating several apparently independent health concerns.
    provenance = fact_sources_payload(user_id)['sources']
    current_sources = {}
    for source in provenance:
        if source['current_item_matches']:
            current_sources.setdefault(source['profile_item_id'], []).append(source)
    merged = {}
    topic_labels = {'blood_pressure': '血压情况', 'blood_glucose': '血糖情况', 'heart_rate': '心率情况'}
    for card in cards:
        metric = next((key for key in topic_labels if key in card['key']), None)
        if not metric:
            continue
        target = merged.setdefault(metric, {'key': f'topic-{metric}', 'topic': metric, 'title': topic_labels[metric],
            'message': '结合已确认的健康信息与近期记录，整理需要核对和就诊时可讨论的事项。',
            'daily_prevention': None, 'evidence': [], 'reasons': [], 'source_rules': [], 'sources': [],
            'rule_version': FOCUS_RULE_VERSION, 'measurement_rule_version': RULE_VERSION,
            'applicability': '沿用各条既有规则的年龄、测量情境、时间及明确名称条件；同主题仅汇总展示，不计算疾病概率。'})
        target['source_rules'].append(card['key'])
        target['reasons'].append({'key': card['key'], 'message': card['message'], 'applicability': card['applicability']})
        target['daily_prevention'] = target['daily_prevention'] or card.get('daily_prevention')
        for source in card['sources']:
            if source['url'] not in {item['url'] for item in target['sources']}:
                target['sources'].append(source)
        for evidence in card['evidence']:
            identifier = ('measurement', evidence['reading_id']) if evidence['type'] == 'measurement' else ('profile_item', evidence.get('item_id') or evidence.get('locator'))
            existing = next((item for item in target['evidence'] if item['_identity'] == identifier), None)
            if existing:
                if evidence.get('flag') and evidence['flag'] not in existing.get('flags', []):
                    existing.setdefault('flags', []).append(evidence['flag'])
                continue
            enriched = {**evidence, '_identity': identifier}
            if evidence['type'] == 'profile_item':
                enriched['report_sources'] = current_sources.get(evidence.get('item_id'), [])
            else:
                enriched['flags'] = [evidence['flag']]
                enriched['report_source'] = measurement_source_payload(evidence['reading_id'])
            target['evidence'].append(enriched)
    for card in merged.values():
        for item in card['evidence']:
            item.pop('_identity', None)
        histories = sum(item['type'] == 'profile_item' for item in card['evidence'])
        readings = sum(item['type'] == 'measurement' for item in card['evidence'])
        parts = ([f'已确认 {histories} 条相关既往或家族病史'] if histories else []) + ([f'近 30 天有 {readings} 条指标满足多日复核条件'] if readings else [])
        card['summary'] = '；'.join(parts) + '。核对来源与测量情境，就诊时讨论已有记录和监测安排。'
        for reason in card['reasons']:
            if reason['key'].startswith('family_history'):
                reason['message'] = '家族病史中有明确记录的相关疾病名称。可整理亲属的已知诊断，就诊时讨论是否需要适合自己的监测或筛查。'
            elif reason['key'].startswith('past_history'):
                reason['message'] = '既往病史中明确记录了相关疾病。可携带原报告与近期指标，核对已有的个人监测安排。'
            else:
                reason['message'] = '近期同类、同情境的指标在至少两个本地日期触发同一参考标记。请先核对录入值及测量方式，有疑问时向专业人员咨询。'
        if card['daily_prevention']:
            card['daily_prevention'] = '安排适合自身能力的日常活动，保持多样、均衡的饮食。存在健康问题或正在用药时，与医护人员讨论生活习惯的调整。'
    return list(merged.values()), {"status": "available", "reason": "No matching evidence for these limited discussion rules. This does not establish that there are no health concerns." if not merged else "Based on explicitly recorded history and applicable current readings from the past 30 days."}
