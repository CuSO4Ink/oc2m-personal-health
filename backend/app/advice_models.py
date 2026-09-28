"""Private, additive cloud-advice consent and validated result cache."""
from .extensions import db
from .models import utc_now


class AdviceState(db.Model):
    __tablename__ = 'advice_states'
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    consent_version = db.Column(db.String(30))
    consent_at = db.Column(db.DateTime)
    lock_token = db.Column(db.String(40))
    lock_until = db.Column(db.DateTime)
    last_error_code = db.Column(db.String(40))
    last_error_at = db.Column(db.DateTime)


class AdviceResult(db.Model):
    __tablename__ = 'advice_results'
    __table_args__ = (db.UniqueConstraint('user_id', 'fingerprint', 'language', 'model', 'prompt_version', name='uq_advice_snapshot'),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    fingerprint = db.Column(db.String(64), nullable=False)
    language = db.Column(db.String(2), nullable=False)
    model = db.Column(db.String(100), nullable=False)
    prompt_version = db.Column(db.String(30), nullable=False)
    content = db.Column(db.JSON, nullable=False)
    sources = db.Column(db.JSON, nullable=False)
    input_summary = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    def payload(self):
        return {'id': self.id, 'language': self.language, 'model': self.model,
                'created_at': self.created_at.isoformat() + 'Z', 'is_ai': True,
                'sources': self.sources, 'input': self.input_summary, **self.content}
