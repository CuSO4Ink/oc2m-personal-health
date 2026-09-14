import secrets
from datetime import timedelta

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db
from ..models import PasswordResetToken, User, utc_now


auth_bp = Blueprint("auth", __name__)


def body():
    return request.get_json(silent=True) or {}


def normalise_email(value):
    return str(value or "").strip().lower()


def validate_password(password):
    if len(password) < 8:
        return "Password must contain at least 8 characters."
    if not any(character.isalpha() for character in password) or not any(character.isdigit() for character in password):
        return "Password must include at least one letter and one number."
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
    db.session.commit()
    login_user(user)
    return jsonify({"user": user.to_dict()}), 201


@auth_bp.post("/login")
def login():
    data = body()
    email = normalise_email(data.get("email"))
    password = str(data.get("password") or "")
    user = User.query.filter_by(email=email).first()

    if not user or not user.check_password(password):
        return jsonify({"error": "invalid_credentials", "message": "The email address or password is incorrect."}), 401

    login_user(user, remember=bool(data.get("remember")))
    return jsonify({"user": user.to_dict()})


@auth_bp.post("/logout")
@login_required
def logout():
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
    db.session.commit()
    return jsonify({"message": "Your password has been reset. You can now sign in."})

