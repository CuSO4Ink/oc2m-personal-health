from app import create_app
from app.extensions import db
from datetime import date, datetime

from app.models import HealthRecord, HealthRecordVersion, User


DEMO_EMAIL = "alex.morgan@example.com"
DEMO_PASSWORD = "HealthDemo2026!"


app = create_app()
with app.app_context():
    user = User.query.filter_by(email=DEMO_EMAIL).first()
    if not user:
        user = User(email=DEMO_EMAIL, full_name="Alex Morgan", role="patient")
        db.session.add(user)
    user.set_password(DEMO_PASSWORD)
    db.session.flush()
    if not HealthRecord.query.filter_by(user_id=user.id).first():
        demo_records = [
            HealthRecord(
                user_id=user.id,
                title="Annual Blood Test",
                record_type="Lab Report",
                condition="Routine health screening",
                record_date=date(2026, 9, 11),
                source_type="hospital",
                source_name="City General Hospital",
                content="Complete blood count and metabolic panel. Results were within the reference range. Continue routine annual monitoring.",
                synced_at=datetime(2026, 9, 11, 10, 20),
            ),
            HealthRecord(
                user_id=user.id,
                title="Follow-up Consultation",
                record_type="Visit Summary",
                condition="Blood pressure follow-up",
                record_date=date(2026, 9, 8),
                source_type="hospital",
                source_name="Riverside Community Clinic",
                content="Blood pressure remains stable. Continue current lifestyle plan and record home readings twice each week.",
                synced_at=datetime(2026, 9, 8, 16, 45),
            ),
            HealthRecord(
                user_id=user.id,
                title="Penicillin Allergy",
                record_type="Allergy",
                condition="Medication allergy",
                record_date=date(2024, 5, 18),
                source_type="self",
                source_name="Self-reported",
                content="Developed a widespread itchy rash after taking penicillin. Avoid penicillin until reviewed by an allergy specialist.",
            ),
            HealthRecord(
                user_id=user.id,
                title="Daily Vitamin D",
                record_type="Medication",
                condition="Supplement",
                record_date=date(2026, 8, 20),
                source_type="self",
                source_name="Self-reported",
                content="Vitamin D3, 1,000 IU once daily with breakfast.",
            ),
        ]
        for record in demo_records:
            db.session.add(record)
            db.session.flush()
            db.session.add(HealthRecordVersion(
                record_id=record.id,
                version=1,
                snapshot={
                    "title": record.title,
                    "record_type": record.record_type,
                    "condition": record.condition,
                    "record_date": record.record_date.isoformat(),
                    "source_name": record.source_name,
                    "content": record.content,
                },
                changed_by="System import" if record.source_type == "hospital" else user.full_name,
                change_note="Imported from provider" if record.source_type == "hospital" else "Record created",
            ))
    db.session.commit()
    print(f"Demo account ready: {DEMO_EMAIL}")
