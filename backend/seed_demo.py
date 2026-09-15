from app import create_app
from app.extensions import db
from datetime import date, datetime

from app.models import HealthAlert, HealthMeasurement, HealthRecord, HealthRecordVersion, User


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
    if not HealthMeasurement.query.filter_by(user_id=user.id).first():
        measurement_rows = [
            ("blood_pressure", 126, 79, "", datetime(2026, 8, 20, 8, 15), "Connected blood pressure monitor"),
            ("blood_pressure", 129, 81, "", datetime(2026, 8, 25, 8, 10), "Connected blood pressure monitor"),
            ("blood_pressure", 128, 80, "", datetime(2026, 9, 1, 8, 20), "Connected blood pressure monitor"),
            ("blood_pressure", 146, 92, "", datetime(2026, 9, 3, 19, 5), "Manual entry"),
            ("blood_pressure", 132, 84, "", datetime(2026, 9, 5, 8, 12), "Connected blood pressure monitor"),
            ("blood_pressure", 128, 78, "", datetime(2026, 9, 8, 8, 25), "Connected blood pressure monitor"),
            ("blood_pressure", 120, 80, "", datetime(2026, 9, 11, 8, 30), "Manual entry"),
            ("blood_pressure", 124, 78, "", datetime(2026, 9, 15, 8, 20), "Connected blood pressure monitor"),
            ("blood_glucose", 5.7, None, "fasting", datetime(2026, 8, 21, 7, 10), "Manual entry"),
            ("blood_glucose", 5.5, None, "fasting", datetime(2026, 8, 28, 7, 12), "Manual entry"),
            ("blood_glucose", 5.8, None, "fasting", datetime(2026, 9, 4, 7, 9), "Connected glucose meter"),
            ("blood_glucose", 5.4, None, "fasting", datetime(2026, 9, 10, 7, 15), "Connected glucose meter"),
            ("blood_glucose", 5.6, None, "fasting", datetime(2026, 9, 15, 7, 15), "Connected glucose meter"),
            ("heart_rate", 70, None, "resting", datetime(2026, 8, 22, 8, 35), "Connected wearable"),
            ("heart_rate", 73, None, "resting", datetime(2026, 8, 29, 8, 32), "Connected wearable"),
            ("heart_rate", 71, None, "resting", datetime(2026, 9, 5, 8, 40), "Connected wearable"),
            ("heart_rate", 72, None, "resting", datetime(2026, 9, 11, 8, 35), "Connected wearable"),
            ("heart_rate", 74, None, "resting", datetime(2026, 9, 15, 8, 30), "Connected wearable"),
        ]
        abnormal_bp = None
        for metric_type, value, secondary_value, context, measured_at, source_name in measurement_rows:
            unit = {"blood_pressure": "mmHg", "blood_glucose": "mmol/L", "heart_rate": "bpm"}[metric_type]
            measurement = HealthMeasurement(
                user_id=user.id,
                metric_type=metric_type,
                value=value,
                secondary_value=secondary_value,
                unit=unit,
                context=context,
                measured_at=measured_at,
                source_type="device" if source_name.startswith("Connected") else "self",
                source_name=source_name,
            )
            db.session.add(measurement)
            if metric_type == "blood_pressure" and value == 146:
                abnormal_bp = measurement
        db.session.flush()
        db.session.add(HealthAlert(
            user_id=user.id,
            measurement_id=abnormal_bp.id,
            severity="high",
            title="Blood Pressure reading needs attention",
            message="A 146/92 mmHg reading matched the current high threshold. Review the context and seek professional advice if you are concerned.",
            rule_name="blood_pressure_reference_threshold",
            rule_version="1.0",
        ))
    db.session.commit()
    print(f"Demo account ready: {DEMO_EMAIL}")
