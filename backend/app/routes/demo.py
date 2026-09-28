from io import BytesIO
from flask import Blueprint, current_app, jsonify, request, send_file
from flask_login import current_user, login_required
from ..demo_data import DEMO_ACCOUNTS, DEMO_PASSWORD, sample_report_pdf
from ..demo_reset import DemoResetError, reset_demo_account, reset_scope

demo_bp = Blueprint("demo", __name__)


@demo_bp.get('/reset-account')
@login_required
def account_reset_scope():
    return jsonify(reset_scope())


@demo_bp.post('/reset-account')
@login_required
def reset_current_account():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or data.get('confirmed') is not True:
        return jsonify(error='confirmation_required', message='Confirm the reset scope before resetting your personal demo data.'), 400
    try:
        return jsonify(reset_demo_account(current_user.id))
    except DemoResetError as exc:
        return jsonify(error=exc.code, message=exc.message), exc.status


@demo_bp.get("/context")
def demo_context():
    prepared = bool(current_app.config.get("DEMO_DATASET")) and current_app.config.get("DEMO_FEATURES_ENABLED", False)
    return jsonify({"prepared": prepared, "dataset_id": current_app.config.get("DEMO_DATASET") if prepared else None, "samples_available": bool(current_app.config.get("DEMO_FEATURES_ENABLED", False)), "accounts": DEMO_ACCOUNTS if prepared else [], "password": DEMO_PASSWORD if prepared else None})


@demo_bp.get("/sample-report")
@login_required
def sample_report():
    if not current_app.config.get("DEMO_FEATURES_ENABLED", False):
        return jsonify({"message": "Sample reports are disabled in this environment."}), 404
    return send_file(BytesIO(sample_report_pdf()), mimetype="application/pdf", as_attachment=True, download_name="sample-check-up.pdf", max_age=0)
