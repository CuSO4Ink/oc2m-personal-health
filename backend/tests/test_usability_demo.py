from io import BytesIO
from pypdf import PdfReader

from run_demo import prepare_demo
from app.demo_data import DEMO_ACCOUNTS, DEMO_PASSWORD, sample_report_pdf, seed_usability_demo
from app.extensions import db
from app.models import AccountProfile, User, HealthRecord, HealthMeasurement, HealthAlert, ShareGrant, HealthReminder, RecordAttachment
from app.record_models import PersonalHealthProfile
from app.community_models import CommunityIdentity


def test_fresh_demo_is_small_and_does_not_overwrite_previous_data(tmp_path):
    app, first_path = prepare_demo(demo_root=tmp_path)
    with app.app_context():
        assert User.query.count() == len(DEMO_ACCOUNTS) == 6
        starter = User.query.filter_by(email="start@example.test").one()
        assert HealthRecord.query.count() == RecordAttachment.query.count() == 0
        assert HealthMeasurement.query.count() == PersonalHealthProfile.query.count() == 0
        assert HealthAlert.query.count() == ShareGrant.query.count() == 0
        assert HealthReminder.query.count() == 0
        assert CommunityIdentity.query.count() == 6
        assert all(item.date_of_birth is None and not item.phone for item in AccountProfile.query.all())
        starter.full_name = "Retained previous demo edit"
        db.session.commit()
    reused, reused_path = prepare_demo(demo_root=tmp_path)
    assert reused_path == first_path
    with reused.app_context():
        assert User.query.filter_by(email="start@example.test").one().full_name == "Retained previous demo edit"
    fresh, second_path = prepare_demo(fresh=True, demo_root=tmp_path)
    assert second_path != first_path and first_path.is_file()
    with fresh.app_context():
        assert User.query.filter_by(email="start@example.test").one().full_name == "Taylor"
        try:
            seed_usability_demo()
        except ValueError:
            pass
        else:
            raise AssertionError("Seeding must refuse a non-empty database")


def test_each_demo_person_is_a_real_login_with_an_empty_health_folder(tmp_path):
    app, _ = prepare_demo(demo_root=tmp_path)
    for account in DEMO_ACCOUNTS:
        client = app.test_client()
        response = client.post('/api/auth/login', json={'email': account['email'], 'password': DEMO_PASSWORD})
        assert response.status_code == 200
        assert response.get_json()['user']['full_name'] == account['name']
        records = client.get('/api/records').get_json()
        assert records['total'] == 0
        if account['email'] != 'start@example.test':
            circles = client.get('/api/community').get_json()['circles']
            assert len(circles) == 3
            for circle in circles:
                members = client.get(f"/api/community/circles/{circle['id']}/members").get_json()
                assert circle['member_count'] == members['total'] == len(members['members']) == 5


def test_sample_pdf_contains_real_extractable_readings():
    text = PdfReader(BytesIO(sample_report_pdf())).pages[0].extract_text()
    assert "124/78 mmHg" in text and "5.4 mmol/L" in text and "72 bpm" in text
    assert "Synthetic data" in text
