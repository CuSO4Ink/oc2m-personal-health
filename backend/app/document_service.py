"""Local indexing shared by upload and simulated hospital sync."""
import hashlib
from .extensions import db
from .models import utc_now
from .document_models import DocumentIndex
from .report_parser import extract_document
from .record_audit import append_audit


def index_attachment(attachment, record, force=False):
    digest = hashlib.sha256(attachment.data).hexdigest()
    index = db.session.get(DocumentIndex, attachment.id)
    if index and index.source_digest == digest and index.status == "complete" and not force:
        return index
    if not index:
        index = DocumentIndex(attachment_id=attachment.id, record_id=record.id,
                              user_id=record.user_id, source_digest=digest, attempts=0)
        db.session.add(index)
    result = extract_document(attachment.data, attachment.content_type)
    if index.source_digest == digest and index.pages:
        old_pages = {page["page"]: page for page in index.pages if page.get("text", "").strip()}
        # A transient retry failure must not erase successfully indexed pages.
        for page in result["pages"]:
            if not page.get("text", "").strip() and page["page"] in old_pages:
                page.update(old_pages[page["page"]])
        count = sum(bool(page.get("text", "").strip()) for page in result["pages"])
        if result["total_pages"] and count == result["total_pages"]:
            result["status"] = "complete"
            result["warnings"] = []
    index.source_digest = digest
    index.pages = result["pages"]
    index.status = result["status"]
    index.total_pages = result["total_pages"]
    index.warnings = result["warnings"]
    index.attempts += 1
    index.updated_at = utc_now()
    db.session.flush()
    append_audit(record.user_id, "document_indexed", record.id,
                 {"attachment_id": attachment.id, "filename": attachment.filename,
                  "status": index.status, "total_pages": index.total_pages,
                  "processed_pages": [p["page"] for p in index.pages if p["text"].strip()]},
                 source="system", actor_name="系统整理")
    # Lazy import avoids the records/extraction route import cycle.
    from .routes.extraction import create_draft_from_document
    if index.pages:
        create_draft_from_document(record, attachment, index)
    return index
