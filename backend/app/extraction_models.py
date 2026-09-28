"""User-reviewed extraction drafts and durable measurement provenance."""
from .extensions import db
from .models import HealthMeasurement, utc_now
from .insight_models import MeasurementDisposition


class ReportExtraction(db.Model):
    __tablename__ = "report_extractions"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    record_id = db.Column(db.Integer, db.ForeignKey("health_records.id"), nullable=False, index=True)
    # Keep the identifier/filename after a user removes the original attachment.
    attachment_id = db.Column(db.Integer)
    filename = db.Column(db.String(200), nullable=False, default="")
    source_digest = db.Column(db.String(64), nullable=False, index=True)
    source_kind = db.Column(db.String(30), nullable=False)
    method = db.Column(db.String(40), nullable=False)
    original_text = db.Column(db.Text, nullable=False)
    reviewed_text = db.Column(db.Text, nullable=False)
    candidates = db.Column(db.JSON, nullable=False)
    warnings = db.Column(db.JSON, nullable=False, default=list)
    page_info = db.Column(db.JSON, nullable=False, default=dict)
    revision = db.Column(db.Integer, nullable=False, default=1)
    confirmed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    def to_dict(self):
        return {"id": self.id, "record_id": self.record_id, "attachment_id": self.attachment_id,
                "filename": self.filename, "source_kind": self.source_kind, "method": self.method,
                "original_text": self.original_text, "reviewed_text": self.reviewed_text,
                "candidates": self.candidates, "warnings": self.warnings, "page_info": self.page_info,
                "revision": self.revision, "confirmed_at": self.confirmed_at.isoformat() + "Z" if self.confirmed_at else None,
                "created_at": self.created_at.isoformat() + "Z"}


class MeasurementSource(db.Model):
    __tablename__ = "measurement_sources"
    __table_args__ = (db.UniqueConstraint("user_id", "source_digest", "candidate_key", name="uq_extracted_candidate"),)
    measurement_id = db.Column(db.Integer, db.ForeignKey("health_measurements.id"), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    extraction_id = db.Column(db.Integer, db.ForeignKey("report_extractions.id"), nullable=False)
    record_id = db.Column(db.Integer, db.ForeignKey("health_records.id"), nullable=False)
    attachment_id = db.Column(db.Integer)
    filename = db.Column(db.String(200), nullable=False, default="")
    source_digest = db.Column(db.String(64), nullable=False)
    candidate_key = db.Column(db.String(24), nullable=False)
    evidence = db.Column(db.String(1000), nullable=False)
    original_values = db.Column(db.JSON, nullable=False)
    confirmed_values = db.Column(db.JSON, nullable=False)
    confirmed_at = db.Column(db.DateTime, nullable=False, default=utc_now)


def measurement_source_payload(measurement_id):
    measurement = db.session.get(HealthMeasurement, measurement_id)
    if not measurement:
        return None
    identifier, visited = measurement_id, set()
    source = None
    # Corrections create new immutable readings; follow their same-owner history.
    while identifier not in visited:
        visited.add(identifier)
        source = MeasurementSource.query.filter_by(measurement_id=identifier, user_id=measurement.user_id).first()
        if source:
            break
        previous = MeasurementDisposition.query.join(HealthMeasurement, HealthMeasurement.id == MeasurementDisposition.measurement_id).filter(
            MeasurementDisposition.replacement_id == identifier, HealthMeasurement.user_id == measurement.user_id).first()
        if not previous:
            break
        identifier = previous.measurement_id
    if not source:
        return None
    return {"record_id": source.record_id, "attachment_id": source.attachment_id, "original_measurement_id": source.measurement_id,
            "filename": source.filename, "extraction_id": source.extraction_id,
            "evidence": source.evidence, "original_values": source.original_values,
            "confirmed_values": source.confirmed_values,
            "confirmed_at": source.confirmed_at.isoformat() + "Z",
            "record_path": f"/records/{source.record_id}", "review_path": f"/records/{source.record_id}?extraction={source.extraction_id}"}
