import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, session
from flask_cors import CORS

from .extensions import db, login_manager
from .models import AccountSession, User
from .routes.account import account_bp
from .routes.auth import auth_bp
from .routes.community import community_bp
from .routes.insights import insights_bp
from .routes.notifications import notifications_bp
from .routes.overview import overview_bp
from .routes.records import records_bp
from .routes.sharing import sharing_bp
from .routes.services import services_bp
from .routes.system import system_bp
from .routes.demo import demo_bp
from .routes.extraction import extraction_bp
from .routes.advice import advice_bp
from .schema import initialize_schema


def create_app(test_config=None):
    load_dotenv()
    if not (test_config and test_config.get('TESTING')):
        load_dotenv(Path(__file__).resolve().parents[1] / '.env.deepseek', override=False)
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        APP_ENV=os.getenv("APP_ENV", "development"),
        DEMO_FEATURES_ENABLED=os.getenv("DEMO_FEATURES_ENABLED", "true" if os.getenv("APP_ENV", "development") != "production" else "false").lower() == "true",
        SECRET_KEY=os.getenv("FLASK_SECRET_KEY", "development-only-secret"),
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL", "sqlite:///personal_health.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        RESET_CODE_DELIVERY=os.getenv("RESET_CODE_DELIVERY", "demo"),
        MAX_CONTENT_LENGTH=11 * 1024 * 1024,
        DEEPSEEK_API_KEY=os.getenv('DEEPSEEK_API_KEY', ''),
        DEEPSEEK_MODEL=os.getenv('DEEPSEEK_MODEL', 'deepseek-flash'),
        DEEPSEEK_TIMEOUT=os.getenv('DEEPSEEK_TIMEOUT', '45'),
    )
    if test_config:
        app.config.update(test_config)
    app.config['DEEPSEEK_TIMEOUT'] = max(5, min(90, int(app.config['DEEPSEEK_TIMEOUT'])))
    if app.config["APP_ENV"] == "production":
        if app.config["SECRET_KEY"] in {None, "", "development-only-secret", "replace-with-a-random-development-secret"} or app.config["RESET_CODE_DELIVERY"] == "demo" or app.config["DEMO_FEATURES_ENABLED"]:
            raise ValueError("Production requires a private secret, RESET_CODE_DELIVERY=disabled, and DEMO_FEATURES_ENABLED=false. External delivery is not connected.")
        app.config.update(SESSION_COOKIE_SECURE=True, REMEMBER_COOKIE_SECURE=True)

    @app.errorhandler(413)
    def request_too_large(error):
        return {"error": "file_too_large", "message": "Each attachment must be 10 MB or smaller."}, 413

    os.makedirs(app.instance_path, exist_ok=True)
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = None
    CORS(app, resources={r"/api/*": {"origins": "http://127.0.0.1:5173"}}, supports_credentials=True)
    app.register_blueprint(demo_bp, url_prefix="/api/demo")
    app.register_blueprint(extraction_bp, url_prefix="/api/extractions")
    app.register_blueprint(advice_bp, url_prefix="/api/advice")
    app.register_blueprint(account_bp, url_prefix="/api/account")
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(community_bp, url_prefix="/api/community")
    app.register_blueprint(insights_bp, url_prefix="/api/insights")
    app.register_blueprint(notifications_bp, url_prefix="/api/notifications")
    app.register_blueprint(overview_bp, url_prefix="/api/overview")
    app.register_blueprint(records_bp, url_prefix="/api/records")
    app.register_blueprint(sharing_bp, url_prefix="/api/sharing")
    app.register_blueprint(services_bp, url_prefix="/api/services")
    app.register_blueprint(system_bp, url_prefix="/api")

    with app.app_context():
        initialize_schema()

    return app


@login_manager.user_loader
def load_user(user_id):
    try:
        identifier, separator, embedded_token = user_id.partition(":")
        token = embedded_token if separator else session.get("account_session_token")
        account_session = AccountSession.query.filter_by(user_id=int(identifier), token=token).first() if token else None
        if not account_session or not account_session.active:
            return None
        session["account_session_token"] = token
        return db.session.get(User, int(identifier))
    except (ValueError, TypeError):
        return None


@login_manager.unauthorized_handler
def unauthorized():
    return {"error": "authentication_required", "message": "Please sign in to continue."}, 401
