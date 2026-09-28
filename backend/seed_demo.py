from app import create_app
from app.extensions import db
from datetime import date, datetime, timedelta
import sys

from app.models import AccessEvent, AccountProfile, Appointment, AppointmentSlot, CommunityCircle, CommunityComment, CommunityLike, CommunityMembership, CommunityPost, CommunityProfile, ElderCareListing, HealthAlert, HealthMeasurement, HealthRecord, HealthRecordVersion, HealthReminder, MedicalService, ServiceFacility, ShareGrant, ShareGrantRecord, ShareRecipient, User, utc_now


DEMO_EMAIL = "alex.morgan@example.com"
DEMO_PASSWORD = "HealthDemo2026!"


app = create_app()
with app.app_context():
    user = User.query.filter_by(email=DEMO_EMAIL).first()
    if not user:
        user = User(email=DEMO_EMAIL, full_name="Alex Morgan", role="patient")
        db.session.add(user)
        user.set_password(DEMO_PASSWORD)
    elif "--reset-demo-password" in sys.argv:
        user.set_password(DEMO_PASSWORD)
    db.session.flush()
    account_profile = db.session.get(AccountProfile, user.id)
    if not account_profile:
        db.session.add(AccountProfile(user_id=user.id, phone="+44 7700 900123", date_of_birth=date(1984, 6, 18), preferred_language="English"))
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
            offset = utc_now().date() - date(2026, 9, 15)
            record.record_date += offset
            if record.synced_at:
                record.synced_at += offset
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
            measured_at += utc_now().date() - date(2026, 9, 15)
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
    recipients = []
    recipient_rows = [
        ("Dr. Emily Chen", "General Practitioner", "Riverside Community Clinic", "emily.chen@example.test"),
        ("Dr. Samuel Malik", "Cardiologist", "City General Hospital", "samuel.malik@example.test"),
        ("Jordan Lee", "Health Manager", "Community Wellness Centre", "jordan.lee@example.test"),
    ]
    for full_name, role, organisation, email in recipient_rows:
        recipient = ShareRecipient.query.filter_by(email=email).first()
        if not recipient:
            recipient = ShareRecipient(full_name=full_name, role=role, organisation=organisation, email=email, verification_status="verified")
            db.session.add(recipient)
        recipients.append(recipient)
    db.session.flush()
    if not ShareGrant.query.filter_by(user_id=user.id).first():
        records = HealthRecord.query.filter_by(user_id=user.id).order_by(HealthRecord.id.asc()).all()
        active_grant = ShareGrant(
            user_id=user.id,
            recipient_id=recipients[0].id,
            starts_at=utc_now() - timedelta(days=5),
            expires_at=utc_now() + timedelta(days=5),
            allow_download=False,
            purpose="Follow-up consultation",
        )
        revoked_grant = ShareGrant(
            user_id=user.id,
            recipient_id=recipients[1].id,
            starts_at=utc_now() - timedelta(days=45),
            expires_at=utc_now() + timedelta(days=15),
            allow_download=True,
            purpose="Cardiology review",
            revoked_at=utc_now() - timedelta(days=28),
        )
        db.session.add_all([active_grant, revoked_grant])
        db.session.flush()
        for record in records[:3]:
            db.session.add(ShareGrantRecord(grant_id=active_grant.id, record_id=record.id))
        for record in records[:2]:
            db.session.add(ShareGrantRecord(grant_id=revoked_grant.id, record_id=record.id))
        db.session.flush()
        db.session.add_all([
            AccessEvent(user_id=user.id, grant_id=active_grant.id, record_id=records[0].id, action="view", result="allowed", location="Dundee, UK", occurred_at=datetime(2026, 9, 14, 14, 20)),
            AccessEvent(user_id=user.id, grant_id=active_grant.id, record_id=records[1].id, action="view", result="allowed", location="Dundee, UK", occurred_at=datetime(2026, 9, 12, 10, 5)),
            AccessEvent(user_id=user.id, grant_id=active_grant.id, record_id=records[0].id, action="download", result="blocked", location="Location unavailable", occurred_at=datetime(2026, 9, 14, 14, 22), unusual=True),
            AccessEvent(user_id=user.id, grant_id=revoked_grant.id, record_id=records[0].id, action="view", result="blocked", location="Dundee, UK", occurred_at=datetime(2026, 8, 19, 9, 10)),
        ])
    demo_now = utc_now().replace(second=0, microsecond=0)
    facility_rows = [
        ("Riverside Community Clinic", "18 Riverside Way, Dundee", "+44 1382 555 110"),
        ("City General Hospital", "1 Health Campus, Dundee", "+44 1382 555 220"),
    ]
    facilities = {}
    for name, address, phone in facility_rows:
        facility = ServiceFacility.query.filter_by(name=name).first()
        if not facility:
            facility = ServiceFacility(name=name, address=address, phone=phone, verified=True, updated_at=demo_now)
            db.session.add(facility)
        facilities[name] = facility
    db.session.flush()
    service_rows = [
        ("Riverside Community Clinic", "GP Follow-up", "General Practice", 20, "NHS covered"),
        ("City General Hospital", "Cardiology Consultation", "Cardiology", 30, "Referral may be required"),
        ("Riverside Community Clinic", "Health Management Review", "Preventive Care", 30, "NHS covered"),
    ]
    services = []
    for facility_name, name, specialty, duration, cost_label in service_rows:
        service = MedicalService.query.filter_by(facility_id=facilities[facility_name].id, name=name).first()
        if not service:
            service = MedicalService(facility_id=facilities[facility_name].id, name=name, specialty=specialty, duration_minutes=duration, cost_label=cost_label, appointment_mode="in_person")
            db.session.add(service)
        services.append(service)
    db.session.flush()
    for service_index, service in enumerate(services):
        if not AppointmentSlot.query.filter(AppointmentSlot.service_id == service.id, AppointmentSlot.starts_at > demo_now).first():
            for day_offset, hour in [(1 + service_index, 9), (2 + service_index, 11), (4 + service_index, 14)]:
                start = (demo_now + timedelta(days=day_offset)).replace(hour=hour, minute=0)
                db.session.add(AppointmentSlot(service_id=service.id, starts_at=start, ends_at=start + timedelta(minutes=service.duration_minutes), capacity=2, booked_count=0))
        db.session.flush()
    if not Appointment.query.filter_by(user_id=user.id).first():
        demo_slot = AppointmentSlot.query.join(AppointmentSlot.service).filter(MedicalService.name == "GP Follow-up", AppointmentSlot.starts_at > demo_now).order_by(AppointmentSlot.starts_at.asc()).first()
        if demo_slot and demo_slot.available_places > 0:
            demo_slot.booked_count += 1
            db.session.add(Appointment(user_id=user.id, slot_id=demo_slot.id, reason="Review recent home blood pressure readings", status="confirmed"))
    if not HealthReminder.query.filter_by(user_id=user.id).first():
        db.session.add_all([
            HealthReminder(user_id=user.id, title="Record morning blood pressure", category="measurement", next_due_at=demo_now + timedelta(hours=10), schedule_note="Twice each week", source_name="Personal reminder", notes="Rest for five minutes before measuring."),
            HealthReminder(user_id=user.id, title="Take Vitamin D", category="medication", next_due_at=demo_now - timedelta(hours=2), schedule_note="Every morning", source_name="Personal reminder"),
            HealthReminder(user_id=user.id, title="Prepare questions for GP visit", category="appointment", next_due_at=demo_now + timedelta(days=1), schedule_note="Before the appointment", source_name="Personal reminder"),
        ])
    elder_rows = [
        ("Dundee Community Day Centre", "Day support", "24 Community Road, Dundee", "Daytime social support, meals and wellbeing activities for older adults.", ["Day activities", "Lunch service", "Transport support"], "Step-free entrance and accessible toilets"),
        ("Riverside Home Support", "Home care", "Serving Dundee and nearby areas", "Scheduled assistance at home with daily living and wellbeing checks.", ["Personal care", "Meal support", "Wellbeing visits"], "Home assessment available"),
        ("Harbour Respite Centre", "Respite care", "7 Harbour Street, Dundee", "Short-stay respite information for individuals and family carers.", ["Short stays", "Carer support", "Nursing support"], "Wheelchair accessible rooms"),
    ]
    for name, category, address, summary, offered_services, accessibility in elder_rows:
        if not ElderCareListing.query.filter_by(name=name).first():
            db.session.add(ElderCareListing(name=name, category=category, address=address, summary=summary, services=offered_services, accessibility=accessibility, source_name="Demo local care directory", updated_at=demo_now, active=True))
    circle_rows = [
        ("Living Well with High Blood Pressure", "Blood pressure", "Share routines, questions to ask at appointments and everyday experiences of monitoring blood pressure."),
        ("Healthy Ageing Together", "Healthy ageing", "Exchange practical experiences about staying active, connected and independent."),
        ("Family Carer Support", "Carer wellbeing", "A peer space for family carers to discuss routines, respite and looking after their own wellbeing."),
    ]
    circles = []
    for name, topic, description in circle_rows:
        circle = CommunityCircle.query.filter_by(name=name).first()
        if not circle:
            circle = CommunityCircle(name=name, topic=topic, description=description)
            db.session.add(circle)
        circles.append(circle)
    db.session.flush()
    profile = db.session.get(CommunityProfile, user.id)
    if not profile:
        profile = CommunityProfile(user_id=user.id, enabled=True, joined_at=demo_now, updated_at=demo_now)
        db.session.add(profile)
    for circle in circles[:2]:
        membership = CommunityMembership.query.filter_by(user_id=user.id, circle_id=circle.id).first()
        if not membership:
            db.session.add(CommunityMembership(user_id=user.id, circle_id=circle.id, joined_at=demo_now))
    peer_rows = [
        ("community.peer.one@example.test", "Jamie Reed"),
        ("community.peer.two@example.test", "Morgan Hill"),
    ]
    peers = []
    for email, full_name in peer_rows:
        peer = User.query.filter_by(email=email).first()
        if not peer:
            peer = User(email=email, full_name=full_name, role="patient")
            peer.set_password("CommunityDemo2026!")
            db.session.add(peer)
        peers.append(peer)
    db.session.flush()
    for peer in peers:
        if not db.session.get(CommunityProfile, peer.id):
            db.session.add(CommunityProfile(user_id=peer.id, enabled=True, joined_at=demo_now, updated_at=demo_now))
        for circle in circles[:2]:
            if not CommunityMembership.query.filter_by(user_id=peer.id, circle_id=circle.id).first():
                db.session.add(CommunityMembership(user_id=peer.id, circle_id=circle.id, joined_at=demo_now))
    db.session.flush()
    if not CommunityPost.query.first():
        posts = [
            CommunityPost(circle_id=circles[0].id, user_id=peers[0].id, body="Keeping a short note beside my monitor helped me remember whether I had rested before each reading. I now bring the notes to appointments so I can explain the context.", anonymous=True, created_at=demo_now - timedelta(hours=5)),
            CommunityPost(circle_id=circles[1].id, user_id=peers[1].id, body="I started with a ten-minute walk at the same time each afternoon. Having a small, repeatable routine made it easier for me to stay active.", anonymous=False, created_at=demo_now - timedelta(days=1)),
            CommunityPost(circle_id=circles[0].id, user_id=user.id, body="I have been recording home readings twice a week and writing down anything unusual about the day. It makes my follow-up conversations much clearer.", anonymous=True, created_at=demo_now - timedelta(days=2)),
        ]
        db.session.add_all(posts)
        db.session.flush()
        db.session.add_all([
            CommunityLike(user_id=user.id, post_id=posts[0].id),
            CommunityComment(post_id=posts[0].id, user_id=peers[1].id, body="The context note helped me too, especially when my routine changed.", anonymous=True),
        ])
    own_post = CommunityPost.query.filter_by(user_id=user.id, status="published").first()
    if own_post and not CommunityComment.query.filter_by(post_id=own_post.id, user_id=peers[0].id).first():
        db.session.add(CommunityComment(post_id=own_post.id, user_id=peers[0].id, body="Writing down the context sounds useful. Thank you for sharing your experience.", anonymous=True, created_at=demo_now - timedelta(hours=23)))
    db.session.commit()
    print(f"Demo account ready: {DEMO_EMAIL}")
