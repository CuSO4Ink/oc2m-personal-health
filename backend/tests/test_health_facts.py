from datetime import date, timedelta

import pytest
import app as application
from app.extensions import db
from app.models import AccountProfile, HealthMeasurement, HealthRecord, RecordAttachment, utc_now
from app.record_models import profile_payload
from app.health_facts import ProfileFactSource, report_candidates
from app.routes.extraction import create_draft_from_document, pending_candidate_counts


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setattr(application, 'load_dotenv', lambda: None)
    monkeypatch.setattr('app.routes.extraction.ocr_capabilities', lambda: {'available': False, 'languages': []})
    app = application.create_app({'TESTING': True, 'SECRET_KEY': 'facts-tests', 'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'})
    client = app.test_client()
    assert client.post('/api/auth/register', json={'full_name':'Fact Test','email':'facts@example.test','password':'FactsTest123'}).status_code == 201
    with app.app_context():
        profile = AccountProfile.query.filter_by(user_id=1).first()
        if not profile:
            profile = AccountProfile(user_id=1); db.session.add(profile)
        profile.date_of_birth = date(1980, 1, 1); db.session.commit()
    return app, client


def prepare(client, text):
    record = client.post('/api/records', json={'title':'Hospital report','record_type':'Visit Summary','record_date':'2026-09-20','source_name':'Example hospital','content':text}).get_json()['record']
    response = client.post('/api/extractions', json={'record_id':record['id']})
    assert response.status_code == 201
    return response.get_json()['extraction']


def confirm(client, draft, **extra):
    return client.post(f"/api/extractions/{draft['id']}/confirm", json={'revision':draft['revision'], 'profile_revision':draft['profile_revision'], 'acknowledged':True,
        'selections':[{'candidate_id':item['id'],'value':item['value'],'secondary_value':item['secondary_value'],'unit':item['unit'],'context':item['context'],
                       'measured_at':(item['measured_at'] or '2026-09-20T08:00:00')+'Z'} for item in draft['candidates']],
        'facts':[{'candidate_id':item['id']} for item in draft['facts']], **extra})


def test_fact_labels_and_time_require_explicit_positive_statements():
    text = 'Measurement date: 2026-09-20 08:00\nBlood pressure: 128/82 mmHg\nConfirmed diagnosis: Hypertension\nCurrent medication: Amlodipine | dose: 5 mg | frequency: daily\nAllergy: Penicillin | reaction: rash\nFamily history: Type 2 diabetes | relationship: Father'
    readings, facts = report_candidates(text)
    assert readings[0]['measured_at'] == '2026-09-20T08:00:00'
    assert {item['section'] for item in facts} == {'past_history','medications','allergies','family_history'}
    negatives = 'Diagnosis: No diabetes\nDiagnosis: Possible pneumonia\nDiagnosis: cancer ruled out\n诊断：考虑肺炎\n确诊：未见高血压\n过敏：无\nReport date: 2026-09-20 08:00\nBP: 120/80 mmHg'
    readings, facts = report_candidates(negatives)
    assert facts == [] and readings[0]['measured_at'] is None
    assert report_candidates('Measurement date: 2026-09-20\nBP: 120/80 mmHg')[0][0]['measured_at'] is None
    multiple = '[Page 1]\nMeasurement date: 2026-09-19 08:00\nBP: 120/80 mmHg\n[Page 2]\nMeasurement date: 2026-09-20 09:00\nBP: 125/80 mmHg'
    candidates, _ = report_candidates(multiple)
    assert [(item['page'],item['measured_at']) for item in candidates] == [(1,'2026-09-19T08:00:00'),(2,'2026-09-20T09:00:00')]


def test_index_drafts_are_reused_and_only_confirmation_writes_health_data(setup):
    app, client = setup
    with app.app_context():
        record = HealthRecord(user_id=1,title='Synced report',record_type='Visit Summary',record_date=date(2026,9,20),source_type='hospital',source_name='Example hospital',content='Original immutable report')
        db.session.add(record);db.session.flush()
        attachment = RecordAttachment(record_id=record.id,filename='hospital.pdf',content_type='application/pdf',data=b'synthetic unique source',size=23)
        db.session.add(attachment);db.session.flush()
        index = {'status':'complete','total_pages':1,'pages':[{'page':1,'method':'pdf_text','text':'Measurement date: 2026-09-20 08:00\nBP: 128/82 mmHg\nDiagnosis: Hypertension\nMedication: Amlodipine | dose: 5 mg | frequency: daily\nAllergy: Penicillin | reaction: rash'}]}
        draft = create_draft_from_document(record,attachment,index)
        assert create_draft_from_document(record,attachment,index).id == draft.id
        assert pending_candidate_counts(draft) == {'measurement_count':1,'fact_count':3,'total':4}
        assert HealthMeasurement.query.count() == 0 and profile_payload(1)['revision'] == 0
        identifier=draft.id;db.session.commit()
    draft=client.get(f'/api/extractions/{identifier}').get_json()['extraction']
    response=confirm(client,draft)
    assert response.status_code == 200,response.get_json()
    result=response.get_json()
    assert len(result['measurements']) == 1 and len(result['profile_facts']) == 3
    assert result['profile']['revision'] == 1
    provenance=client.get('/api/extractions/profile-provenance').get_json()
    assert len(provenance['sources']) == 3
    assert all(item['page']==1 and item['current_item_matches'] and item['evidence'] and item['review_path'] for item in provenance['sources'])
    other=app.test_client();other.post('/api/auth/register',json={'full_name':'Other Fact','email':'otherfact@example.test','password':'FactsTest123'})
    assert other.get('/api/extractions/profile-provenance').get_json()['sources'] == []
    assert other.get(f'/api/extractions/{identifier}').status_code == 404


def test_profile_conflict_rolls_back_whole_batch_and_preserves_manual_entries(setup):
    app,client=setup
    draft=prepare(client,'BP: 130/85 mmHg\nDiagnosis: Hypertension | detail: report statement')
    profile=client.get('/api/records/profile').get_json()['profile']
    profile['sections']['past_history']={'status':'recorded','items':[{'id':'manual-entry','name':'Hypertension','detail':'My newer manual details','sensitive':True}]}
    assert client.put('/api/records/profile',json=profile).status_code==200
    conflict=confirm(client,draft)
    assert conflict.status_code==409 and conflict.get_json()['error']=='profile_conflict'
    with app.app_context():
        assert HealthMeasurement.query.count()==0 and ProfileFactSource.query.count()==0
    loaded=client.get(f"/api/extractions/{draft['id']}").get_json()['extraction']
    assert loaded['confirmed_at'] is None and loaded['profile_revision']==1
    result=confirm(client,loaded).get_json()
    saved=result['profile']['sections']['past_history']['items']
    assert len(saved)==1 and saved[0]['id']=='manual-entry' and saved[0]['detail']=='My newer manual details' and saved[0]['sensitive']
    assert result['profile']['revision']==1 and len(result['measurements'])==1 and result['fact_duplicates']
    assert client.get('/api/extractions/profile-provenance').get_json()['sources'][0]['linked_existing'] is True


def test_confirmed_report_and_personal_history_merge_into_one_topic_without_duplicate_evidence(setup):
    app,client=setup
    for day in (1,2):
        when=(utc_now()-timedelta(days=day)).strftime('%Y-%m-%d 08:00')
        draft=prepare(client,f'Measurement date: {when}\nBP: 145/92 mmHg\nDiagnosis: Hypertension\nFamily history: Hypertension | relationship: Father')
        assert confirm(client,draft).status_code==200
    data=client.get('/api/insights/metrics').get_json()
    cards=data['health_focus']
    assert len(cards)==1 and cards[0]['key']=='topic-blood_pressure'
    assert len(cards[0]['source_rules'])>=3
    evidence=cards[0]['evidence']
    assert len([item for item in evidence if item['type']=='measurement'])==2
    histories=[item for item in evidence if item['type']=='profile_item']
    assert len(histories)==2 and all(item['report_sources'] for item in histories)
    assert cards[0]['sources'] and cards[0]['rule_version']=='personal-focus-1.0'
    assert len(client.get('/api/records/profile').get_json()['profile']['sections']['past_history']['items'])==1
