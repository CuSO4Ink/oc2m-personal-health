"""Additive measurement history; original readings and alerts remain immutable."""
from .extensions import db
from .models import utc_now


class MeasurementDisposition(db.Model):
    __tablename__ = "measurement_dispositions"
    measurement_id = db.Column(db.Integer, db.ForeignKey("health_measurements.id"), primary_key=True)
    replacement_id = db.Column(db.Integer, db.ForeignKey("health_measurements.id"))
    reason = db.Column(db.String(300), nullable=False)
    changed_at = db.Column(db.DateTime, nullable=False, default=utc_now)


class MeasurementContext(db.Model):
    __tablename__ = "measurement_contexts"
    measurement_id = db.Column(db.Integer, db.ForeignKey("health_measurements.id"), primary_key=True)
    special_context = db.Column(db.String(30), nullable=False, default="general")
