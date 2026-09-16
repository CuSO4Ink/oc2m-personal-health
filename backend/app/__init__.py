import os

from dotenv import load_dotenv
from flask import Flask
from flask_cors import CORS

from .extensions import db, login_manager
from .models import User
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
        MAX_CONTENT_LENGTH=11 * 1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)

    @app.errorhandler(413)
    def request_too_large(error):
        return {"error": "file_too_large", "message": "Each attachment must be 10 MB or smaller."}, 413

    os.makedirs(app.instance_path, exist_ok=True)
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = None
    CORS(app, resources={r"/api/*": {"origins": "http://127.0.0.1:5173"}}, supports_credentials=True)
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
        db.create_all()

    return app


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


@login_manager.unauthorized_handler
def unauthorized():
    return {"error": "authentication_required", "message": "Please sign in to continue."}, 401
