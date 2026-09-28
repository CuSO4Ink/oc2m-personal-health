from datetime import date, timedelta
import pytest

from app import create_app
from app.extensions import db
from app.models import AccountProfile, AccessEvent, HealthAlert, HealthMeasurement, ShareGrant, ShareRecipient, utc_now
from app.record_models import RecordPrivacy, RecordLifecycle
from app.insight_models import MeasurementDisposition


@pytest.fixture
def setup():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "DEMO_FEATURES_ENABLED": True})
    client = app.test_client()
    assert client.post('/api/auth/register', json={"full_name": "Health Owner", "email": "owner@health.test", "password": "Patient123"}).status_code == 201
    with app.app_context():
        profile = db.session.get(AccountProfile, 1)
        if not profile:
            profile = AccountProfile(user_id=1)
            db.session.add(profile)
        profile.date_of_birth = date(1980, 1, 1)
        recipient = ShareRecipient(full_name="Mock Doctor", role="Doctor", organisation="Demonstration", email="mock@directory.test")
        db.session.add(recipient); db.session.commit()
    return app, client


def record_and_grant(client, **overrides):
    record = client.post('/api/records', json={"title": "Private title", "record_type": "Other", "record_date": date.today().isoformat(), "content": "SECRET CLINICAL CONTENT", "condition": "Sensitive condition"}).get_json()['record']
    payload = {"recipient_id": 1, "record_ids": [record['id']], "starts_at": (utc_now() - timedelta(minutes=1)).isoformat(), "expires_at": (utc_now() + timedelta(days=1)).isoformat(), **overrides}
    created = client.post('/api/sharing/grants', json=payload)
    assert created.status_code == 201, created.get_json()
    return record, created.get_json()['grant'], payload


def test_actual_preview_default_exclusion_and_mock_field_export(setup):
    app, client = setup
    record, grant, payload = record_and_grant(client)
    draft = client.post('/api/sharing/grants/draft-preview', json=payload).get_json()
    assert draft['records'][0]['title'] == record['title']
    assert 'SECRET CLINICAL' not in str(draft)
    assert client.post(f"/api/sharing/grants/{grant['id']}/preview").status_code == 200
    assert client.get('/api/sharing/access-events').get_json()['total'] == 0
    denied = client.post(f"/api/sharing/grants/{grant['id']}/simulate-access", json={"action": "download"})
    assert denied.status_code == 403 and 'records' not in denied.get_json()
    assert 'Private title' not in denied.get_data(as_text=True)
    response = client.post(f"/api/sharing/grants/{grant['id']}/simulate-access")
    assert response.get_json()['mode'] == 'mock'
    assert 'email' not in str(response.get_json())
    with app.app_context():
        db.session.get(ShareGrant, grant['id']).allow_download = True
        db.session.commit()
    exported = client.post(f"/api/sharing/grants/{grant['id']}/simulate-access", json={"action": "download"})
    assert exported.status_code == 200 and 'attachment;' in exported.headers['Content-Disposition']
    assert exported.get_json()['attachments_included'] is False
    assert set(exported.get_json()['records'][0]) == {'title', 'record_type', 'record_date', 'source_name'}
    events = client.get('/api/sharing/access-events?page_size=1&page=2').get_json()
    assert events['total'] == 3 and len(events['events']) == 1
    assert events['events'][0]['source'] == 'mock'


def test_dynamic_privacy_exclusion_and_identity_isolation(setup):
    app, client = setup
    record, grant, payload = record_and_grant(client, shared_fields=['title', 'content'])
    with app.app_context():
        db.session.add(RecordPrivacy(record_id=record['id'], sensitive_fields=['content'])); db.session.commit()
    path = f"/api/sharing/grants/{grant['id']}/simulate-access"
    assert client.post(path).get_json()['records'] == [{'title': 'Private title'}]
    with app.app_context():
        db.session.get(RecordPrivacy, record['id']).sensitive = True; db.session.commit()
    assert client.post(path).status_code == 403
    assert client.post('/api/sharing/grants/draft-preview', json=payload).status_code == 400
    with app.app_context():
        db.session.get(RecordPrivacy, record['id']).sensitive = False
        db.session.add(RecordLifecycle(record_id=record['id'], archived_at=utc_now())); db.session.commit()
    assert client.post(path).status_code == 403
    client.post('/api/auth/logout')
    client.post('/api/auth/register', json={"full_name": "Other Owner", "email": "other@health.test", "password": "Patient123"})
    assert client.post(path).status_code == 404
    assert client.get('/api/sharing/access-events').get_json()['total'] == 0
    assert client.get('/api/sharing/audit-events').get_json()['total'] == 0


@pytest.mark.parametrize('state', ['expired', 'scheduled', 'revoked', 'wrong_recipient'])
def test_permission_state_denials_never_return_content(setup, state):
    app, client = setup
    _, grant, _ = record_and_grant(client, shared_fields=['content'])
    with app.app_context():
        saved = db.session.get(ShareGrant, grant['id'])
        if state == 'expired': saved.expires_at = utc_now() - timedelta(seconds=1)
        if state == 'scheduled': saved.starts_at = utc_now() + timedelta(hours=1)
        if state == 'revoked': saved.revoked_at = utc_now()
        db.session.commit()
    response = client.post(f"/api/sharing/grants/{grant['id']}/simulate-access", json={"recipient_id": 999} if state == 'wrong_recipient' else {})
    assert response.status_code == 403
    assert 'records' not in response.get_json() and 'SECRET' not in response.get_data(as_text=True)
    assert client.get('/api/sharing/access-events').get_json()['events'][0]['result'] == 'blocked'


def test_simulation_disabled_has_no_side_effect(setup):
    app, client = setup
    _, grant, _ = record_and_grant(client)
    app.config['DEMO_FEATURES_ENABLED'] = False
    assert client.post(f"/api/sharing/grants/{grant['id']}/simulate-access").status_code == 503
    assert client.post(f"/api/sharing/grants/{grant['id']}/preview").status_code == 200
    assert client.get('/api/sharing/access-events').get_json()['total'] == 0


def add_reading(client, **values):
    return client.post('/api/insights/metrics', json={"metric_type": "blood_pressure", "value": 150, "secondary_value": 55, "measured_at": utc_now().isoformat(), **values})


def test_multiple_flags_correction_and_void_keep_original_alert(setup):
    app, client = setup
    result = add_reading(client).get_json()
    original = result['measurement']; original_alert = result['alert']
    assert original['status'] == 'high' and set(original['flags']) == {'high', 'low'}
    corrected = client.patch(f"/api/insights/metrics/{original['id']}", json={"value": 118, "secondary_value": 78, "reason": "Transcription correction"})
    assert corrected.status_code == 200
    replacement = corrected.get_json()['measurement']
    assert replacement['status'] == 'in_range'
    assert client.get('/api/insights/metrics').get_json()['summary']['count'] == 1
    assert client.get('/api/insights/alerts').get_json()['alerts'] == []
    history = client.get('/api/insights/alerts?status=all').get_json()['alerts']
    assert history[0]['id'] == original_alert['id'] and history[0]['measurement']['value'] == 150
    assert history[0]['acknowledged_at'] is None and history[0]['disposition']['status'] == 'corrected'
    assert client.patch(f"/api/insights/metrics/{original['id']}", json={"reason": "Again"}).status_code == 409
    assert client.post(f"/api/insights/metrics/{replacement['id']}/void", json={"reason": "Duplicate"}).status_code == 200
    data = client.get('/api/insights/metrics').get_json()
    assert data['summary']['count'] == 0 and len(data['superseded_readings']) == 2
    with app.app_context():
        assert db.session.get(HealthMeasurement, original['id']).value == 150
        assert db.session.get(HealthAlert, original_alert['id']).measurement_id == original['id']
        assert MeasurementDisposition.query.count() == 2


@pytest.mark.parametrize('birth,context,reason', [(None, 'general', 'age_unknown'), (date(2015, 1, 1), 'general', 'under_18_at_measurement'), (date(1980, 1, 1), 'pregnancy', 'special_context_requires_professional_review')])
def test_age_and_special_context_protection(setup, birth, context, reason):
    app, client = setup
    with app.app_context():
        db.session.get(AccountProfile, 1).date_of_birth = birth; db.session.commit()
    result = add_reading(client, special_context=context).get_json()
    assert result['measurement']['status'] == 'not_assessed'
    assert result['measurement']['assessment']['reason'] == reason
    assert result['alert'] is None


def test_mixed_context_local_dates_and_owner_only_corrections(setup):
    app, client = setup
    for days, context in [(2, 'fasting'), (1, 'after_meal'), (0, 'fasting')]:
        added = add_reading(client, metric_type='blood_glucose', value=5, context=context, measured_at=(utc_now() - timedelta(days=days)).isoformat())
        assert added.status_code == 201
    data = client.get('/api/insights/metrics?metric=blood_glucose&timezone_offset_minutes=420').get_json()
    assert data['data_sufficiency']['status'] == 'mixed_context'
    assert data['summary']['average'] is None and data['trend'] is None
    reading = data['readings'][0]
    client.post('/api/auth/logout')
    client.post('/api/auth/register', json={"full_name": "Other Reader", "email": "reader@health.test", "password": "Patient123"})
    assert client.patch(f"/api/insights/metrics/{reading['id']}", json={"reason": "Other"}).status_code == 404
    assert client.post(f"/api/insights/metrics/{reading['id']}/void", json={"reason": "Other"}).status_code == 404


def test_local_date_sufficiency_and_read_only_provider_reading(setup):
    app, client = setup
    anchor = (utc_now() - timedelta(days=4)).replace(hour=0, minute=0, second=0, microsecond=0)
    for time in [anchor + timedelta(hours=23), anchor + timedelta(days=1, hours=1), anchor + timedelta(days=2, hours=23)]:
        assert add_reading(client, measured_at=time.isoformat()).status_code == 201
    utc = client.get('/api/insights/metrics?timezone_offset_minutes=0').get_json()
    local = client.get('/api/insights/metrics?timezone_offset_minutes=420').get_json()
    assert utc['summary']['distinct_days'] == 3
    assert local['summary']['distinct_days'] == 2 and local['data_sufficiency']['status'] == 'limited'
    with app.app_context():
        item = HealthMeasurement.query.first(); item.source_type = 'device'; identifier = item.id; db.session.commit()
    assert client.patch(f'/api/insights/metrics/{identifier}', json={'reason': 'Device edit'}).status_code == 403
    assert client.post(f'/api/insights/metrics/{identifier}/void', json={'reason': 'Device void'}).status_code == 403


def set_focus_profile(app, **sections):
    from app.record_models import PersonalHealthProfile, empty_sections
    with app.app_context():
        profile = db.session.get(PersonalHealthProfile, 1)
        if not profile:
            profile = PersonalHealthProfile(user_id=1)
            db.session.add(profile)
        profile.sections = {**empty_sections(), **sections}
        profile.revision = 7
        db.session.commit()


def test_health_focus_matches_explicit_names_and_combines_traceable_readings(setup):
    app, client = setup
    set_focus_profile(app, family_history={"status": "recorded", "items": [{"id": "family-bp", "name": "高血压"}, {"id": "family-glucose", "name": " Type 2 Diabetes "}]},
                      past_history={"status": "recorded", "items": [{"id": "own-bp", "name": "Hypertension"}]})
    reading_ids = [add_reading(client, secondary_value=95, measured_at=(utc_now() - timedelta(days=day)).isoformat()).get_json()['measurement']['id'] for day in [2, 1]]
    data = client.get('/api/insights/metrics').get_json()
    cards = data['health_focus']
    assert {card['key'] for card in cards} == {'topic-blood_pressure', 'topic-blood_glucose'}
    family = next(card for card in cards if card['key'] == 'topic-blood_glucose')
    assert family['evidence'][0]['item_id'] == 'family-glucose'
    assert family['evidence'][0]['profile_revision'] == 7
    assert family['daily_prevention'] and family['sources']
    repeated = next(card for card in cards if card['key'] == 'topic-blood_pressure')
    assert {'family_history-blood_pressure', 'past_history-blood_pressure', 'repeated-blood_pressure--high'}.issubset(set(repeated['source_rules']))
    assert {entry['reading_id'] for entry in repeated['evidence'] if entry['type'] == 'measurement'} == set(reading_ids)
    assert {entry['item_id'] for entry in repeated['evidence'] if entry['type'] == 'profile_item'} == {'family-bp', 'own-bp'}
    assert all(card['rule_version'] == 'personal-focus-1.0' and card['applicability'] and card['sources'] for card in cards)
    assert all('risk_probability' not in card and 'diagnosis' not in card for card in cards)


def test_health_focus_does_not_treat_unknown_none_or_free_text_as_history(setup):
    app, client = setup
    for status in ['unknown', 'none']:
        set_focus_profile(app, family_history={"status": status, "items": [{"id": "stale", "name": "Diabetes"}]})
        assert client.get('/api/insights/metrics').get_json()['health_focus'] == []
    set_focus_profile(app, family_history={"status": "recorded", "items": [{"id": "negated", "name": "No diabetes"}, {"id": "unrelated", "name": "Routine note", "detail": "hypertension diabetes 高血压 糖尿病"}]})
    data = client.get('/api/insights/metrics').get_json()
    assert data['health_focus'] == []
    assert 'does not establish' in data['health_focus_eligibility']['reason']


@pytest.mark.parametrize('birth,special', [(None, 'general'), (date(2015, 1, 1), 'general'), (date(1980, 1, 1), 'pregnancy'), (date(1980, 1, 1), 'individual_target'), (date(1980, 1, 1), 'unknown')])
def test_health_focus_adult_and_special_context_guards(setup, birth, special):
    app, client = setup
    set_focus_profile(app, family_history={"status": "recorded", "items": [{"id": "family-bp", "name": "Hypertension"}]})
    with app.app_context():
        db.session.get(AccountProfile, 1).date_of_birth = birth; db.session.commit()
    for day in [2, 1]:
        assert add_reading(client, special_context=special, measured_at=(utc_now() - timedelta(days=day)).isoformat()).status_code == 201
    data = client.get('/api/insights/metrics').get_json()
    assert data['health_focus'] == []
    assert data['health_focus_eligibility']['status'] == 'not_assessed'


def test_health_focus_repeat_rule_excludes_same_day_stale_and_voided(setup):
    app, client = setup
    same_time = utc_now() - timedelta(days=1)
    for _ in range(2):
        assert add_reading(client, measured_at=same_time.isoformat()).status_code == 201
    assert add_reading(client, measured_at=(utc_now() - timedelta(days=40)).isoformat()).status_code == 201
    assert client.get('/api/insights/metrics').get_json()['health_focus'] == []
    previous = add_reading(client, measured_at=(utc_now() - timedelta(days=2)).isoformat()).get_json()['measurement']
    assert client.get('/api/insights/metrics').get_json()['health_focus']
    assert client.post(f"/api/insights/metrics/{previous['id']}/void", json={'reason': 'Wrong date'}).status_code == 200
    assert client.get('/api/insights/metrics').get_json()['health_focus'] == []
    # Non-resting pulse is not eligible for the resting reference rule.
    for day in [2, 1]:
        assert add_reading(client, metric_type='heart_rate', value=130, context='exercise', measured_at=(utc_now() - timedelta(days=day)).isoformat()).status_code == 201
    assert client.get('/api/insights/metrics?metric=heart_rate').get_json()['health_focus'] == []
