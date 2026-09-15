from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import or_

from ..extensions import db
from ..models import Appointment, AppointmentSlot, ElderCareListing, HealthReminder, MedicalService, utc_now


services_bp = Blueprint("services", __name__)
REMINDER_CATEGORIES = {"medication", "measurement", "appointment", "general"}


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
    query = MedicalService.query.filter_by(active=True)
    specialty = str(request.args.get("specialty") or "").strip()
    keyword = str(request.args.get("q") or "").strip()
    if specialty:
        query = query.filter_by(specialty=specialty)
    if keyword:
        term = f"%{keyword}%"
        query = query.join(MedicalService.facility).filter(or_(MedicalService.name.ilike(term), MedicalService.specialty.ilike(term)))
    services = query.order_by(MedicalService.specialty.asc(), MedicalService.name.asc()).all()
    return jsonify({"services": [service.to_dict(include_slots=True) for service in services]})


@services_bp.get("/appointments")
@login_required
def list_appointments():
    appointments = Appointment.query.filter_by(user_id=current_user.id).join(Appointment.slot).order_by(AppointmentSlot.starts_at.asc()).all()
    return jsonify({"appointments": [appointment.to_dict() for appointment in appointments]})


@services_bp.post("/appointments")
@login_required
def book_appointment():
    data = request.get_json(silent=True) or {}
    try:
        slot_id = int(data.get("slot_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "invalid_slot", "message": "Select an appointment time."}), 400
    slot = AppointmentSlot.query.filter_by(id=slot_id).with_for_update().first()
    if not slot or not slot.service.active or not slot.service.facility.verified:
        return jsonify({"error": "invalid_slot", "message": "This appointment time is unavailable."}), 404
    if slot.starts_at <= utc_now() or slot.available_places <= 0:
        return jsonify({"error": "slot_full", "message": "This appointment time is no longer available. Select another time."}), 409
    existing = Appointment.query.filter_by(user_id=current_user.id, slot_id=slot.id, status="confirmed").first()
    if existing:
        return jsonify({"error": "duplicate_appointment", "message": "You already booked this appointment time.", "appointment": existing.to_dict()}), 409
    reason = str(data.get("reason") or "").strip()
    if len(reason) < 3:
        return jsonify({"error": "reason_required", "message": "Briefly describe the reason for your appointment."}), 400
    appointment = Appointment(user_id=current_user.id, slot_id=slot.id, reason=reason[:300], status="confirmed")
    slot.booked_count += 1
    db.session.add(appointment)
    db.session.commit()
    return jsonify({"appointment": appointment.to_dict()}), 201


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
        db.session.commit()
    return jsonify({"appointment": appointment.to_dict()})


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
    db.session.commit()
    return jsonify({"reminder": reminder.to_dict()}), 201


@services_bp.patch("/reminders/<int:reminder_id>/complete")
@login_required
def complete_reminder(reminder_id):
    reminder = HealthReminder.query.filter_by(id=reminder_id, user_id=current_user.id).first()
    if not reminder:
        return jsonify({"error": "not_found", "message": "Health reminder not found."}), 404
    if not reminder.completed_at:
        reminder.completed_at = utc_now()
        db.session.commit()
    return jsonify({"reminder": reminder.to_dict()})


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
