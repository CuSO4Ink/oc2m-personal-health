from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from ..advice_service import AdviceError, error_payload, generate, status_payload

advice_bp = Blueprint('advice', __name__)


@advice_bp.get('')
@login_required
def latest_advice():
    language = request.args.get('language', 'zh')
    if language not in {'zh', 'en'}:
        return jsonify(error='invalid_language', message='Use language en or zh.'), 400
    return jsonify(status_payload(current_user.id, language))


@advice_bp.post('/generate')
@login_required
def generate_advice():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get('language', 'zh'), str) or data.get('language', 'zh') not in {'zh', 'en'} or ('acknowledged' in data and type(data['acknowledged']) is not bool):
        return jsonify(error='invalid_request', message='Use language en or zh and a boolean acknowledgement.'), 400
    language = data.get('language', 'zh')
    try:
        return jsonify(generate(current_user.id, language, data.get('acknowledged')))
    except AdviceError as exc:
        failure = error_payload(exc.code, language)
        return jsonify(**status_payload(current_user.id, language), error=exc.code, message=failure['message']), exc.status
