from datetime import date

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from ..extensions import db
from ..models import AccountProfile, AccountSession, SecurityEvent, User, utc_now
from .auth import ensure_account_session, normalise_email, record_security_event, validate_password


account_bp = Blueprint("account", __name__)
LANGUAGES = {"English", "简体中文", "繁體中文"}


def body():
    return request.get_json(silent=True) or {}


def profile_for_user():
    profile = db.session.get(AccountProfile, current_user.id)
    if not profile:
        profile = AccountProfile(user_id=current_user.id)
        db.session.add(profile)
        db.session.commit()
    return profile


def account_payload():
    profile = profile_for_user()
    completed = sum(bool(value) for value in [current_user.full_name, current_user.email, profile.phone, profile.date_of_birth])
    return {
        "user": current_user.to_dict(),
        "profile": profile.to_dict(),
        "profile_completeness": int(completed / 4 * 100),
        "sign_in_methods": [
            {"key": "password", "name": "Password", "status": "active", "description": "Available for sign-in and account recovery."},
            {"key": "sms", "name": "SMS verification", "status": "planned", "description": "Requires a verified phone number and message provider."},
            {"key": "face", "name": "Face verification", "status": "planned", "description": "Requires identity, consent and fallback requirements to be confirmed."},
        ],
    }


@account_bp.get("")
@login_required
def get_account():
    ensure_account_session()
    return jsonify(account_payload())


@account_bp.patch("/profile")
@login_required
def update_profile():
    data = body()
    full_name = str(data.get("full_name") or "").strip()
    phone = str(data.get("phone") or "").strip()
    language = str(data.get("preferred_language") or "English").strip()
    if len(full_name) < 2 or len(full_name) > 100:
        return jsonify({"error": "invalid_name", "message": "Enter your full name."}), 400
    if len(phone) > 40:
        return jsonify({"error": "invalid_phone", "message": "Enter a valid phone number."}), 400
    if language not in LANGUAGES:
        return jsonify({"error": "invalid_language", "message": "Select a supported language."}), 400
    date_of_birth = None
    if data.get("date_of_birth"):
        try:
            date_of_birth = date.fromisoformat(str(data["date_of_birth"]))
        except (TypeError, ValueError):
            return jsonify({"error": "invalid_birth_date", "message": "Enter a valid date of birth."}), 400
        if date_of_birth >= date.today():
            return jsonify({"error": "invalid_birth_date", "message": "Date of birth must be in the past."}), 400
    profile = profile_for_user()
    current_user.full_name = full_name
    profile.phone = phone
    profile.date_of_birth = date_of_birth
    profile.preferred_language = language
    profile.updated_at = utc_now()
    record_security_event(current_user.id, "profile_updated", "Account profile information was updated.")
    db.session.commit()
    return jsonify(account_payload())


@account_bp.post("/change-email")
@login_required
def change_email():
    data = body()
    current_password = str(data.get("current_password") or "")
    email = normalise_email(data.get("email"))
    if not current_user.check_password(current_password):
        record_security_event(current_user.id, "email_change_failed", "An email change attempt used an incorrect password.", result="blocked", important=True)
        db.session.commit()
        return jsonify({"error": "invalid_password", "message": "Current password is incorrect."}), 403
    if not email or "@" not in email:
        return jsonify({"error": "invalid_email", "message": "Enter a valid email address."}), 400
    existing = User.query.filter(User.email == email, User.id != current_user.id).first()
    if existing:
        return jsonify({"error": "email_exists", "message": "An account with this email already exists."}), 409
    if email == current_user.email:
        return jsonify({"error": "email_unchanged", "message": "Enter a different email address."}), 400
    previous_email = current_user.email
    current_user.email = email
    record_security_event(current_user.id, "email_changed", f"Sign-in email changed from {previous_email} to {email}.", important=True)
    db.session.commit()
    return jsonify(account_payload())


@account_bp.post("/change-password")
@login_required
def change_password():
    data = body()
    current_password = str(data.get("current_password") or "")
    new_password = str(data.get("new_password") or "")
    if not current_user.check_password(current_password):
        record_security_event(current_user.id, "password_change_failed", "A password change attempt used an incorrect current password.", result="blocked", important=True)
        db.session.commit()
        return jsonify({"error": "invalid_password", "message": "Current password is incorrect."}), 403
    password_error = validate_password(new_password)
    if password_error:
        return jsonify({"error": "invalid_password", "message": password_error}), 400
    if current_user.check_password(new_password):
        return jsonify({"error": "password_unchanged", "message": "Choose a password you have not just used."}), 400
    current_session = ensure_account_session()
    current_user.set_password(new_password)
    profile = profile_for_user()
    profile.password_changed_at = utc_now()
    for account_session in AccountSession.query.filter_by(user_id=current_user.id, revoked_at=None).all():
        if account_session.id != current_session.id:
            account_session.revoked_at = utc_now()
    record_security_event(current_user.id, "password_changed", "Password changed. Other active sessions were signed out.", important=True)
    db.session.commit()
    return jsonify({"message": "Password changed and other sessions were signed out.", "account": account_payload()})


@account_bp.get("/sessions")
@login_required
def list_sessions():
    current_session = ensure_account_session()
    sessions = AccountSession.query.filter_by(user_id=current_user.id, revoked_at=None).order_by(AccountSession.last_seen_at.desc()).all()
    active = [item for item in sessions if item.active]
    return jsonify({"sessions": [item.to_dict(current_session.token) for item in active]})


@account_bp.delete("/sessions/<int:session_id>")
@login_required
def revoke_session(session_id):
    current_session = ensure_account_session()
    account_session = AccountSession.query.filter_by(id=session_id, user_id=current_user.id, revoked_at=None).first()
    if not account_session or not account_session.active:
        return jsonify({"error": "not_found", "message": "Active session not found."}), 404
    if account_session.id == current_session.id:
        return jsonify({"error": "current_session", "message": "Use Sign out to end the current session."}), 400
    account_session.revoked_at = utc_now()
    record_security_event(current_user.id, "session_revoked", f"Signed out {account_session.device_name}.", important=True)
    db.session.commit()
    return jsonify({"message": "Session signed out."})


@account_bp.post("/sessions/revoke-others")
@login_required
def revoke_other_sessions():
    current_session = ensure_account_session()
    count = 0
    for account_session in AccountSession.query.filter_by(user_id=current_user.id, revoked_at=None).all():
        if account_session.id != current_session.id and account_session.active:
            account_session.revoked_at = utc_now()
            count += 1
    record_security_event(current_user.id, "other_sessions_revoked", f"Signed out {count} other active session(s).", important=count > 0)
    db.session.commit()
    return jsonify({"message": f"Signed out {count} other active session(s).", "revoked_count": count})


@account_bp.get("/security-events")
@login_required
def list_security_events():
    events = SecurityEvent.query.filter_by(user_id=current_user.id).order_by(SecurityEvent.created_at.desc()).limit(100).all()
    return jsonify({"events": [event.to_dict() for event in events]})
