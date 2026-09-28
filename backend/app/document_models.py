"""Private document text index, deliberately separate from shareable record content."""
from .extensions import db
from .models import utc_now


class DocumentIndex(db.Model):
    __tablename__ = "document_indexes"
    attachment_id = db.Column(db.Integer, db.ForeignKey("record_attachments.id"), primary_key=True)
    record_id = db.Column(db.Integer, db.ForeignKey("health_records.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    source_digest = db.Column(db.String(64), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="failed")
    total_pages = db.Column(db.Integer)
    pages = db.Column(db.JSON, nullable=False, default=list)
    warnings = db.Column(db.JSON, nullable=False, default=list)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    def summary(self):
        return {"status": self.status, "total_pages": self.total_pages,
                "processed_pages": [page["page"] for page in self.pages if page.get("text", "").strip()],
                "warnings": self.warnings, "attempts": self.attempts,
                "updated_at": self.updated_at.isoformat() + "Z"}
