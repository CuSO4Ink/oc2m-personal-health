from datetime import date, timedelta
import re

import pytest

from app import create_app
from app.extensions import db
from app.models import HealthRecord, ShareRecipient, utc_now
from app.record_models import ProviderImportReference, RecordPrivacy
from app.routes.records import demo_import_items
from app.sample_catalog import hospital_samples, with_record_display


@pytest.fixture
def sample_owner():
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:', 'DEMO_FEATURES_ENABLED': True})
    client = app.test_client()
    assert client.post('/api/auth/register', json={'full_name': 'Sample Owner', 'email': 'sample-owner@example.test', 'password': 'Patient123'}).status_code == 201
    sample = hospital_samples()[0]
    with app.app_context():
        record = HealthRecord(user_id=1, title=sample['display_zh']['title'], record_type=sample['record_type'], record_date=date.fromisoformat(sample['record_date']), source_type='hospital', source_name='示例医院（模拟）', condition=sample['display_zh']['condition'], content=sample['display_zh']['content'])
        db.session.add(record); db.session.flush()
        db.session.add(ProviderImportReference(record_id=record.id, user_id=1, provider='demo_hospital', external_id=sample['external_id']))
        db.session.add(ShareRecipient(full_name='Dr. Lee', email='sample-doctor@example.test', role='Doctor', organisation='Maple Grove Clinic'))
        db.session.commit()
    return app, client


def test_eight_hospital_samples_have_canonical_english_metadata_and_existing_pdf_names(sample_owner):
    _, client = sample_owner
    items = demo_import_items()
    assert len(items) == 8
    assert len({item['filename'] for item in items}) == 8
    for item in items:
        assert item['filename'].endswith('.pdf')
        assert not re.search(r'[\u3400-\u9fff]', ' '.join(item[key] for key in ['title', 'filename', 'condition', 'content', 'source_name']))
        assert item['sample_display']['title'] == item['title']
    preview = client.post('/api/records/imports')
    assert preview.status_code == 201
    assert len(preview.get_json()['job']['items']) == 8
    assert len(client.get('/api/records/imports').get_json()['jobs'][0]['items']) == 8


def test_old_sample_display_preserves_raw_content_and_never_translates_personal_edits(sample_owner):
    app, client = sample_owner
    record = client.get('/api/records/1').get_json()['record']
    assert record['title'] == hospital_samples()[0]['display_zh']['title']
    assert record['sample_display']['title'] == hospital_samples()[0]['title']
    assert record['sample_display']['source_name'] == hospital_samples()[0]['source_name']
    with app.app_context():
        current = db.session.get(HealthRecord, 1)
        current.condition = '我自己写的疾病主题'
        db.session.commit()
        display = with_record_display(current, current.to_dict())
        assert display['condition'] == '我自己写的疾病主题'
        assert 'condition' not in display['sample_display']
        personal = HealthRecord(user_id=1, title=current.title, record_type='Other', source_type='self', record_date=date.today(), content='个人记录')
        db.session.add(personal); db.session.flush()
        assert 'sample_display' not in with_record_display(personal, personal.to_dict())


def test_shared_sample_display_contains_only_authorized_and_currently_visible_fields(sample_owner):
    app, client = sample_owner
    payload = {'recipient_id': 1, 'record_ids': [1], 'shared_fields': ['title', 'content'], 'starts_at': (utc_now() - timedelta(minutes=1)).isoformat(), 'expires_at': (utc_now() + timedelta(days=1)).isoformat()}
    response = client.post('/api/sharing/grants', json=payload)
    assert response.status_code == 201
    grant = response.get_json()['grant']['id']
    visible = client.post(f'/api/sharing/grants/{grant}/preview').get_json()['records'][0]
    assert set(visible['sample_display']) == {'title', 'content'}
    assert 'condition' not in visible and 'source_name' not in visible
    with app.app_context():
        db.session.add(RecordPrivacy(record_id=1, sensitive_fields=['content']))
        db.session.commit()
    visible = client.post(f'/api/sharing/grants/{grant}/preview').get_json()['records'][0]
    assert set(visible['sample_display']) == {'title'}
    assert 'content' not in visible
