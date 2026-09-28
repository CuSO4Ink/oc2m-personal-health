from .extensions import db
from .models import utc_now


class ReminderCancellation(db.Model):
    __tablename__ = "reminder_cancellations"
    reminder_id = db.Column(db.Integer, db.ForeignKey("health_reminders.id"), primary_key=True)
    cancelled_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    reminder = db.relationship("HealthReminder", backref=db.backref("cancellation", uselist=False))


class ServiceClinician(db.Model):
    __tablename__ = "service_clinicians"
    service_id = db.Column(db.Integer, db.ForeignKey("medical_services.id"), primary_key=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey("share_recipients.id"), primary_key=True)
    recipient = db.relationship("ShareRecipient")


class AppointmentSharing(db.Model):
    __tablename__ = "appointment_sharing"
    appointment_id = db.Column(db.Integer, db.ForeignKey("appointments.id"), primary_key=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey("share_recipients.id"), nullable=False)
    grant_id = db.Column(db.Integer, db.ForeignKey("share_grants.id"))
    recipient = db.relationship("ShareRecipient")
    grant = db.relationship("ShareGrant")
