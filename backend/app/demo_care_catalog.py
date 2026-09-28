"""Maintain fictional future scheduling only inside the dedicated demo dataset."""
from datetime import datetime, time, timedelta

from flask import current_app

from .extensions import db
from .models import AppointmentSlot, MedicalService, ServiceFacility, ShareRecipient, utc_now
from .service_models import ServiceClinician


def ensure_demo_care_catalog():
    if not current_app.config.get("DEMO_DATASET"):
        return
    facility = ServiceFacility.query.filter(ServiceFacility.name.in_([
        "Example Clinic · demonstration", "Maple Grove Family Clinic"])).first()
    if not facility:
        facility = ServiceFacility(name="Maple Grove Family Clinic", address="128 Maple Avenue, Brookfield", phone="", verified=False)
        db.session.add(facility); db.session.flush()
    facility.name, facility.address = "Maple Grove Family Clinic", "128 Maple Avenue, Brookfield"
    facility.phone = ""
    service = MedicalService.query.filter_by(facility_id=facility.id).order_by(MedicalService.id).first()
    if not service:
        service = MedicalService(facility_id=facility.id, name="General health review", specialty="General Practice", duration_minutes=20, cost_label="No payment is collected", active=True)
        db.session.add(service); db.session.flush()
    if service.name in {"Routine check-up · demo", "General health review"}:
        service.name, service.cost_label = "General health review", "No payment is collected"
    for email, name in [("sam.lee@example.test", "Dr. Samuel Lee"), ("maya.chen@example.test", "Dr. Maya Chen")]:
        doctor = ShareRecipient.query.filter_by(email=email).first()
        if not doctor:
            doctor = ShareRecipient(email=email, full_name=name, role="General practitioner", organisation=facility.name, verification_status="verified")
            db.session.add(doctor); db.session.flush()
        doctor.full_name, doctor.organisation = name, facility.name
        if not db.session.get(ServiceClinician, (service.id, doctor.id)):
            db.session.add(ServiceClinician(service_id=service.id, recipient_id=doctor.id))
    manager = ShareRecipient.query.filter_by(email="morgan@example.test").first()
    if manager:
        manager.full_name, manager.organisation = "Morgan Reed", "Cedar Wellness Centre"
    # A rolling week keeps old demo databases useful without deleting past bookings.
    for offset in range(1, 8):
        day = utc_now().date() + timedelta(days=offset)
        if day.weekday() >= 5:
            continue
        for hour in (16, 20):
            starts = datetime.combine(day, time(hour))
            if not AppointmentSlot.query.filter_by(service_id=service.id, starts_at=starts).first():
                db.session.add(AppointmentSlot(service_id=service.id, starts_at=starts, ends_at=starts + timedelta(minutes=service.duration_minutes), capacity=4))
    db.session.commit()
