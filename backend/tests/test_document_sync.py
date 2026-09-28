from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

import app as application
from app.extensions import db
from app.models import HealthMeasurement, RecordAttachment
from app.document_models import DocumentIndex
from app.extraction_models import ReportExtraction
from app.record_models import PersonalHealthProfile

SAMPLES = Path(__file__).parents[1] / 'app' / 'hospital_samples'


@pytest.fixture
def client_app(monkeypatch):
    monkeypatch.setattr(application, 'load_dotenv', lambda: None)
    monkeypatch.setattr('app.report_parser.windows_ocr', lambda data, extension, pages=None, language='auto': ({number: 'Achilles tendon rehabilitation. Scanned care note.' for number in (pages or [1])}, None))
    app = application.create_app({'TESTING': True, 'SECRET_KEY': 'document-test-only', 'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:', 'DEMO_FEATURES_ENABLED': True})
    client = app.test_client()
    assert client.post('/api/auth/register', json={'full_name': 'Document Test', 'email': 'document@example.invalid', 'password': 'RecordTest123'}).status_code == 201
    return client, app


def sync(client):
    job = client.post('/api/records/imports').get_json()['job']
    response = client.post(f"/api/records/imports/{job['id']}/confirm", json={'revision': job['revision'], 'selections': {item['external_id']: item['selected_type'] for item in job['items']}})
    assert response.status_code == 200
    return response.get_json()['job']


def upload(client, content, filename='uploaded.pdf'):
    record = client.post('/api/records', json={'title': 'Uploaded test document', 'record_type': 'Other', 'record_date': '2026-09-20', 'content': 'Private note with no report text'}).get_json()['record']
    result = client.post(f"/api/records/{record['id']}/attachments", data={'file': (BytesIO(content), filename), 'version': str(record['version'])}, content_type='multipart/form-data')
    assert result.status_code == 201
    return result.get_json()['record']


def test_hospital_pdf_sync_classification_private_search_and_no_unconfirmed_health_writes(client_app):
    client, app = client_app
    job = sync(client)
    assert job['counts']['imported'] == 8 and job['counts']['failed'] == 0
    assert len({item['selected_type'] for item in job['items']}) == 6
    assert len({item['record_date'] for item in job['items']}) == 3
    scan = PdfReader(SAMPLES / 'scanned-care-2026-09-20.pdf')
    assert not scan.pages[0].extract_text().strip()
    with app.app_context():
        assert RecordAttachment.query.count() == DocumentIndex.query.count() == 8
        assert HealthMeasurement.query.count() == 0
        assert not PersonalHealthProfile.query.first() or all(section['status'] == 'unknown' for section in PersonalHealthProfile.query.first().sections.values())
        assert ReportExtraction.query.count() == 8
    found = client.get('/api/records?q=thyroid').get_json()
    assert found['total'] == 1
    hit = found['records'][0]['search_hits'][0]
    assert hit['page'] == 1 and 'thyroid' in hit['snippet'].lower() and '&page=1' in hit['path']
    assert 'thyroid' not in found['records'][0]['content'].lower()
    assert len(client.get('/api/records/pending-review').get_json()['records']) >= 6
    assert client.get('/api/records?q=Achilles').get_json()['total'] == 1
    assert client.get('/api/records?q=imaging-2026').get_json()['records'][0]['search_hits'][0]['kind'] == 'filename'


def test_full_document_search_includes_sixth_page(client_app):
    client, _ = client_app
    writer = PdfWriter()
    lab = PdfReader(SAMPLES / 'check-up-2026-06-20.pdf')
    for _ in range(5): writer.add_page(lab.pages[0])
    writer.add_page(PdfReader(SAMPLES / 'imaging-2026-09-20.pdf').pages[0])
    output = BytesIO(); writer.write(output)
    record = upload(client, output.getvalue())
    assert record['attachments'][0]['index']['status'] == 'complete'
    assert record['attachments'][0]['index']['processed_pages'] == [1, 2, 3, 4, 5, 6]
    hit = client.get('/api/records?q=thyroid').get_json()['records'][0]['search_hits'][0]
    assert hit['page'] == 6


def test_partial_ocr_status_retry_and_owner_isolation(client_app, monkeypatch):
    client, app = client_app
    monkeypatch.setattr('app.report_parser.windows_ocr', lambda *args, **kwargs: ({}, 'OCR unavailable during this attempt'))
    monkeypatch.setattr('app.report_parser.ocr_capabilities', lambda: {'available': False})
    writer = PdfWriter()
    writer.add_page(PdfReader(SAMPLES / 'check-up-2026-06-20.pdf').pages[0])
    writer.add_page(PdfReader(SAMPLES / 'scanned-care-2026-09-20.pdf').pages[0])
    output = BytesIO(); writer.write(output)
    record = upload(client, output.getvalue())
    attachment = record['attachments'][0]
    assert attachment['index']['status'] == 'partial' and attachment['index']['processed_pages'] == [1]
    assert client.get('/api/records?q=Achilles').get_json()['total'] == 0
    monkeypatch.setattr('app.report_parser.windows_ocr', lambda *args, **kwargs: ({2: 'Achilles tendon rehabilitation'}, None))
    retried = client.post(f"/api/records/{record['id']}/attachments/{attachment['id']}/index").get_json()['record']
    assert retried['attachments'][0]['index']['status'] == 'complete'
    assert client.get('/api/records?q=Achilles').get_json()['records'][0]['search_hits'][0]['page'] == 2
    other = app.test_client()
    other.post('/api/auth/register', json={'full_name': 'Other', 'email': 'other-document@example.invalid', 'password': 'RecordTest123'})
    assert other.get('/api/records?q=Achilles').get_json()['total'] == 0
    assert other.post(f"/api/records/{record['id']}/attachments/{attachment['id']}/index").status_code == 404


def test_metadata_correction_preserves_original_and_sync_is_idempotent(client_app):
    client, app = client_app
    job = sync(client)
    item = job['items'][0]
    record = client.get(f"/api/records/{item['record_id']}").get_json()['record']
    path = f"/api/records/{record['id']}/attachments/{record['attachments'][0]['id']}"
    original = client.get(path).data
    corrected = client.patch(f"/api/records/{record['id']}/classification", json={'version': record['version'], 'record_type': 'Other', 'condition': 'Personal filing label'})
    assert corrected.status_code == 200
    assert client.get(path).data == original
    assert client.patch(f"/api/records/{record['id']}/classification", json={'version': record['version'], 'record_type': 'Imaging'}).status_code == 409
    assert client.patch(f"/api/records/{record['id']}", json={**record, 'content': 'Tampered hospital content'}).status_code == 403
    repeated = sync(client)
    assert repeated['counts']['duplicate'] == 8
    assert {entry['record_id'] for entry in repeated['items']} == {entry['record_id'] for entry in job['items']}
    with app.app_context(): assert RecordAttachment.query.count() == DocumentIndex.query.count() == 8


def test_failed_document_is_preserved_and_deleted_attachment_leaves_no_search_text(client_app):
    client, app = client_app
    failed = upload(client, b'%PDF-1.4\ninvalid body\n%%EOF')
    assert failed['attachments'][0]['index']['status'] == 'failed'
    record = upload(client, (SAMPLES / 'imaging-2026-09-20.pdf').read_bytes())
    attachment = record['attachments'][0]
    assert client.get('/api/records?q=thyroid').get_json()['total'] == 1
    response = client.delete(f"/api/records/{record['id']}/attachments/{attachment['id']}", json={'version': record['version']})
    assert response.status_code == 200
    assert client.get('/api/records?q=thyroid').get_json()['total'] == 0
    with app.app_context(): assert db.session.get(DocumentIndex, attachment['id']) is None


def test_newer_review_confirmation_does_not_resurface_an_old_automatic_draft(client_app):
    client, _ = client_app
    record = upload(client, (SAMPLES / 'check-up-2026-06-20.pdf').read_bytes())
    assert record['pending_extractions'][0]['candidate_count'] == 3
    # Correcting the evidence changes the candidate key. An older unconfirmed
    # OCR draft must not become pending again after this newer review completes.
    response = client.post('/api/extractions', json={'record_id': record['id'], 'attachment_id': record['attachments'][0]['id'],
                          'text': 'Blood pressure: 125/80 mmHg'})
    assert response.status_code == 201
    draft = response.get_json()['extraction']
    confirmed = client.post(f"/api/extractions/{draft['id']}/confirm", json={'revision': draft['revision'], 'acknowledged': True,
        'selections': [{'candidate_id': draft['candidates'][0]['id'], 'value': 125, 'secondary_value': 80, 'unit': 'mmHg',
                        'measured_at': '2026-06-20T08:00:00Z', 'context': '', 'special_context': 'general'}]})
    assert confirmed.status_code == 200, confirmed.get_json()
    assert client.get(f"/api/records/{record['id']}").get_json()['record']['pending_extractions'] == []
    assert all(item['record_id'] != record['id'] for item in client.get('/api/records/pending-review').get_json()['records'])
