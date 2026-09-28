from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import subprocess

import pytest
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

import app as application
from app.extensions import db
from app.models import HealthMeasurement, RecordAttachment
from app.extraction_models import MeasurementSource, ReportExtraction, measurement_source_payload
from app import report_parser


@pytest.fixture
def app_factory(monkeypatch):
    monkeypatch.setattr(application, 'load_dotenv', lambda: None)
    monkeypatch.setattr('app.routes.extraction.ocr_capabilities', lambda: {'available': False, 'languages': []})
    def make(uri='sqlite:///:memory:'):
        return application.create_app({'TESTING': True, 'SECRET_KEY': 'extraction-test-only', 'SQLALCHEMY_DATABASE_URI': uri})
    return make


def register(app, email='extract@example.invalid'):
    client = app.test_client()
    assert client.post('/api/auth/register', json={'full_name': 'Extraction Test', 'email': email, 'password': 'ExtractTest123'}).status_code == 201
    return client


def record(client, content='Blood pressure: 128/82 mmHg\nFasting glucose: 108 mg/dL\nHeart rate: 72 bpm'):
    result = client.post('/api/records', json={'title': 'Local report', 'record_type': 'Lab Report', 'record_date': '2026-09-10', 'condition': 'Review', 'source_name': 'Personal', 'content': content})
    assert result.status_code == 201
    return result.get_json()['record']


def prepare(client, rid, **extra):
    result = client.post('/api/extractions', json={'record_id': rid, **extra})
    assert result.status_code == 201, result.get_json()
    return result.get_json()['extraction']


def selection(candidate, **extra):
    return {'candidate_id': candidate['id'], 'value': candidate['value'], 'secondary_value': candidate['secondary_value'],
            'unit': candidate['unit'], 'context': candidate['context'], 'measured_at': '2026-09-10T10:00:00+08:00', **extra}


def confirm(client, draft, selections=None, **extra):
    return client.post(f"/api/extractions/{draft['id']}/confirm", json={'revision': draft['revision'], 'acknowledged': True,
        'selections': selections if selections is not None else [selection(item) for item in draft['candidates']], **extra})


def text_pdf(pages=1):
    writer = PdfWriter()
    for _ in range(pages):
        page = writer.add_blank_page(width=600, height=800)
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data(b'BT /F1 14 Tf 40 700 Td (Blood pressure: 128/82 mmHg) Tj 0 -25 Td (Fasting glucose: 5.8 mmol/L) Tj ET')
        page[NameObject('/Contents')] = writer._add_object(stream)
    output = BytesIO(); writer.write(output)
    return output.getvalue()


def test_parser_requires_explicit_labels_units_and_avoids_reference_ranges():
    values = report_parser.parse_candidates('血压：128/82毫米汞柱\n空腹血糖：5.8 mmol/L\n静息心率：72 次/分钟')
    assert [item['metric_type'] for item in values] == ['blood_pressure', 'blood_glucose', 'heart_rate']
    assert values[1]['context'] == 'fasting' and values[2]['context'] == 'resting'
    assert all(item['measured_at'] is None for item in values)
    assert report_parser.parse_candidates('Reference glucose: 5.8 mmol/L\nTarget BP: 120/80 mmHg\n128/82 mmHg\nGlucose: 5.8\nHbA1c: 6.2 %\nFetalheart rate: 130 bpm\nDate 2026/09/10') == []


def test_real_pdf_text_page_limit_and_ocr_timeout_fallback(monkeypatch):
    result = report_parser.extract_attachment(text_pdf(6), 'application/pdf')
    assert result['method'] == 'pdf_text' and result['total_pages'] == 6 and result['processed_pages'] == [1, 2, 3, 4, 5]
    assert len(report_parser.parse_candidates(result['text'])) == 10
    assert any('1 later pages were not processed' in item for item in result['warnings'])
    monkeypatch.setattr(report_parser, 'ocr_capabilities', lambda: {'available': True})
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired('local-ocr', 35)
    monkeypatch.setattr(report_parser, '_powershell', timeout)
    fallback = report_parser.extract_attachment(b'not used', 'image/png')
    assert not fallback['text'] and any('35 seconds' in item for item in fallback['warnings'])


def test_candidates_do_not_save_measurements_and_confirm_preserves_corrected_value(app_factory):
    app = app_factory(); client = register(app); source = record(client)
    draft = prepare(client, source['id'])
    with app.app_context():
        assert HealthMeasurement.query.count() == 0
    assert confirm(client, draft, acknowledged=False).status_code == 400
    assert confirm(client, draft, [selection(draft['candidates'][0], measured_at=None)]).status_code == 400
    assert confirm(client, draft, [selection(draft['candidates'][1], context={})]).status_code == 400
    assert confirm(client, draft, [selection(draft['candidates'][0], special_context=[])]).status_code == 400
    selections = [selection(draft['candidates'][0], value=130), selection(draft['candidates'][1])]
    response = confirm(client, draft, selections)
    assert response.status_code == 200, response.get_json()
    measurements = response.get_json()['measurements']
    assert measurements[0]['value'] == 130 and measurements[1]['value'] == 6.0
    with app.app_context():
        assert HealthMeasurement.query.count() == 2
        provenance = measurement_source_payload(measurements[0]['id'])
        assert provenance['original_values']['value'] == 128 and provenance['confirmed_values']['value'] == 130
        assert provenance['review_path'] == f"/records/{source['id']}?extraction={draft['id']}"
        assert db.session.get(ReportExtraction, draft['id']).original_text == source['content']
    repeated = prepare(client, source['id'])
    assert len([item for item in repeated['candidates'] if item['existing_measurement_id']]) == 2
    assert confirm(client, draft, selections).status_code == 409
    result = confirm(client, repeated, [selection(repeated['candidates'][0])]).get_json()
    assert not result['measurements'] and len(result['duplicates']) == 1
    correction = client.patch(f"/api/insights/metrics/{measurements[0]['id']}", json={'value': 132, 'reason': 'Correct transcribed systolic reading'})
    assert correction.status_code == 200
    with app.app_context():
        provenance = measurement_source_payload(correction.get_json()['measurement']['id'])
        assert provenance['original_measurement_id'] == measurements[0]['id']
        assert provenance['original_values']['value'] == 128


def test_review_optimistic_revision_original_preserved_and_ownership(app_factory):
    app = app_factory(); client = register(app); source = record(client)
    draft = prepare(client, source['id'])
    other = register(app, 'other@example.invalid')
    assert other.get(f"/api/extractions/{draft['id']}").status_code == 404
    assert other.post('/api/extractions', json={'record_id': source['id']}).status_code == 404
    assert other.patch(f"/api/extractions/{draft['id']}/review", json={'revision': 1, 'text': 'BP: 130/82 mmHg'}).status_code == 404
    assert confirm(other, draft).status_code == 404
    response = client.patch(f"/api/extractions/{draft['id']}/review", json={'revision': 1, 'text': 'BP: 130/82 mmHg'})
    revised = response.get_json()['extraction']
    assert revised['revision'] == 2 and revised['original_text'] == source['content'] and revised['text_edited']
    assert client.patch(f"/api/extractions/{draft['id']}/review", json={'revision': 1, 'text': 'BP: 140/82 mmHg'}).status_code == 409
    assert confirm(client, draft).status_code in {400, 409}
    assert confirm(client, revised).status_code == 200
    assert client.patch(f"/api/extractions/{draft['id']}/review", json={'revision': 3, 'text': 'BP: 140/82 mmHg'}).status_code == 409


def test_attachment_ownership_dedup_and_durable_source_after_removal(app_factory):
    app = app_factory(); client = register(app); source = record(client)
    upload = client.post(f"/api/records/{source['id']}/attachments", data={'version': '1', 'file': (BytesIO(text_pdf()), 'synthetic.pdf')}, content_type='multipart/form-data')
    assert upload.status_code == 201, upload.get_json()
    attached = upload.get_json()['record']; attachment = attached['attachments'][0]
    unrelated = record(client)
    assert client.post('/api/extractions', json={'record_id': unrelated['id'], 'attachment_id': attachment['id']}).status_code == 404
    draft = prepare(client, source['id'], attachment_id=attachment['id'])
    assert draft['method'] == 'pdf_text'
    result = confirm(client, draft).get_json()
    assert len(result['measurements']) == 2
    repeated = prepare(client, source['id'], attachment_id=attachment['id'])
    assert len(confirm(client, repeated).get_json()['duplicates']) == 2
    assert client.delete(f"/api/records/{source['id']}/attachments/{attachment['id']}", json={'version': attached['version']}).status_code == 200
    loaded = client.get(f"/api/extractions/{draft['id']}").get_json()['extraction']
    assert loaded['attachment_available'] is False and loaded['original_text']
    with app.app_context():
        assert RecordAttachment.query.count() == 0 and MeasurementSource.query.count() == 2
        assert measurement_source_payload(result['measurements'][0]['id'])['filename'] == 'synthetic.pdf'


def test_archive_blocks_import_and_manual_fallback_remains_local(app_factory):
    app = app_factory(); client = register(app); source = record(client, 'No supported readings')
    draft = prepare(client, source['id'], text='Pulse: 73 bpm')
    assert draft['method'] == 'manual_text' and len(draft['candidates']) == 1
    assert client.patch(f"/api/records/{source['id']}/archive", json={'version': 1, 'archived': True}).status_code == 200
    assert confirm(client, draft).status_code == 409
    assert client.post('/api/extractions', json={'record_id': source['id']}).status_code == 409


def test_concurrent_confirm_and_restart_do_not_duplicate(app_factory, tmp_path):
    uri = f"sqlite:///{(tmp_path / 'extraction.sqlite').as_posix()}"
    app = app_factory(uri); client = register(app); source = record(client, 'Pulse: 73 bpm')
    draft1 = prepare(client, source['id']); draft2 = prepare(client, source['id'])
    cookie = client.get_cookie('session')
    def run(draft):
        with app.test_client() as concurrent_client:
            concurrent_client.set_cookie('session', cookie.value)
            return confirm(concurrent_client, draft).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(run, [draft1, draft2]))
    assert all(status in {200, 409} for status in statuses)
    with app.app_context():
        assert HealthMeasurement.query.count() == 1 and MeasurementSource.query.count() == 1
    reopened = app_factory(uri)
    reader = reopened.test_client(); reader.set_cookie('session', cookie.value)
    stored = reader.get(f"/api/extractions/{draft1['id']}")
    assert stored.status_code == 200 and stored.get_json()['extraction']['candidates'][0]['existing_measurement_id']
