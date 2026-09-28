from datetime import timedelta

import app as application
from app.extensions import db
from app.models import HealthMeasurement, utc_now


def test_old_linked_reading_is_private_and_separate_from_period_statistics(monkeypatch):
    monkeypatch.setattr(application, 'load_dotenv', lambda: None)
    app = application.create_app({'TESTING': True, 'SECRET_KEY': 'focused-reading-test-only', 'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'})
    owner = app.test_client()
    assert owner.post('/api/auth/register', json={'full_name': 'Reading Owner', 'email': 'owner@example.invalid', 'password': 'ReadingTest123'}).status_code == 201
    now = utc_now()
    old = owner.post('/api/insights/metrics', json={'metric_type': 'blood_pressure', 'value': 128, 'secondary_value': 82,
        'measured_at': (now - timedelta(days=800)).isoformat() + 'Z', 'source_name': 'Historical report'}).get_json()['measurement']
    recent = []
    for days, value in [(1, 120), (3, 122), (5, 124)]:
        response = owner.post('/api/insights/metrics', json={'metric_type': 'blood_pressure', 'value': value, 'secondary_value': 80,
            'measured_at': (now - timedelta(days=days)).isoformat() + 'Z'})
        assert response.status_code == 201
        recent.append(response.get_json()['measurement']['id'])
    baseline = owner.get('/api/insights/metrics?metric=blood_pressure&days=365').get_json()
    response = owner.get(f"/api/insights/metrics?metric=blood_pressure&days=365&reading_id={old['id']}")
    assert response.status_code == 200
    focused = response.get_json()
    assert focused['focused_reading']['id'] == old['id'] and focused['focused_reading_outside_period'] is True
    assert {item['id'] for item in focused['readings']} == set(recent)
    for key in ('readings', 'summary', 'latest', 'trend', 'data_sufficiency', 'superseded_readings'):
        assert focused[key] == baseline[key], key
    assert baseline['summary']['count'] == 3 and baseline['summary']['average'] == 122
    assert owner.get(f"/api/insights/metrics?metric=heart_rate&reading_id={old['id']}").status_code == 404
    assert owner.get('/api/insights/metrics?reading_id=bad').status_code == 400
    assert owner.get('/api/insights/metrics?reading_id=9999999999999999999999999').status_code == 400
    assert owner.get('/api/insights/metrics?days=800').status_code == 400

    other = app.test_client()
    assert other.post('/api/auth/register', json={'full_name': 'Other Reader', 'email': 'other@example.invalid', 'password': 'ReadingTest123'}).status_code == 201
    foreign = other.get(f"/api/insights/metrics?metric=blood_pressure&reading_id={old['id']}")
    missing = other.get('/api/insights/metrics?metric=blood_pressure&reading_id=999999')
    assert foreign.status_code == missing.status_code == 404
    assert foreign.get_json() == missing.get_json() == {'message': 'Reading not found.'}
    with app.app_context():
        assert db.session.get(HealthMeasurement, old['id']).value == 128
