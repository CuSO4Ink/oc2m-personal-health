from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request, current_app
from flask_login import current_user, login_required
from sqlalchemy import or_, update

from ..extensions import db
from ..models import Appointment, AppointmentSlot, ElderCareListing, HealthReminder, MedicalService, Notification, ReminderSchedule, utc_now
from ..service_models import ReminderCancellation, ServiceClinician, AppointmentSharing
from ..demo_care_catalog import ensure_demo_care_catalog
from ..record_audit import append_audit
from ..sharing_scope import digest
from .sharing import validate_grant, persist_grant


services_bp = Blueprint("services", __name__)
REMINDER_CATEGORIES = {"medication", "measurement", "appointment", "general"}


def service_bookable(service):
    return service.active and (service.facility.verified or bool(current_app.config.get("DEMO_DATASET") and ServiceClinician.query.filter_by(service_id=service.id).first()))


def appointment_payload(appointment):
    payload = appointment.to_dict()
    link = db.session.get(AppointmentSharing, appointment.id)
    payload["clinician"] = link.recipient.to_dict() if link else None
    payload["sharing"] = {"grant_id": link.grant_id, "status": link.grant.status, "expires_at": link.grant.expires_at.isoformat() + "Z"} if link and link.grant else None
    payload["mode"] = "local_simulation"
    return payload


def parse_datetime(value, label="date and time"):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except (TypeError, ValueError):
        raise ValueError(f"Select a valid {label}.") from None


@services_bp.get("/medical")
@login_required
def medical_catalog():
    ensure_demo_care_catalog()
    query = MedicalService.query.filter_by(active=True)
    specialty = str(request.args.get("specialty") or "").strip()
    keyword = str(request.args.get("q") or "").strip()
    if specialty:
        query = query.filter_by(specialty=specialty)
    if keyword:
        term = f"%{keyword}%"
        query = query.join(MedicalService.facility).filter(or_(MedicalService.name.ilike(term), MedicalService.specialty.ilike(term)))
    services = query.order_by(MedicalService.specialty.asc(), MedicalService.name.asc()).all()
    payload = []
    for service in services:
        if not service_bookable(service):
            continue
        item = service.to_dict(include_slots=True)
        item["slots"] = [slot for slot in item["slots"] if slot["available"]]
        item["clinicians"] = [link.recipient.to_dict() for link in ServiceClinician.query.filter_by(service_id=service.id).all()]
        if item["slots"]:
            payload.append(item)
    return jsonify({"services": payload, "mode": "local_simulation"})


@services_bp.get("/appointments")
@login_required
def list_appointments():
    appointments = Appointment.query.filter_by(user_id=current_user.id).join(Appointment.slot).order_by(AppointmentSlot.starts_at.asc()).all()
    return jsonify({"appointments": [appointment_payload(appointment) for appointment in appointments]})


@services_bp.post("/appointments")
@login_required
def book_appointment():
    data = request.get_json(silent=True) or {}
    try:
        slot_id = int(data.get("slot_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "invalid_slot", "message": "Select an appointment time."}), 400
    slot = AppointmentSlot.query.filter_by(id=slot_id).with_for_update().first()
    if not slot or not service_bookable(slot.service):
        return jsonify({"error": "invalid_slot", "message": "This appointment time is unavailable."}), 404
    if slot.starts_at <= utc_now() or slot.available_places <= 0:
        return jsonify({"error": "slot_full", "message": "This appointment time is no longer available. Select another time."}), 409
    existing = Appointment.query.filter_by(user_id=current_user.id, slot_id=slot.id, status="confirmed").first()
    if existing:
        return jsonify({"error": "duplicate_appointment", "message": "You already booked this appointment time.", "appointment": existing.to_dict()}), 409
    reason = str(data.get("reason") or "").strip()
    if len(reason) < 3:
        return jsonify({"error": "reason_required", "message": "Briefly describe the reason for your appointment."}), 400
    clinicians = ServiceClinician.query.filter_by(service_id=slot.service_id).all()
    clinician = next((item.recipient for item in clinicians if type(data.get("recipient_id")) is int and item.recipient_id == data["recipient_id"]), None)
    if clinicians and not clinician:
        return jsonify({"message": "Choose a clinician from this service."}), 400
    sharing = data.get("sharing_draft")
    validated = None
    if sharing is not None:
        if not isinstance(sharing, dict) or not clinician or sharing.get("recipient_id") != clinician.id:
            return jsonify({"message": "The sharing recipient must be the selected clinician."}), 400
        try:
            validated = validate_grant(sharing)
        except ValueError as error:
            return jsonify({"message": str(error)}), 400
        if not sharing.get("preview_token") or sharing["preview_token"] != digest(validated[-1]):
            return jsonify({"message": "Your sharing selection changed. Preview the content again before booking."}), 409
    appointment = Appointment(user_id=current_user.id, slot_id=slot.id, reason=reason[:300], status="confirmed")
    reserved = db.session.execute(update(AppointmentSlot).where(AppointmentSlot.id == slot.id, AppointmentSlot.booked_count < AppointmentSlot.capacity).values(booked_count=AppointmentSlot.booked_count + 1))
    if not reserved.rowcount:
        db.session.rollback()
        return jsonify({"message": "This appointment time is full."}), 409
    db.session.add(appointment)
    db.session.flush()
    if clinician:
        grant = persist_grant(sharing, validated) if sharing is not None else None
        db.session.add(AppointmentSharing(appointment_id=appointment.id, recipient_id=clinician.id, grant_id=grant.id if grant else None))
    append_audit(current_user.id, "appointment_booked", details={"appointment_id": appointment.id, "slot_id": slot.id, "recipient_id": clinician.id if clinician else None})
    db.session.commit()
    return jsonify({"appointment": appointment_payload(appointment)}), 201


@services_bp.patch("/appointments/<int:appointment_id>/cancel")
@login_required
def cancel_appointment(appointment_id):
    appointment = Appointment.query.filter_by(id=appointment_id, user_id=current_user.id).first()
    if not appointment:
        return jsonify({"error": "not_found", "message": "Appointment not found."}), 404
    if appointment.status == "confirmed":
        appointment.status = "cancelled"
        appointment.cancelled_at = utc_now()
        appointment.slot.booked_count = max(0, appointment.slot.booked_count - 1)
        link = db.session.get(AppointmentSharing, appointment.id)
        if link and link.grant and link.grant.status in {"active", "scheduled"}:
            link.grant.revoked_at = utc_now()
            append_audit(current_user.id, "grant_revoked", details={"grant_id": link.grant_id, "reason": "appointment_cancelled"})
        db.session.commit()
    return jsonify({"appointment": appointment_payload(appointment)})


@services_bp.get("/reminders")
@login_required
def list_reminders():
    reminders = HealthReminder.query.filter_by(user_id=current_user.id).order_by(HealthReminder.completed_at.asc(), HealthReminder.next_due_at.asc()).all()
    return jsonify({"reminders": [reminder.to_dict() for reminder in reminders]})


@services_bp.post("/reminders")
@login_required
def create_reminder():
    data = request.get_json(silent=True) or {}
    title = str(data.get("title") or "").strip()
    category = str(data.get("category") or "general").strip()
    repeat_days = data.get("repeat_days", 0)
    if type(repeat_days) is not int or repeat_days not in {0, 1, 7}:
        return jsonify({"message": "Select one-time, daily or weekly repetition."}), 400
    if len(title) < 2:
        return jsonify({"error": "invalid_title", "message": "Enter a reminder title."}), 400
    if category not in REMINDER_CATEGORIES:
        return jsonify({"error": "invalid_category", "message": "Select a valid reminder category."}), 400
    try:
        next_due_at = parse_datetime(data.get("next_due_at"), "reminder date and time")
    except ValueError as error:
        return jsonify({"error": "invalid_time", "message": str(error)}), 400
    if next_due_at > utc_now() + timedelta(days=730):
        return jsonify({"error": "time_too_far", "message": "Choose a reminder within the next two years."}), 400
    reminder = HealthReminder(
        user_id=current_user.id,
        title=title,
        category=category,
        next_due_at=next_due_at,
        schedule_note=str(data.get("schedule_note") or "One time").strip()[:160] or "One time",
        source_name="Personal reminder",
        notes=str(data.get("notes") or "").strip()[:300],
    )
    db.session.add(reminder)
    db.session.flush()
    if repeat_days:
        reminder.schedule_note = f"Every {repeat_days * 24} hours (UTC)"
        db.session.add(ReminderSchedule(reminder_id=reminder.id, interval_days=repeat_days))
    db.session.commit()
    return jsonify({"reminder": reminder.to_dict()}), 201


@services_bp.patch("/reminders/<int:reminder_id>/complete")
@login_required
def complete_reminder(reminder_id):
    reminder = HealthReminder.query.filter_by(id=reminder_id, user_id=current_user.id).first()
    if not reminder:
        return jsonify({"error": "not_found", "message": "Health reminder not found."}), 404
    if reminder.cancellation:
        return jsonify({"message": "A cancelled reminder cannot be completed."}), 409
    if not reminder.completed_at:
        claimed = db.session.execute(update(HealthReminder).where(HealthReminder.id == reminder.id, HealthReminder.completed_at.is_(None)).values(completed_at=utc_now()))
        if not claimed.rowcount:
            db.session.rollback()
            return jsonify({"reminder": reminder.to_dict()})
        interval = reminder.recurrence.interval_days if reminder.recurrence else 0
        if interval:
            due = reminder.next_due_at
            steps = max(1, (utc_now() - due).days // interval + 1)
            successor = HealthReminder(user_id=reminder.user_id, title=reminder.title, category=reminder.category,
                                       next_due_at=due + timedelta(days=steps * interval), schedule_note=reminder.schedule_note,
                                       source_name=reminder.source_name, notes=reminder.notes)
            db.session.add(successor)
            db.session.flush()
            db.session.add(ReminderSchedule(reminder_id=successor.id, interval_days=interval))
        db.session.commit()
    return jsonify({"reminder": reminder.to_dict()})


@services_bp.patch("/reminders/<int:reminder_id>/stop-repeat")
@login_required
def stop_repeat(reminder_id):
    reminder = HealthReminder.query.filter_by(id=reminder_id, user_id=current_user.id).first()
    if not reminder:
        return jsonify({"message": "Health reminder not found."}), 404
    if reminder.completed_at or reminder.cancellation:
        return jsonify({"message": "Stop repetition on the current unfinished reminder."}), 409
    if reminder.recurrence:
        reminder.recurrence.interval_days = 0
        reminder.schedule_note = "One time (repetition stopped)"
        db.session.commit()
    return jsonify({"reminder": reminder.to_dict()})


@services_bp.patch("/reminders/<int:reminder_id>")
@login_required
def edit_reminder(reminder_id):
    reminder = HealthReminder.query.filter_by(id=reminder_id, user_id=current_user.id).first()
    if not reminder:
        return jsonify({"message": "Health reminder not found."}), 404
    if reminder.completed_at or reminder.cancellation:
        return jsonify({"message": "Completed or cancelled reminders are kept as history."}), 409
    data = request.get_json(silent=True) or {}
    title = str(data.get("title") or "").strip()
    category = data.get("category", "general")
    repeat = data.get("repeat_days", 0)
    if len(title) < 2 or len(title) > 160 or category not in REMINDER_CATEGORIES:
        return jsonify({"message": "Enter a title (2–160 characters) and a supported category."}), 400
    if type(repeat) is not int or repeat not in {0, 1, 7}:
        return jsonify({"message": "Select one-time, daily or weekly repetition."}), 400
    try:
        due = parse_datetime(data.get("next_due_at"), "reminder date and time")
    except ValueError as error:
        return jsonify({"message": str(error)}), 400
    if due > utc_now() + timedelta(days=730):
        return jsonify({"message": "Choose a reminder within the next two years."}), 400
    reminder.title, reminder.category, reminder.next_due_at = title, category, due
    reminder.notes = str(data.get("notes") or "").strip()[:300]
    reminder.schedule_note = f"Every {repeat * 24} hours (UTC)" if repeat else str(data.get("schedule_note") or "One time").strip()[:160]
    if reminder.recurrence:
        reminder.recurrence.interval_days = repeat
    elif repeat:
        db.session.add(ReminderSchedule(reminder_id=reminder.id, interval_days=repeat))
    # A new schedule must not retain an outdated due notice.
    Notification.query.filter_by(user_id=current_user.id, dedupe_key=f"health-reminder-{reminder.id}").delete()
    db.session.commit()
    return jsonify({"reminder": reminder.to_dict()})


@services_bp.patch("/reminders/<int:reminder_id>/cancel")
@login_required
def cancel_reminder(reminder_id):
    reminder = HealthReminder.query.filter_by(id=reminder_id, user_id=current_user.id).first()
    if not reminder:
        return jsonify({"message": "Health reminder not found."}), 404
    if reminder.completed_at:
        return jsonify({"message": "Completed reminders remain in history."}), 409
    if not reminder.cancellation:
        db.session.add(ReminderCancellation(reminder_id=reminder.id))
        if reminder.recurrence:
            reminder.recurrence.interval_days = 0
        db.session.commit()
    return jsonify({"reminder": reminder.to_dict()})


@services_bp.patch("/appointments/<int:appointment_id>/reschedule")
@login_required
def reschedule_appointment(appointment_id):
    appointment = Appointment.query.filter_by(id=appointment_id, user_id=current_user.id).first()
    if not appointment:
        return jsonify({"message": "Appointment not found."}), 404
    data = request.get_json(silent=True) or {}
    if data.get("expected_slot_id") != appointment.slot_id:
        return jsonify({"message": "Appointment changed. Refresh before rescheduling."}), 409
    if appointment.status != "confirmed" or appointment.slot.starts_at <= utc_now():
        return jsonify({"message": "Only future confirmed appointments can be rescheduled."}), 409
    slot = db.session.get(AppointmentSlot, data.get("slot_id")) if type(data.get("slot_id")) is int else None
    if not slot or slot.service_id != appointment.slot.service_id or slot.id == appointment.slot_id or slot.starts_at <= utc_now() or not service_bookable(slot.service):
        return jsonify({"message": "Choose another available time for the same service."}), 400
    if Appointment.query.filter_by(user_id=current_user.id, slot_id=slot.id, status="confirmed").first():
        return jsonify({"message": "You already booked this time."}), 409
    reserved = db.session.execute(update(AppointmentSlot).where(AppointmentSlot.id == slot.id, AppointmentSlot.booked_count < AppointmentSlot.capacity).values(booked_count=AppointmentSlot.booked_count + 1))
    if not reserved.rowcount:
        db.session.rollback()
        return jsonify({"message": "This time is full. Your original appointment is unchanged."}), 409
    old_slot_id = appointment.slot_id
    old_time = appointment.slot.starts_at
    changed = db.session.execute(update(Appointment).where(Appointment.id == appointment.id, Appointment.slot_id == old_slot_id, Appointment.status == "confirmed").values(slot_id=slot.id))
    if not changed.rowcount:
        db.session.rollback()
        return jsonify({"message": "Appointment changed. Refresh before rescheduling."}), 409
    db.session.execute(update(AppointmentSlot).where(AppointmentSlot.id == old_slot_id, AppointmentSlot.booked_count > 0).values(booked_count=AppointmentSlot.booked_count - 1))
    for notification in Notification.query.filter_by(user_id=current_user.id, dedupe_key=f"appointment-{appointment.id}").all():
        notification.message = f"Your appointment was rescheduled to {slot.starts_at.isoformat()} UTC with {slot.service.facility.name}."
        notification.read_at = None
    db.session.add(Notification(user_id=current_user.id, dedupe_key=f"reschedule-{appointment.id}-{utc_now().isoformat()}", category="care", severity="info", title="Appointment rescheduled", message=f"Changed from {old_time.isoformat()} UTC to {slot.starts_at.isoformat()} UTC.", action_path="/services", source_name="Local appointment service"))
    db.session.commit()
    db.session.expire(appointment, ["slot"])
    return jsonify({"appointment": appointment_payload(appointment)})


@services_bp.get("/elder-care")
@login_required
def elder_care_catalog():
    query = ElderCareListing.query.filter_by(active=True)
    category = str(request.args.get("category") or "").strip()
    keyword = str(request.args.get("q") or "").strip()
    if category:
        query = query.filter_by(category=category)
    if keyword:
        term = f"%{keyword}%"
        query = query.filter(or_(ElderCareListing.name.ilike(term), ElderCareListing.address.ilike(term), ElderCareListing.summary.ilike(term)))
    listings = query.order_by(ElderCareListing.name.asc()).all()
    return jsonify({"listings": [listing.to_dict() for listing in listings]})
