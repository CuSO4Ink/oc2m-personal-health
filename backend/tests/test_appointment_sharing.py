from datetime import date, timedelta

import pytest

from app import create_app
from app.extensions import db
from app.models import Appointment, AppointmentSlot, HealthRecord, MedicalService, ServiceFacility, ShareGrant, ShareRecipient, utc_now
from app.service_models import AppointmentSharing, ServiceClinician
from app.demo_care_catalog import ensure_demo_care_catalog


@pytest.fixture
def care():
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:', 'DEMO_FEATURES_ENABLED': True})
    client = app.test_client()
    assert client.post('/api/auth/register', json={'full_name': 'Care Owner', 'email': 'care@example.test', 'password': 'Patient123'}).status_code == 201
    with app.app_context():
        clinic = ServiceFacility(name='Fictional clinic', address='128 Maple Avenue', verified=True)
        db.session.add(clinic); db.session.flush()
        service = MedicalService(facility_id=clinic.id, name='Review', specialty='General Practice')
        doctor = ShareRecipient(full_name='Dr. Lee', email='lee@example.test', role='Doctor', organisation=clinic.name)
        other = ShareRecipient(full_name='Other doctor', email='other@example.test', role='Doctor', organisation='Other clinic')
        db.session.add_all([service, doctor, other]); db.session.flush()
        db.session.add(ServiceClinician(service_id=service.id, recipient_id=doctor.id))
        for offset, capacity, booked in [(1, 2, 0), (2, 2, 0), (-1, 2, 0), (3, 1, 1)]:
            start = utc_now() + timedelta(days=offset)
            db.session.add(AppointmentSlot(service_id=service.id, starts_at=start, ends_at=start + timedelta(minutes=20), capacity=capacity, booked_count=booked))
        db.session.add(HealthRecord(user_id=1, title='Selected report', record_type='Lab Report', record_date=date.today(), source_type='self', content='Summary', version=1))
        db.session.commit()
    return app, client


def draft(client):
    payload = {'recipient_id': 1, 'record_ids': [1], 'shared_fields': ['title', 'content'], 'purpose': 'Follow-up review', 'starts_at': (utc_now() - timedelta(minutes=1)).isoformat(), 'expires_at': (utc_now() + timedelta(days=7)).isoformat()}
    response = client.post('/api/sharing/grants/draft-preview', json=payload)
    assert response.status_code == 200, response.get_json()
    return {**payload, 'preview_token': response.get_json()['preview_token']}


def test_catalogue_and_booking_agree_on_future_available_slots(care):
    _, client = care
    services = client.get('/api/services/medical').get_json()['services']
    assert [slot['id'] for slot in services[0]['slots']] == [1, 2]
    assert [person['id'] for person in services[0]['clinicians']] == [1]
    assert client.post('/api/services/appointments', json={'slot_id': 3, 'recipient_id': 1, 'reason': 'Follow-up'}).status_code == 409
    assert client.post('/api/services/appointments', json={'slot_id': 4, 'recipient_id': 1, 'reason': 'Follow-up'}).status_code == 409
    assert client.post('/api/services/appointments', json={'slot_id': 1, 'recipient_id': 2, 'reason': 'Follow-up'}).status_code == 400
    response = client.post('/api/services/appointments', json={'slot_id': 1, 'recipient_id': 1, 'reason': 'Follow-up'})
    assert response.status_code == 201
    assert response.get_json()['appointment']['clinician']['id'] == 1
    assert response.get_json()['appointment']['sharing'] is None


def test_booking_and_fixed_scope_share_are_atomic_and_cancel_revokes(care):
    app, client = care
    scope = draft(client)
    invalid = client.post('/api/services/appointments', json={'slot_id': 1, 'recipient_id': 1, 'reason': 'Follow-up', 'sharing_draft': {**scope, 'preview_token': 'stale'}})
    assert invalid.status_code == 409
    with app.app_context():
        assert db.session.get(AppointmentSlot, 1).booked_count == 0
        assert Appointment.query.count() == ShareGrant.query.count() == 0
    response = client.post('/api/services/appointments', json={'slot_id': 1, 'recipient_id': 1, 'reason': 'Follow-up', 'sharing_draft': scope})
    assert response.status_code == 201, response.get_json()
    appointment = response.get_json()['appointment']
    grant_id = appointment['sharing']['grant_id']
    preview = client.post(f'/api/sharing/grants/{grant_id}/preview').get_json()
    assert preview['records'] == [{'title': 'Selected report', 'content': 'Summary'}]
    with app.app_context():
        db.session.get(HealthRecord, 1).content = 'New unshared text'
        db.session.commit()
    assert client.patch(f"/api/services/appointments/{appointment['id']}/reschedule", json={'slot_id': 2, 'expected_slot_id': 1}).status_code == 200
    with app.app_context():
        link = db.session.get(AppointmentSharing, appointment['id'])
        assert link.grant_id == grant_id
        assert link.grant.expires_at.isoformat() == scope['expires_at']
    assert client.post(f'/api/sharing/grants/{grant_id}/preview').get_json()['records'][0]['content'] == 'Summary'
    assert client.patch(f"/api/services/appointments/{appointment['id']}/cancel").get_json()['appointment']['sharing']['status'] == 'revoked'
    assert client.post(f'/api/sharing/grants/{grant_id}/preview').status_code == 403


def test_foreign_recipient_and_foreign_record_cannot_be_shared_during_booking(care):
    app, client = care
    scope = draft(client)
    for changed in [{**scope, 'recipient_id': 2}, {**scope, 'record_ids': [999]}, {**scope, 'preview_token': None}]:
        assert client.post('/api/services/appointments', json={'slot_id': 1, 'recipient_id': 1, 'reason': 'Follow-up', 'sharing_draft': changed}).status_code in {400, 409}
    with app.app_context():
        assert Appointment.query.count() == ShareGrant.query.count() == 0
        assert db.session.get(AppointmentSlot, 1).booked_count == 0


def test_demo_catalogue_is_opt_in_idempotent_and_old_bookings_survive(care):
    app, client = care
    assert client.post('/api/services/appointments', json={'slot_id': 1, 'recipient_id': 1, 'reason': 'Follow-up'}).status_code == 201
    with app.app_context():
        ensure_demo_care_catalog()
        assert MedicalService.query.count() == 1
        app.config['DEMO_DATASET'] = True
        ensure_demo_care_catalog()
        counts = (MedicalService.query.count(), AppointmentSlot.query.count(), ShareRecipient.query.count())
        ensure_demo_care_catalog()
        assert counts == (MedicalService.query.count(), AppointmentSlot.query.count(), ShareRecipient.query.count())
        assert Appointment.query.count() == 1
    catalogue = client.get('/api/services/medical').get_json()['services']
    local = next(service for service in catalogue if service['facility']['name'] == 'Maple Grove Family Clinic')
    assert local['facility']['address'] == '128 Maple Avenue, Brookfield'
    result = client.post('/api/services/appointments', json={'slot_id': local['slots'][0]['id'], 'recipient_id': local['clinicians'][0]['id'], 'reason': 'Review results'})
    assert result.status_code == 201, result.get_json()
