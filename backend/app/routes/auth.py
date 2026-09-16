import secrets
import hashlib
from datetime import timedelta

from flask import Blueprint, current_app, jsonify, request, session
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db
from ..models import AccountSession, AuthAttempt, PasswordResetToken, SecurityEvent, User, utc_now


auth_bp = Blueprint("auth", __name__)


def body():
    return request.get_json(silent=True) or {}


def normalise_email(value):
    return str(value or "").strip().lower()


def validate_password(password):
    if len(password) > 128:
        return "Password must be 128 characters or fewer."
    if len(password) < 8:
        return "Password must contain at least 8 characters."
    if not any(character.isalpha() for character in password) or not any(character.isdigit() for character in password):
        return "Password must include at least one letter and one number."
    return None


def throttle(scope, email, limit=5, minutes=15, record=False):
    key = hashlib.sha256(f"{scope}:{email}:{request_ip()}".encode()).hexdigest()
    cutoff = utc_now() - timedelta(minutes=minutes)
    AuthAttempt.query.filter(AuthAttempt.created_at < utc_now() - timedelta(days=1)).delete()
    if AuthAttempt.query.filter(AuthAttempt.key == key, AuthAttempt.created_at >= cutoff).count() >= limit:
        response = jsonify({"error": "rate_limited", "message": f"Too many attempts. Try again in {minutes} minutes."})
        response.headers["Retry-After"] = str(minutes * 60)
        return response, 429
    if record:
        db.session.add(AuthAttempt(key=key)); db.session.commit()
    return None


def request_device_name():
    agent = str(request.user_agent.string or "").lower()
    browser = "Chrome" if "chrome" in agent else "Safari" if "safari" in agent else "Firefox" if "firefox" in agent else "Web browser"
    platform = "macOS" if "macintosh" in agent or "mac os" in agent else "Windows" if "windows" in agent else "Mobile" if "mobile" in agent else "Unknown device"
    return f"{browser} on {platform}"


def request_ip():
    return str(request.remote_addr or "Unavailable")[:80]


def record_security_event(user_id, event_type, description, result="success", important=False):
    db.session.add(SecurityEvent(
        user_id=user_id,
        event_type=event_type,
        description=description,
        result=result,
        ip_address=request_ip(),
        device_name=request_device_name(),
        important=important,
    ))


def create_account_session(user, remember=False):
    token = secrets.token_urlsafe(36)
    now = utc_now()
    account_session = AccountSession(
        user_id=user.id,
        token=token,
        device_name=request_device_name(),
        ip_address=request_ip(),
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(days=30 if remember else 1),
    )
    db.session.add(account_session)
    session["account_session_token"] = token
    return account_session


def ensure_account_session():
    token = session.get("account_session_token")
    account_session = AccountSession.query.filter_by(token=token, user_id=current_user.id).first() if token else None
    if not account_session:
        account_session = create_account_session(current_user, remember=False)
        record_security_event(current_user.id, "session_created", "This browser was added as an active session.")
        db.session.commit()
    return account_session


@auth_bp.before_app_request
def enforce_revoked_session():
    if not current_user.is_authenticated:
        return None
    token = session.get("account_session_token")
    if not token:
        return None
    account_session = AccountSession.query.filter_by(token=token, user_id=current_user.id).first()
    if not account_session or not account_session.active:
        session.pop("account_session_token", None)
        logout_user()
        if request.path.startswith("/api/"):
            return jsonify({"error": "session_ended", "message": "This session has ended. Please sign in again."}), 401
        return None
    if account_session.last_seen_at < utc_now() - timedelta(minutes=5):
        account_session.last_seen_at = utc_now()
        db.session.commit()
    return None


@auth_bp.post("/register")
def register():
    data = body()
    email = normalise_email(data.get("email"))
    full_name = str(data.get("full_name") or "").strip()
    password = str(data.get("password") or "")

    if not email or "@" not in email:
        return jsonify({"error": "invalid_email", "message": "Enter a valid email address."}), 400
    if len(full_name) < 2:
        return jsonify({"error": "invalid_name", "message": "Enter your full name."}), 400
    password_error = validate_password(password)
    if password_error:
        return jsonify({"error": "invalid_password", "message": password_error}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "email_exists", "message": "An account with this email already exists."}), 409

    user = User(email=email, full_name=full_name, role="patient")
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    create_account_session(user)
    login_user(user)
    record_security_event(user.id, "account_created", "Your account was created and signed in.")
    db.session.commit()
    return jsonify({"user": user.to_dict()}), 201


@auth_bp.post("/login")
def login():
    data = body()
    email = normalise_email(data.get("email"))
    password = str(data.get("password") or "")
    limited = throttle("login", email)
    if limited:
        return limited
    user = User.query.filter_by(email=email).first()

    if not user or not user.check_password(password):
        throttle("login", email, record=True)
        if user:
            record_security_event(user.id, "login_failed", "A sign-in attempt used an incorrect password.", result="blocked", important=True)
            db.session.commit()
        return jsonify({"error": "invalid_credentials", "message": "The email address or password is incorrect."}), 401

    remember = bool(data.get("remember"))
    session.clear()
    if not remember:
        session["_remember"] = "clear"
    create_account_session(user, remember=remember)
    login_user(user, remember=remember)
    record_security_event(user.id, "login", "Signed in successfully.")
    db.session.commit()
    return jsonify({"user": user.to_dict()})


@auth_bp.post("/logout")
@login_required
def logout():
    token = session.get("account_session_token")
    account_session = AccountSession.query.filter_by(token=token, user_id=current_user.id).first() if token else None
    if account_session and account_session.active:
        account_session.revoked_at = utc_now()
    record_security_event(current_user.id, "logout", "Signed out from this browser.")
    db.session.commit()
    session.pop("account_session_token", None)
    logout_user()
    return jsonify({"message": "Signed out successfully."})


@auth_bp.get("/me")
def me():
    if not current_user.is_authenticated:
        return jsonify({"user": None})
    return jsonify({"user": current_user.to_dict()})


@auth_bp.post("/password-reset/request")
def request_password_reset():
    email = normalise_email(body().get("email"))
    limited = throttle("reset-request", email, limit=3, minutes=10, record=True)
    if limited:
        return limited
    user = User.query.filter_by(email=email).first()
    response = {"message": "If this email belongs to an account, a reset code has been prepared."}

    if user:
        PasswordResetToken.query.filter_by(user_id=user.id, used_at=None).delete()
        code = f"{secrets.randbelow(1_000_000):06d}"
        token = PasswordResetToken(user_id=user.id, expires_at=utc_now() + timedelta(minutes=10))
        token.set_code(code)
        db.session.add(token)
        db.session.commit()
        if current_app.config["RESET_CODE_DELIVERY"] == "demo":
            response["demo_code"] = code

    return jsonify(response)


@auth_bp.post("/password-reset/confirm")
def confirm_password_reset():
    data = body()
    email = normalise_email(data.get("email"))
    limited = throttle("reset-confirm", email, record=True)
    if limited:
        return limited
    code = str(data.get("code") or "").strip()
    password = str(data.get("password") or "")
    user = User.query.filter_by(email=email).first()
    password_error = validate_password(password)
    if password_error:
        return jsonify({"error": "invalid_password", "message": password_error}), 400
    if not user:
        return jsonify({"error": "invalid_reset", "message": "The reset code is invalid or has expired."}), 400

    token = PasswordResetToken.query.filter_by(user_id=user.id, used_at=None).order_by(PasswordResetToken.created_at.desc()).first()
    if not token or token.expires_at <= utc_now() or not token.check_code(code):
        return jsonify({"error": "invalid_reset", "message": "The reset code is invalid or has expired."}), 400

    token.used_at = utc_now()
    user.set_password(password)
    AccountSession.query.filter_by(user_id=user.id, revoked_at=None).update({"revoked_at": utc_now()})
    record_security_event(user.id, "password_reset", "Password was reset using an account recovery code.", important=True)
    db.session.commit()
    return jsonify({"message": "Your password has been reset. You can now sign in."})
