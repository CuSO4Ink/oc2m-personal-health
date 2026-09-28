"""A small, coherent synthetic dataset. Only used by run_demo.py on a NEW database."""
from datetime import timedelta

from flask import current_app

from .extensions import db
from .models import (AccountProfile, AppointmentSlot, CommunityProfile, MedicalService,
                     ServiceFacility, ShareRecipient, User, utc_now)
from .community_models import CommunityIdentity

DEMO_PASSWORD = "HealthDemo2026!"
DEMO_ACCOUNTS = [
    {"email": "start@example.test", "name": "Taylor", "title": "Taylor · Start here", "description": "Start with an empty health folder and try syncing the hospital reports."},
    {"email": "alex@example.test", "name": "Alex", "title": "Alex · Community member", "description": "An empty health folder with an active community profile."},
    {"email": "jamie@example.test", "name": "Jamie", "title": "Jamie · Chat partner", "description": "Sign in in another browser to try friend requests and private messages."},
    {"email": "morgan@example.test", "name": "Morgan", "title": "Morgan · Community member", "description": "A separate account for exploring circles and conversations."},
    {"email": "riley@example.test", "name": "Riley", "title": "Riley · Community member", "description": "A separate account for exploring circles and conversations."},
    {"email": "casey@example.test", "name": "Casey", "title": "Casey · Community member", "description": "A separate account for exploring circles and conversations."},
]


def ensure_demo_accounts():
    """Create missing synthetic people without changing existing users or choices."""
    if not current_app.config.get("DEMO_DATASET"):
        return set()
    created = set()
    for item in DEMO_ACCOUNTS:
        if User.query.filter_by(email=item["email"]).first():
            continue
        user = User(full_name=item["name"], email=item["email"], role="patient")
        user.set_password(DEMO_PASSWORD)
        db.session.add(user)
        db.session.flush()
        social = item["email"] != "start@example.test"
        db.session.add(AccountProfile(user_id=user.id, preferred_language="English"))
        db.session.add(CommunityProfile(user_id=user.id, enabled=social))
        db.session.add(CommunityIdentity(user_id=user.id, nickname=item["name"], discoverable=social,
                                        invite_code=f"DEMO-{item['name'].upper()}"))
        created.add(user.id)
    db.session.flush()
    return created


def sample_report_pdf(report_date=None):
    """Minimal text PDF fixture, readable by PDF viewers and local text extraction."""
    report_date = report_date or (utc_now() - timedelta(days=1)).date()
    lines = ["PERSONAL HEALTH - SAMPLE REPORT", "Synthetic data for testing only", "",
             f"Report date: {report_date.isoformat()}", f"Measurement time: {report_date.isoformat()} 08:30", "Blood pressure: 124/78 mmHg",
             "Fasting blood glucose: 5.4 mmol/L", "Resting heart rate: 72 bpm", "",
             "Review the values, measurement date and context before importing.",
             "This sample is not a medical report or medical advice."]
    escaped_lines = [line.replace("(", "\\(").replace(")", "\\)") for line in lines]
    stream = "BT /F1 13 Tf 50 770 Td 24 TL\n" + "\n".join("(" + line + ") Tj T*" for line in escaped_lines) + "\nET"
    content = stream.encode("ascii")
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
               b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream"]
    pdf = b"%PDF-1.4\n"
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(pdf)); pdf += f"{number} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(pdf)
    pdf += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    pdf += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    pdf += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return pdf


def seed_usability_demo():
    if User.query.first():
        raise ValueError("The usability demo can only initialise an empty database.")
    now = utc_now().replace(second=0, microsecond=0)
    ensure_demo_accounts()
    from .demo_community_catalog import ensure_demo_community_catalog
    ensure_demo_community_catalog()
    db.session.add_all([ShareRecipient(full_name="Dr. Sam Lee · demo",role="General practitioner",organisation="Example Clinic",email="sam.lee@example.test",verification_status="verified"), ShareRecipient(full_name="Morgan · demo",role="Health manager",organisation="Example Wellness",email="morgan@example.test",verification_status="verified")])
    facility = ServiceFacility(name="Example Clinic · demonstration",address="Sample address",phone="Not connected",verified=False)
    db.session.add(facility);db.session.flush()
    service=MedicalService(facility_id=facility.id,name="Routine check-up · demo",specialty="General Practice",duration_minutes=20,cost_label="Demonstration only",appointment_mode="in_person")
    db.session.add(service);db.session.flush()
    for days in (2,4,7): db.session.add(AppointmentSlot(service_id=service.id,starts_at=now+timedelta(days=days),ends_at=now+timedelta(days=days,minutes=20),capacity=4))
    db.session.commit()
    from .demo_care_catalog import ensure_demo_care_catalog
    ensure_demo_care_catalog()
