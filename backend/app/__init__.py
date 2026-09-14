import os

from dotenv import load_dotenv
from flask import Flask
from flask_cors import CORS

from .extensions import db, login_manager
from .models import User
from .routes.auth import auth_bp
from .routes.system import system_bp


def create_app(test_config=None):
    load_dotenv()
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.getenv("FLASK_SECRET_KEY", "development-only-secret"),
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL", "sqlite:///personal_health.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        RESET_CODE_DELIVERY=os.getenv("RESET_CODE_DELIVERY", "demo"),
    )
    if test_config:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = None
    CORS(app, resources={r"/api/*": {"origins": "http://127.0.0.1:5173"}}, supports_credentials=True)
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(system_bp, url_prefix="/api")

    with app.app_context():
        db.create_all()

    return app


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


@login_manager.unauthorized_handler
def unauthorized():
    return {"error": "authentication_required", "message": "Please sign in to continue."}, 401
