from copy import deepcopy
from datetime import date, timedelta

import pytest

from app import create_app
from app.extensions import db
from app.models import HealthMeasurement, HealthRecord, RecordAttachment, ShareGrant, ShareGrantRecord, ShareFieldSettings, ShareRecipient, utc_now
from app.record_models import PersonalHealthProfile, RecordPrivacy, RecordLifecycle, empty_sections
from app.sharing_models import ShareScopeSnapshot
from app.insight_models import MeasurementDisposition


@pytest.fixture
def sharing():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "DEMO_FEATURES_ENABLED": True})
    client = app.test_client()
    assert client.post('/api/auth/register', json={"full_name": "Sharing Owner", "email": "scopes@example.test", "password": "Patient123"}).status_code == 201
    with app.app_context():
        db.session.add(ShareRecipient(full_name="Demo clinician", role="Doctor", organisation="Demo clinic", email="demo-clinician@example.test"))
        record = HealthRecord(user_id=1, title="Checkup", record_type="Lab Report", record_date=date.today(), source_type="self", source_name="Demo clinic", content="Reviewed summary only", condition="Routine", version=1)
        db.session.add(record); db.session.flush()
        db.session.add(RecordAttachment(record_id=record.id, filename="original.pdf", content_type="application/pdf", size=25, data=b"%PDF-1.4\nORIGINAL MEDICAL DOCUMENT"))
        sections = empty_sections()
        sections['allergies'] = {"status": "recorded", "items": [{"id": "pollen", "name": "Pollen", "detail": "Old details", "sensitive": False}, {"id": "hidden", "name": "PRIVATE HISTORY", "sensitive": True}]}
        db.session.add(PersonalHealthProfile(user_id=1, revision=2, sections=sections))
        db.session.add(HealthMeasurement(user_id=1, metric_type="heart_rate", value=72, unit="bpm", context="resting", measured_at=utc_now(), notes="PRIVATE MEASUREMENT NOTE"))
        db.session.commit()
    return app, client


def payload(**values):
    return {"recipient_id": 1, "record_ids": [], "starts_at": (utc_now() - timedelta(minutes=1)).isoformat(),
            "expires_at": (utc_now() + timedelta(days=1)).isoformat(), **values}


def create(client, **values):
    result = client.post('/api/sharing/grants', json=payload(**values))
    assert result.status_code == 201, result.get_json()
    return result.get_json()['grant']['id']


def test_files_require_explicit_choice_and_acknowledgement_and_cannot_expand(sharing):
    app, client = sharing
    assert client.post('/api/sharing/grants', json=payload(attachment_ids=[1])).status_code == 400
    identifier = create(client, attachment_ids=[1], acknowledge_original_files=True)
    preview = client.post(f'/api/sharing/grants/{identifier}/preview').get_json()
    assert preview['records'] == [] and preview['attachments'][0]['filename'] == 'original.pdf'
    assert preview['attachments'][0]['download_url'] is None
    response = client.get(preview['attachments'][0]['preview_url'])
    assert response.status_code == 200 and b'ORIGINAL MEDICAL DOCUMENT' in response.data
    assert response.headers['Cache-Control'] == 'private, no-store'
    assert client.get(f'/api/sharing/grants/{identifier}/attachments/1?download=1').status_code == 403
    with app.app_context():
        db.session.add(RecordAttachment(record_id=1, filename="new.pdf", content_type="application/pdf", size=10, data=b"UNSELECTED SECRET")); db.session.commit()
    denied = client.get(f'/api/sharing/grants/{identifier}/attachments/2')
    assert denied.status_code == 403 and b'UNSELECTED SECRET' not in denied.data
    assert len(client.post(f'/api/sharing/grants/{identifier}/preview').get_json()['attachments']) == 1


@pytest.mark.parametrize('state', ['revoked', 'expired', 'scheduled', 'wrong_recipient'])
def test_file_permission_state_never_returns_bytes(sharing, state):
    app, client = sharing
    identifier = create(client, attachment_ids=[1], acknowledge_original_files=True, allow_download=True)
    with app.app_context():
        grant = db.session.get(ShareGrant, identifier)
        if state == 'revoked': grant.revoked_at = utc_now()
        if state == 'expired': grant.expires_at = utc_now() - timedelta(seconds=1)
        if state == 'scheduled': grant.starts_at = utc_now() + timedelta(days=1)
        db.session.commit()
    query = '?mode=simulation&download=1' + ('&recipient_id=99' if state == 'wrong_recipient' else '')
    denied = client.get(f'/api/sharing/grants/{identifier}/attachments/1{query}')
    assert denied.status_code == 403 and b'ORIGINAL MEDICAL' not in denied.data
    event = client.get('/api/sharing/access-events').get_json()['events'][0]
    assert event['event_kind'] == 'scope' and event['result'] == 'blocked'


@pytest.mark.parametrize('change', ['sensitive', 'hidden_field', 'archive', 'changed_bytes', 'deleted'])
def test_file_privacy_and_identity_rechecked_at_every_request(sharing, change):
    app, client = sharing
    identifier = create(client, attachment_ids=[1], acknowledge_original_files=True, allow_download=True)
    with app.app_context():
        if change == 'sensitive': db.session.add(RecordPrivacy(record_id=1, sensitive=True))
        if change == 'hidden_field': db.session.add(RecordPrivacy(record_id=1, sensitive_fields=['condition']))
        if change == 'archive': db.session.add(RecordLifecycle(record_id=1, archived_at=utc_now()))
        if change == 'changed_bytes': db.session.get(RecordAttachment, 1).data = b'REPLACEMENT SECRET'
        if change == 'deleted': db.session.delete(db.session.get(RecordAttachment, 1))
        db.session.commit()
    denied = client.get(f'/api/sharing/grants/{identifier}/attachments/1?download=1')
    assert denied.status_code == 403 and b'ORIGINAL MEDICAL' not in denied.data and b'REPLACEMENT SECRET' not in denied.data


def test_profile_and_records_are_fixed_snapshots_but_current_sensitivity_revokes(sharing):
    app, client = sharing
    identifier = create(client, record_ids=[1], shared_fields=['content'], profile_sections=['allergies'])
    with app.app_context():
        db.session.get(HealthRecord, 1).content = 'FUTURE OCR MUST NOT LEAK'
        profile = db.session.get(PersonalHealthProfile, 1)
        sections = deepcopy(profile.sections)
        sections['allergies']['items'][0]['detail'] = 'FUTURE PROFILE DETAILS'
        sections['allergies']['items'].append({"id": "new", "name": "FUTURE HISTORY"})
        profile.sections = sections; profile.revision += 1; db.session.commit()
    visible = client.post(f'/api/sharing/grants/{identifier}/preview').get_json()
    assert visible['records'] == [{'content': 'Reviewed summary only'}]
    assert visible['profile'][0]['revision'] == 2 and len(visible['profile'][0]['items']) == 1
    assert visible['profile'][0]['items'][0]['detail'] == 'Old details'
    assert 'PRIVATE HISTORY' not in str(visible) and 'FUTURE' not in str(visible)
    with app.app_context():
        profile = db.session.get(PersonalHealthProfile, 1); sections = deepcopy(profile.sections)
        sections['allergies']['items'][0]['sensitive'] = True; profile.sections = sections; db.session.commit()
    assert client.post(f'/api/sharing/grants/{identifier}/preview').get_json()['profile'] == []


def test_specific_profile_items_and_dates_are_validated_without_record_requirement(sharing):
    app, client = sharing
    identifier = create(client, profile_items=[{'section': 'allergies', 'item_id': 'pollen'}])
    assert client.post(f'/api/sharing/grants/{identifier}/preview').get_json()['profile'][0]['items'][0]['name'] == 'Pollen'
    assert client.post('/api/sharing/grants', json=payload(profile_items=[{'section': 'allergies', 'item_id': 'hidden'}])).status_code == 400
    assert client.post('/api/sharing/grants', json=payload(measurement_ids=[1])).status_code == 400
    today = utc_now().date().isoformat()
    identifier = create(client, measurement_ids=[1], measurement_period={'from': today, 'to': today})
    preview = client.post(f'/api/sharing/grants/{identifier}/preview').get_json()
    assert preview['measurements'][0]['value'] == 72 and 'PRIVATE MEASUREMENT NOTE' not in str(preview)
    with app.app_context():
        db.session.add(MeasurementDisposition(measurement_id=1, reason='Wrong reading')); db.session.commit()
    assert client.post(f'/api/sharing/grants/{identifier}/preview').status_code == 403
    assert client.get(f'/api/sharing/scope-options?from={today}&to={today}').get_json()['measurements'] == []


def test_preview_token_stops_changed_content_and_new_grant_does_not_share_ocr_text(sharing):
    app, client = sharing
    request = payload(record_ids=[1], shared_fields=['content'])
    preview = client.post('/api/sharing/grants/draft-preview', json=request).get_json()
    with app.app_context():
        db.session.get(HealthRecord, 1).content = 'Changed after preview'; db.session.commit()
    denied = client.post('/api/sharing/grants', json={**request, 'preview_token': preview['preview_token']})
    assert denied.status_code == 409
    with app.app_context(): assert ShareGrant.query.count() == 0


def test_hidden_fields_prevent_original_pdf_and_old_grants_do_not_gain_files(sharing):
    app, client = sharing
    with app.app_context():
        db.session.add(RecordPrivacy(record_id=1, sensitive_fields=['condition'])); db.session.commit()
    assert client.post('/api/sharing/grants', json=payload(attachment_ids=[1], acknowledge_original_files=True)).status_code == 400
    identifier = create(client, record_ids=[1], shared_fields=['title'])
    with app.app_context():
        db.session.delete(db.session.get(ShareScopeSnapshot, identifier)); db.session.commit()
    old = client.post(f'/api/sharing/grants/{identifier}/preview').get_json()
    assert old['attachments_included'] is False and 'attachments' not in old
    assert client.get(f'/api/sharing/grants/{identifier}/attachments/1').status_code == 403


def test_owner_preview_audit_recipient_file_audit_review_and_cross_account_isolation(sharing):
    app, client = sharing
    identifier = create(client, attachment_ids=[1], acknowledge_original_files=True, allow_download=True)
    assert client.get(f'/api/sharing/grants/{identifier}/attachments/1').status_code == 200
    assert client.get('/api/sharing/access-events').get_json()['total'] == 0
    assert client.get(f'/api/sharing/grants/{identifier}/attachments/1?mode=simulation&download=1').status_code == 200
    event = client.get('/api/sharing/access-events?action=download&review=pending').get_json()['events'][0]
    assert event['event_kind'] == 'scope' and event['source'] == 'mock'
    assert client.patch(f"/api/sharing/scope-events/{event['id']}/review").get_json()['event']['reviewed_at']
    actions = {item['action'] for item in client.get('/api/sharing/audit-events').get_json()['events']}
    assert {'shared_file_owner_preview', 'shared_file_access', 'access_reviewed'}.issubset(actions)
    client.post('/api/auth/logout')
    client.post('/api/auth/register', json={"full_name": "Other", "email": "other-scope@example.test", "password": "Patient123"})
    assert client.get(f'/api/sharing/grants/{identifier}/attachments/1?mode=simulation').status_code == 404
    assert client.patch(f"/api/sharing/scope-events/{event['id']}/review").status_code == 404
    assert client.post('/api/sharing/grants', json=payload(attachment_ids=[1], acknowledge_original_files=True)).status_code == 400
    assert client.get('/api/sharing/access-events').get_json()['total'] == 0
    assert client.get('/api/sharing/audit-events').get_json()['total'] == 0
