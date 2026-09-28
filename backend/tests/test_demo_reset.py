from datetime import date, timedelta

import pytest
from sqlalchemy import Boolean, Date, DateTime, Integer, JSON, event, insert, select, text

import app as application
from app.demo_community_catalog import ensure_demo_community_catalog, protected_demo_community_ids
from app.demo_data import DEMO_PASSWORD, seed_usability_demo
from app.demo_reset import reset_demo_account
from app.extensions import db
from app.models import AccountProfile, AccountSession, HealthRecord, User, utc_now
from app.record_models import empty_sections


@pytest.fixture
def setup(monkeypatch, tmp_path):
    monkeypatch.setattr(application, 'load_dotenv', lambda: None)
    monkeypatch.setattr('app.report_parser.windows_ocr', lambda data, extension, pages=None, language='auto': ({number: 'Synthetic care note.' for number in (pages or [1])}, None))
    app = application.create_app({'TESTING': True, 'SECRET_KEY': 'reset-test', 'SQLALCHEMY_DATABASE_URI': f"sqlite:///{(tmp_path / 'reset.db').as_posix()}", 'DEMO_FEATURES_ENABLED': True, 'DEMO_DATASET': 'reset-test', 'DEEPSEEK_API_KEY': ''})
    with app.app_context():
        event.listen(db.engine, 'connect', lambda connection, _: connection.execute('PRAGMA foreign_keys=ON'))
        db.session.execute(text('PRAGMA foreign_keys=ON')); db.session.commit()
        assert db.session.execute(text('PRAGMA foreign_keys')).scalar() == 1
        seed_usability_demo()
        ensure_demo_community_catalog()
        owner_id = User.query.filter_by(email='alex@example.test').one().id
        other_id = User.query.filter_by(email='jamie@example.test').one().id
    client = app.test_client()
    assert client.post('/api/auth/login', json={'email': 'alex@example.test', 'password': DEMO_PASSWORD}).status_code == 200
    return app, client, owner_id, other_id


def row(name, **values):
    """Small synthetic FK fixture; supply references explicitly, fill plain required fields."""
    table = db.metadata.tables[name]
    for column in table.columns:
        if column.name in values or column.nullable or column.default or column.server_default or column.primary_key:
            continue
        assert not column.foreign_keys, f'Missing explicit test foreign key: {name}.{column.name}'
        values[column.name] = (utc_now() if isinstance(column.type, DateTime) else date.today() if isinstance(column.type, Date)
            else False if isinstance(column.type, Boolean) else 1 if isinstance(column.type, Integer) else {} if isinstance(column.type, JSON) else 'Synthetic fixture')
    result = db.session.execute(insert(table).values(**values))
    return result.inserted_primary_key[0]


def count(name, **where):
    table = db.metadata.tables[name]
    query = select(table)
    for key, value in where.items(): query = query.where(table.c[key] == value)
    return len(db.session.execute(query).all())


def sync(client):
    job = client.post('/api/records/imports').get_json()['job']
    response = client.post(f"/api/records/imports/{job['id']}/confirm", json={'revision': job['revision'], 'selections': {item['external_id']: item['selected_type'] for item in job['items']}})
    assert response.status_code == 200, response.get_json()
    return response.get_json()['job']


def add_private_fixture(app, owner, other):
    with app.app_context():
        tables = db.metadata.tables
        record = HealthRecord.query.filter_by(user_id=owner).order_by(HealthRecord.id).first()
        record_id = record.id
        extraction = db.session.execute(select(tables['report_extractions']).where(tables['report_extractions'].c.user_id == owner)).mappings().first()
        foreign_record = row('health_records', user_id=other, title='Other private record', record_type='Other', content='DO NOT REMOVE')
        measurement = row('health_measurements', user_id=owner, metric_type='heart_rate', value=80, unit='bpm', context='resting', measured_at=utc_now())
        replacement = row('health_measurements', user_id=owner, metric_type='heart_rate', value=78, unit='bpm', context='resting', measured_at=utc_now())
        row('health_measurements', user_id=other, metric_type='heart_rate', value=72, unit='bpm', context='resting', measured_at=utc_now())
        row('measurement_contexts', measurement_id=measurement)
        row('measurement_dispositions', measurement_id=measurement, replacement_id=replacement, reason='Test correction')
        row('health_alerts', user_id=owner, measurement_id=measurement)
        row('measurement_sources', measurement_id=measurement, user_id=owner, extraction_id=extraction['id'], record_id=record_id)
        sections = empty_sections(); sections['allergies'] = {'status':'recorded', 'items':[{'id':'allergy','name':'Test allergy'}]}
        row('personal_health_profiles', user_id=owner, sections=sections)
        row('profile_fact_sources', user_id=owner, profile_item_id='allergy', section='allergies', extraction_id=extraction['id'], record_id=record_id)
        row('record_annotations', user_id=owner, record_id=record_id)
        row('record_privacy', record_id=record_id, sensitive=True)
        row('record_lifecycles', record_id=record_id, archived_at=utc_now())
        recipient = db.session.execute(select(tables['share_recipients'].c.id)).scalar()
        grant = row('share_grants', user_id=owner, recipient_id=recipient, starts_at=utc_now(), expires_at=utc_now()+timedelta(days=2))
        row('share_grant_records', grant_id=grant, record_id=record_id)
        row('share_field_settings', grant_id=grant)
        row('share_scope_snapshots', grant_id=grant)
        access = row('access_events', user_id=owner, grant_id=grant, record_id=record_id)
        row('access_reviews', event_id=access)
        row('simulated_access_events', event_id=access)
        row('share_scope_access_events', user_id=owner, grant_id=grant)
        reminder = row('health_reminders', user_id=owner, title='Personal reminder', next_due_at=utc_now())
        row('reminder_schedules', reminder_id=reminder, interval_days=1)
        row('reminder_cancellations', reminder_id=reminder)
        slot = db.session.execute(select(tables['appointment_slots'].c.id)).scalar()
        appointment = row('appointments', user_id=owner, slot_id=slot, status='confirmed')
        row('appointments', user_id=owner, slot_id=slot, status='cancelled', cancelled_at=utc_now())
        row('appointments', user_id=other, slot_id=slot, status='confirmed')
        db.session.execute(tables['appointment_slots'].update().where(tables['appointment_slots'].c.id==slot).values(booked_count=2))
        row('appointment_sharing', appointment_id=appointment, recipient_id=recipient, grant_id=grant)
        notification = row('notifications', user_id=owner, dedupe_key='personal-test')
        row('notification_resolutions', notification_id=notification)
        row('notifications', user_id=other, dedupe_key='foreign-test', title='Keep other notice')
        row('security_events', user_id=owner, important=True)
        row('advice_states', user_id=owner, consent_version='deepseek-health-1', consent_at=utc_now())
        row('advice_results', user_id=owner, language='en', model='synthetic', fingerprint='x'*64, prompt_version='test', content={}, sources=[], input_summary={})
        row('notification_preferences', user_id=owner, muted_categories=['care'])
        row('password_reset_tokens', user_id=owner, code_hash='synthetic-security-state', expires_at=utc_now()+timedelta(minutes=5))
        row('email_change_tokens', user_id=owner)
        row('auth_attempts', key='synthetic-security-state')
        account = db.session.get(AccountProfile, owner); account.phone='15555551234'; account.date_of_birth=date(1980,1,1); account.preferred_language='English'

        originals = protected_demo_community_ids()
        circle = min(originals['circles'])
        own_post = row('community_posts', user_id=owner, circle_id=circle, body='My test post')
        row('community_likes', user_id=other, post_id=own_post)
        other_reply = row('community_comments', user_id=other, post_id=own_post, body='Reply removed with the reset post')
        own_reply = row('community_comments', user_id=owner, post_id=min(originals['posts']), body='My test reply')
        foreign_post = row('community_posts', user_id=other, circle_id=circle, body='Unrelated post remains')
        post_report = row('community_reports', reporter_id=other, post_id=own_post)
        comment_report = row('community_comment_reports', reporter_id=other, comment_id=own_reply)
        row('community_report_reviews', reporter_id=other, target_type='post', report_id=post_report)
        row('community_report_reviews', reporter_id=other, target_type='comment', report_id=comment_report)
        relationship = row('community_connections', first_id=min(owner,other), second_id=max(owner,other), requester_id=owner, status='accepted')
        message = row('community_messages', connection_id=relationship, sender_id=owner, body='Owner private message')
        received = row('community_messages', connection_id=relationship, sender_id=other, body='Other private message')
        row('community_message_deliveries', user_id=owner, message_id=message, client_nonce='reset-message')
        report = row('community_message_reports', reporter_id=other, message_id=message)
        row('community_report_reviews', reporter_id=other, target_type='message', report_id=report)
        row('community_blocks', user_id=owner, target_id=other)
        incoming_block = row('community_blocks', user_id=other, target_id=owner)
        morgan = User.query.filter_by(email='morgan@example.test').one().id
        riley = User.query.filter_by(email='riley@example.test').one().id
        unrelated = row('community_connections', first_id=min(morgan,riley), second_id=max(morgan,riley), requester_id=morgan, status='accepted')
        unrelated_message = row('community_messages', connection_id=unrelated, sender_id=morgan, body='Unrelated conversation remains')
        db.session.commit()
        return {'originals': originals, 'foreign_record': foreign_record, 'foreign_post': foreign_post, 'other_reply': other_reply, 'received': received,
                'incoming_block': incoming_block, 'unrelated_message': unrelated_message, 'slot': slot}


def test_reset_is_demo_only_authenticated_and_requires_exact_confirmation(setup):
    app, client, owner, _ = setup
    assert app.test_client().get('/api/demo/reset-account').status_code == 401
    assert app.test_client().post('/api/demo/reset-account', json={'confirmed':True}).status_code == 401
    assert client.get('/api/demo/reset-account').get_json()['available']
    for value in (None, False, 1, 'true'):
        assert client.post('/api/demo/reset-account', json={'confirmed':value}).status_code == 400
    app.config['DEMO_DATASET'] = None
    assert not client.get('/api/demo/reset-account').get_json()['available']
    assert client.post('/api/demo/reset-account', json={'confirmed':True}).status_code == 403
    app.config.update(DEMO_DATASET='reset-test', DEMO_FEATURES_ENABLED=False)
    assert client.post('/api/demo/reset-account', json={'confirmed':True}).status_code == 403
    with app.app_context(): assert db.session.get(User, owner) is not None


def test_reset_removes_all_private_dependencies_preserves_fixtures_and_can_resync(setup):
    app, client, owner, other = setup
    assert sync(client)['counts']['imported'] == 8
    fixture = add_private_fixture(app, owner, other)
    with app.app_context():
        user = db.session.get(User, owner)
        credential = (user.email, user.full_name, user.password_hash)
        sessions = AccountSession.query.filter_by(user_id=owner).count()
        catalog_counts = {name: count(name) for name in ('community_circles','share_recipients','service_facilities','medical_services','appointment_slots','service_clinicians')}
    # A supplied foreign ID is ignored: the HTTP route can reset only current_user.
    response = client.post('/api/demo/reset-account', json={'confirmed':True,'user_id':other})
    assert response.status_code == 200, response.get_json()
    assert response.get_json()['deleted']['health_records'] == 8
    with app.app_context():
        assert db.session.execute(text('PRAGMA foreign_key_check')).all() == []
        assert protected_demo_community_ids() == fixture['originals']
        for name in ('personal_health_profiles','health_records','health_measurements','health_alerts','advice_states','advice_results','share_grants','access_events','share_scope_access_events','appointments','health_reminders','notifications','security_events','provider_import_references','record_import_jobs','document_indexes','report_extractions','profile_fact_sources','measurement_sources','record_audit_events','record_annotations'):
            assert count(name,user_id=owner) == 0, name
        for name in ('extraction_facts','measurement_dispositions','measurement_contexts','share_scope_snapshots','share_grant_records','share_field_settings','access_reviews','simulated_access_events','reminder_schedules','reminder_cancellations','appointment_sharing','notification_resolutions','community_message_deliveries','community_message_reports','community_comment_reports','community_reports','community_report_reviews'):
            assert count(name) == 0, name
        assert count('health_records',id=fixture['foreign_record']) == 1
        assert count('health_measurements',user_id=other) == 1
        assert count('appointments',user_id=other) == count('notifications',user_id=other) == 1
        assert count('community_posts',id=fixture['foreign_post']) == 1
        assert count('community_comments',id=fixture['other_reply']) == count('community_messages',id=fixture['received']) == 0
        assert count('community_messages',id=fixture['unrelated_message']) == count('community_blocks',id=fixture['incoming_block']) == 1
        for name,total in catalog_counts.items(): assert count(name) == total
        slots = db.metadata.tables['appointment_slots']
        assert db.session.execute(select(slots.c.booked_count).where(slots.c.id==fixture['slot'])).scalar() == 1
        user = db.session.get(User,owner)
        assert (user.email,user.full_name,user.password_hash) == credential
        assert AccountSession.query.filter_by(user_id=owner).count() == sessions
        account = db.session.get(AccountProfile,owner)
        assert account.phone == '' and account.date_of_birth is None and account.preferred_language == 'English'
        assert count('notification_preferences',user_id=owner) == 1
        assert count('password_reset_tokens',user_id=owner) == count('email_change_tokens',user_id=owner) == 1
        assert count('auth_attempts',key='synthetic-security-state') == 1
    assert client.get('/api/records').get_json()['total'] == 0
    assert client.get('/api/notifications').get_json()['summary']['total'] == 0
    assert sync(client)['counts']['imported'] == 8
    assert client.post('/api/demo/reset-account',json={'confirmed':True}).status_code == 200
    again = client.post('/api/demo/reset-account',json={'confirmed':True}).get_json()
    assert sum(again['deleted'].values()) == 0


def test_reset_rolls_back_every_delete_when_a_later_step_fails(setup):
    app, client, owner, _ = setup
    assert sync(client)['counts']['imported'] == 8
    with app.app_context():
        before = {name: count(name) for name in ('health_records','record_attachments','document_indexes','report_extractions','provider_import_references')}
        def fail_records(connection, cursor, statement, parameters, context, executemany):
            if statement.startswith('DELETE FROM health_records'):
                raise RuntimeError('Synthetic rollback probe')
        event.listen(db.engine, 'before_cursor_execute', fail_records)
        try:
            with pytest.raises(RuntimeError,match='Synthetic rollback probe'):
                reset_demo_account(owner)
        finally:
            event.remove(db.engine, 'before_cursor_execute', fail_records)
        assert {name: count(name) for name in before} == before
        assert db.session.execute(text('PRAGMA foreign_key_check')).all() == []
