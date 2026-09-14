from app import create_app
from app.extensions import db
from app.models import User


DEMO_EMAIL = "alex.morgan@example.com"
DEMO_PASSWORD = "HealthDemo2026!"


app = create_app()
with app.app_context():
    user = User.query.filter_by(email=DEMO_EMAIL).first()
    if not user:
        user = User(email=DEMO_EMAIL, full_name="Alex Morgan", role="patient")
        db.session.add(user)
    user.set_password(DEMO_PASSWORD)
    db.session.commit()
    print(f"Demo account ready: {DEMO_EMAIL}")

