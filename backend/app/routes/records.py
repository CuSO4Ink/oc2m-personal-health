from datetime import date
from copy import deepcopy
from difflib import SequenceMatcher
from io import BytesIO
import re
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, current_app, jsonify, request, send_file
from flask_login import current_user, login_required
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import HealthRecord, HealthRecordVersion, RecordAttachment, utc_now
from ..record_models import (PROFILE_SECTIONS, PersonalHealthProfile, ProviderImportReference,
                             RecordAnnotation, RecordImportJob, RecordLifecycle, RecordPrivacy,
                             profile_payload, record_privacy_payload)
from ..record_audit import RecordAuditEvent, append_audit
from ..document_models import DocumentIndex
from ..document_service import index_attachment
from ..extraction_models import ReportExtraction
from ..sample_catalog import hospital_samples, sample_display, with_record_display


records_bp = Blueprint("records", __name__)
RECORD_TYPES = {"Lab Report", "Visit Summary", "Medication", "Allergy", "Imaging", "Other"}


def body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def parse_date(value, field_name="record date"):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise ValueError(f"Enter a valid {field_name}.") from None


def validate_record(data):
    title = str(data.get("title") or "").strip()
    record_type = str(data.get("record_type") or "").strip()
    content = str(data.get("content") or "").strip()
    if not 2 <= len(title) <= 160:
        return None, "Enter a record title between 2 and 160 characters."
    if record_type not in RECORD_TYPES:
        return None, "Select a valid record type."
    if not content or len(content) > 30000:
        return None, "Enter record details up to 30,000 characters."
    if len(str(data.get("condition") or "")) > 120 or len(str(data.get("source_name") or "")) > 160:
        return None, "Condition or source name is too long."
    try:
        record_date = parse_date(data.get("record_date"))
    except ValueError as error:
        return None, str(error)
    return {
        "title": title,
        "record_type": record_type,
        "condition": str(data.get("condition") or "").strip(),
        "record_date": record_date,
        "source_name": str(data.get("source_name") or "Self-reported").strip() or "Self-reported",
        "content": content,
    }, None


def snapshot(record):
    return {
        "title": record.title,
        "record_type": record.record_type,
        "condition": record.condition,
        "record_date": record.record_date.isoformat(),
        "source_name": record.source_name,
        "content": record.content,
    }


def owned_record(record_id):
    return HealthRecord.query.filter_by(id=record_id, user_id=current_user.id).first()


def record_payload(record):
    result = with_record_display(record, record.to_dict())
    lifecycle = db.session.get(RecordLifecycle, record.id)
    result.update(record_privacy_payload(record.id))
    result["archived_at"] = lifecycle.archived_at.isoformat() + "Z" if lifecycle and lifecycle.archived_at else None
    result["archive_reason"] = lifecycle.archive_reason if lifecycle else ""
    result["is_editable"] = record.is_editable and not result["archived"]
    result["data_origin"] = "demonstration_provider" if record.source_type == "hospital" else "personal_entry"
    annotations = RecordAnnotation.query.filter_by(record_id=record.id, user_id=record.user_id).order_by(RecordAnnotation.created_at.desc()).all()
    result["annotations"] = [item.to_dict() for item in annotations]
    indexes = {item.attachment_id: item for item in DocumentIndex.query.filter_by(record_id=record.id, user_id=record.user_id).all()}
    latest_drafts = {}
    for draft in ReportExtraction.query.filter_by(record_id=record.id, user_id=record.user_id).order_by(ReportExtraction.id.desc()).all():
        latest_drafts.setdefault(draft.attachment_id, draft.id)
    for attachment in result["attachments"]:
        attachment["index"] = indexes[attachment["id"]].summary() if attachment["id"] in indexes else {"status": "pending", "warnings": []}
        attachment["latest_extraction_id"] = latest_drafts.get(attachment["id"])
    result["pending_extractions"] = pending_extractions(record.id, record.user_id)
    return result


def pending_extractions(record_id, user_id):
    drafts = ReportExtraction.query.filter_by(record_id=record_id, user_id=user_id).order_by(ReportExtraction.id.desc()).all()
    seen, result = set(), []
    for draft in drafts:
        if draft.attachment_id and not RecordAttachment.query.filter_by(id=draft.attachment_id, record_id=record_id).first():
            continue
        if draft.attachment_id in seen:
            continue
        seen.add(draft.attachment_id)
        if draft.confirmed_at:
            continue
        from .extraction import pending_candidate_counts
        counts = pending_candidate_counts(draft)
        count, facts = counts["measurement_count"], counts["fact_count"]
        if count or facts:
            result.append({"id": draft.id, "attachment_id": draft.attachment_id, "filename": draft.filename,
                           "candidate_count": count, "fact_count": facts})
    return result


def pending_review_records():
    rows = []
    for record in HealthRecord.query.filter_by(user_id=current_user.id).order_by(HealthRecord.record_date.desc()).all():
        if record_privacy_payload(record.id)["archived"]:
            continue
        pending = pending_extractions(record.id, current_user.id)
        if pending:
            rows.append(with_record_display(record, {"record_id": record.id, "title": record.title, "record_date": record.record_date.isoformat(), "extractions": pending}))
    return rows


@records_bp.get("/pending-review")
@login_required
def pending_document_review():
    rows = pending_review_records()
    return jsonify({"records": rows, "count": len(rows)})


def version_conflict(record):
    db.session.expire(record)
    return jsonify({"error": "version_conflict", "message": "This record changed. Compare with the latest version before saving.", "record": record_payload(record)}), 409


def claim_version(record, expected):
    if type(expected) is not int:
        return False
    changed = db.session.execute(update(HealthRecord).where(
        HealthRecord.id == record.id, HealthRecord.user_id == current_user.id,
        HealthRecord.version == expected).values(version=HealthRecord.version + 1, updated_at=utc_now()),
        execution_options={"synchronize_session": False})
    if not changed.rowcount:
        db.session.rollback()
        return False
    db.session.refresh(record)
    return True


def save_version(record, note):
    db.session.add(HealthRecordVersion(record_id=record.id, version=record.version,
        snapshot=snapshot(record), changed_by=current_user.full_name, change_note=note[:240]))


ALIASES = (("hypertension", "high blood pressure", "高血压"),
           ("diabetes", "blood glucose", "blood sugar", "糖尿病", "血糖"),
           ("allergy", "allergies", "过敏"), ("medication", "medicine", "用药", "药物"),
           ("heart rate", "pulse", "心率"))


def search_matches(record, keyword):
    text = " ".join((record.title, record.condition, record.content, record.source_name, record.record_type)).casefold()
    keyword = keyword.casefold().strip()
    terms = {keyword}
    for group in ALIASES:
        if keyword in group:
            terms.update(group)
    if any(term in text for term in terms):
        return "exact_or_alias"
    # A small, explainable fallback for a single misspelled word, never a diagnosis.
    if len(keyword) >= 4 and " " not in keyword and keyword.isascii():
        if any(abs(len(word) - len(keyword)) <= 2 and SequenceMatcher(None, keyword, word).ratio() >= .82
               for word in re.findall(r"[a-z]+", text)):
            return "approximate"
    return None


def document_matches(record_id, keyword):
    """Owner-filtered parent query gates this call; each hit identifies its actual source."""
    hits = []
    attachments = RecordAttachment.query.filter_by(record_id=record_id).all()
    for attachment in attachments:
        index = DocumentIndex.query.filter_by(attachment_id=attachment.id, user_id=current_user.id).first()
        sources = [(None, attachment.filename, "filename")]
        if index:
            sources += [(page["page"], page["text"], "document_text") for page in index.pages if page.get("text")]
        for page, text, kind in sources:
            from types import SimpleNamespace
            match = search_matches(SimpleNamespace(title=text, condition="", content="", source_name="", record_type=""), keyword)
            if not match:
                continue
            terms = {keyword.casefold()}
            for group in ALIASES:
                if keyword.casefold() in group:
                    terms.update(group)
            offsets = [text.casefold().find(term) for term in terms if term in text.casefold()]
            if not offsets and match == "approximate":
                offsets = [word.start() for word in re.finditer(r"[a-z]+", text.casefold())
                           if abs(len(word.group()) - len(keyword)) <= 2 and SequenceMatcher(None, keyword.casefold(), word.group()).ratio() >= .82]
            start = min(offsets) if offsets else 0
            start = max(0, start - 65) if start >= 0 else 0
            snippet = ("…" if start else "") + " ".join(text[start:start + 220].split())
            hits.append({"attachment_id": attachment.id, "filename": attachment.filename, "page": page,
                         "snippet": snippet, "match": match, "kind": kind,
                         "path": f"/records/{record_id}?document={attachment.id}" + (f"&page={page}" if page else "")})
            if len(hits) >= 5:
                return hits
    return hits


@records_bp.get("")
@login_required
def list_records():
    try:
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 20))
        if page < 1 or not 1 <= page_size <= 200:
            raise ValueError()
    except ValueError:
        return jsonify({"message": "Choose a positive page and a page size between 1 and 200."}), 400
    query = HealthRecord.query.filter_by(user_id=current_user.id)
    keyword = str(request.args.get("q") or "").strip()
    record_type = str(request.args.get("type") or "").strip()
    source_type = str(request.args.get("source") or "").strip()

    condition = str(request.args.get("condition") or "").strip()
    if condition:
        query = query.filter(HealthRecord.condition == condition)
    if record_type:
        query = query.filter(HealthRecord.record_type == record_type)
    if source_type in {"self", "hospital"}:
        query = query.filter(HealthRecord.source_type == source_type)
    try:
        if request.args.get("from"):
            query = query.filter(HealthRecord.record_date >= parse_date(request.args["from"], "start date"))
        if request.args.get("to"):
            query = query.filter(HealthRecord.record_date <= parse_date(request.args["to"], "end date"))
    except ValueError as error:
        return jsonify({"error": "invalid_date", "message": str(error)}), 400

    archived = request.args.get("archived", "active")
    archived_ids = db.session.query(RecordLifecycle.record_id).filter(RecordLifecycle.archived_at.is_not(None))
    if archived == "active":
        query = query.filter(HealthRecord.id.notin_(archived_ids))
    elif archived == "archived":
        query = query.filter(HealthRecord.id.in_(archived_ids))
    elif archived != "all":
        return jsonify({"message": "Choose active, archived or all records."}), 400
    query = query.order_by(HealthRecord.record_date.desc(), HealthRecord.updated_at.desc(), HealthRecord.id.desc())
    offset = (page - 1) * page_size
    matches = {}
    if keyword:
        # Stream search text rather than materialising every record, relationship and attachment.
        # Matching happens before pagination, so approximate results on later pages remain reachable.
        selected, total = [], 0
        searchable = query.with_entities(HealthRecord.id, HealthRecord.title, HealthRecord.condition,
            HealthRecord.content, HealthRecord.source_name, HealthRecord.record_type)
        for row in searchable.yield_per(200):
            match = search_matches(row, keyword)
            hits = document_matches(row.id, keyword)
            if match or hits:
                if offset <= total < offset + page_size:
                    selected.append(row.id)
                    matches[row.id] = {"match": match or hits[0]["match"], "hits": hits}
                total += 1
        records = query.filter(HealthRecord.id.in_(selected)).all() if selected else []
    else:
        total = query.order_by(None).count()
        records = query.offset(offset).limit(page_size).all()
    results = []
    for record in records:
        result = record_payload(record)
        result["search_match"] = matches.get(record.id, {}).get("match")
        result["search_hits"] = matches.get(record.id, {}).get("hits", [])
        results.append(result)
    conditions = [row[0] for row in db.session.query(HealthRecord.condition).filter(HealthRecord.user_id == current_user.id, HealthRecord.condition != "").distinct().order_by(HealthRecord.condition).all()]
    return jsonify({"records": results, "pending_records": pending_review_records(), "count": len(results), "total": total, "page": page,
                    "page_size": page_size, "conditions": conditions,
                    "search_note": "搜索标题、疾病、正文、附件名和已识别的 PDF 全文。支持名称片段、常见别名和轻微英文拼写错误；未识别页可能无法命中。"})


@records_bp.post("")
@login_required
def create_record():
    values, error = validate_record(body())
    if error:
        return jsonify({"error": "invalid_record", "message": error}), 400
    record = HealthRecord(user_id=current_user.id, source_type="self", **values)
    db.session.add(record)
    db.session.flush()
    db.session.add(HealthRecordVersion(
        record_id=record.id,
        version=1,
        snapshot=snapshot(record),
        changed_by=current_user.full_name,
        change_note="Record created",
    ))
    append_audit(current_user.id, "record_created", record.id, {"version": 1})
    db.session.commit()
    return jsonify({"record": record_payload(record)}), 201


@records_bp.get("/<int:record_id>")
@login_required
def get_record(record_id):
    record = owned_record(record_id)
    if not record:
        return jsonify({"error": "not_found", "message": "Health record not found."}), 404
    append_audit(current_user.id, "view", record.id)
    db.session.commit()
    return jsonify({"record": record_payload(record)})


@records_bp.patch("/<int:record_id>")
@login_required
def update_record(record_id):
    record = owned_record(record_id)
    if not record:
        return jsonify({"error": "not_found", "message": "Health record not found."}), 404
    if not record.is_editable or record_privacy_payload(record.id)["archived"]:
        return jsonify({"error": "read_only", "message": "Hospital-synced records preserve the source document and cannot be edited directly."}), 403
    data = body()
    values, error = validate_record(data)
    if error:
        return jsonify({"error": "invalid_record", "message": error}), 400
    if not claim_version(record, data.get("version")):
        return version_conflict(record)
    before = snapshot(record)
    for field, value in values.items():
        setattr(record, field, value)
    record.updated_at = utc_now()
    db.session.add(HealthRecordVersion(
        record_id=record.id,
        version=record.version,
        snapshot=snapshot(record),
        changed_by=current_user.full_name,
        change_note=str(data.get("change_note") or "Record updated").strip()[:240],
    ))
    append_audit(current_user.id, "edit", record.id, {"version": record.version, "changed_fields": [key for key in values if before.get(key) != snapshot(record).get(key)]})
    db.session.commit()
    return jsonify({"record": record_payload(record)})


@records_bp.get("/<int:record_id>/history")
@login_required
def record_history(record_id):
    record = owned_record(record_id)
    if not record:
        return jsonify({"error": "not_found", "message": "Health record not found."}), 404
    ascending = sorted(record.versions, key=lambda item: (item.version, item.id))
    previous = {}
    versions = []
    for version in ascending:
        item = version.to_dict()
        item["changes"] = [{"field": key, "before": previous.get(key), "after": value}
                           for key, value in item["snapshot"].items() if previous.get(key) != value]
        previous = item["snapshot"]
        item["snapshot"] = with_record_display(record, item["snapshot"])
        versions.append(item)
    events = RecordAuditEvent.query.filter_by(user_id=current_user.id, record_id=record.id).order_by(RecordAuditEvent.created_at.desc()).all()
    return jsonify({"versions": list(reversed(versions)), "events": [event.to_dict() for event in events]})


@records_bp.post("/<int:record_id>/attachments")
@login_required
def upload_attachment(record_id):
    record = owned_record(record_id)
    if not record:
        return jsonify({"message": "Health record not found."}), 404
    if not record.is_editable or record_privacy_payload(record.id)["archived"]:
        return jsonify({"message": "Attachments on provider records are read-only."}), 403
    if len(record.attachments) >= 10:
        return jsonify({"message": "A record can contain at most 10 attachments."}), 400
    upload = request.files.get("file")
    if not upload or not upload.filename:
        return jsonify({"message": "Choose a PDF, PNG or JPEG file."}), 400
    filename = upload.filename.replace("\\", "/").split("/")[-1]
    filename = "".join(char for char in filename if char.isprintable()).strip()[:200]
    data = upload.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024:
        return jsonify({"message": "Each attachment must be 10 MB or smaller."}), 413
    extension = filename.rsplit(".", 1)[-1].lower()
    content_type = None
    if extension == "pdf" and data.startswith(b"%PDF-") and b"%%EOF" in data[-1024:]:
        content_type = "application/pdf"
    elif extension == "png" and data.startswith(b"\x89PNG\r\n\x1a\n") and b"IEND" in data[-20:]:
        content_type = "image/png"
    elif extension in {"jpg", "jpeg"} and data.startswith(b"\xff\xd8\xff") and data.endswith(b"\xff\xd9"):
        content_type = "image/jpeg"
    if not content_type:
        return jsonify({"message": "File content must match a PDF, PNG or JPEG file. Other formats are not supported."}), 400
    attachment = RecordAttachment(record_id=record.id, filename=filename, content_type=content_type, size=len(data), data=data)
    # The API supports explicit optimistic locking; legacy clients still use the current version.
    expected = request.form.get("version", str(record.version))
    if not str(expected).isdigit() or not claim_version(record, int(expected)):
        return version_conflict(record)
    db.session.add(attachment)
    db.session.flush()
    append_audit(current_user.id, "attachment_added", record.id, {"attachment_id": attachment.id, "filename": filename, "size": len(data), "version": record.version})
    save_version(record, f"Attachment added: {filename}")
    record.updated_at = utc_now()
    index_attachment(attachment, record)
    db.session.commit()
    db.session.expire(record, ["attachments"])
    payload = record_payload(record)
    return jsonify({"attachment": next(item for item in payload["attachments"] if item["id"] == attachment.id), "record": payload}), 201


@records_bp.post("/<int:record_id>/attachments/<int:attachment_id>/index")
@login_required
def retry_document_index(record_id, attachment_id):
    record = owned_record(record_id)
    attachment = RecordAttachment.query.filter_by(id=attachment_id, record_id=record_id).first() if record else None
    if not attachment:
        return jsonify({"message": "找不到这份文件。"}), 404
    if record_privacy_payload(record.id)["archived"]:
        return jsonify({"message": "请先恢复归档资料，再重新整理。"}), 409
    index_attachment(attachment, record, force=True)
    db.session.commit()
    return jsonify({"record": record_payload(record)})


@records_bp.patch("/<int:record_id>/classification")
@login_required
def change_classification(record_id):
    record = owned_record(record_id)
    if not record:
        return jsonify({"message": "找不到这条记录。"}), 404
    data = body()
    if data.get("record_type") not in RECORD_TYPES or len(str(data.get("condition", ""))) > 120:
        return jsonify({"message": "请选择有效分类，疾病或主题最多 120 字。"}), 400
    if record_privacy_payload(record.id)["archived"]:
        return jsonify({"message": "请先恢复归档资料。"}), 409
    before = {"record_type": record.record_type, "condition": record.condition}
    if not claim_version(record, data.get("version")):
        return version_conflict(record)
    record.record_type = data["record_type"]
    record.condition = str(data.get("condition", record.condition)).strip()
    save_version(record, "个人整理分类已更新；原始文件未改变")
    append_audit(current_user.id, "record_classified", record.id, {"before": before,
                 "after": {"record_type": record.record_type, "condition": record.condition}})
    db.session.commit()
    return jsonify({"record": record_payload(record)})


@records_bp.get("/<int:record_id>/attachments/<int:attachment_id>")
@login_required
def attachment_content(record_id, attachment_id):
    if not owned_record(record_id):
        return jsonify({"message": "Health record not found."}), 404
    attachment = RecordAttachment.query.filter_by(id=attachment_id, record_id=record_id).first()
    if not attachment:
        return jsonify({"message": "Attachment not found."}), 404
    append_audit(current_user.id, "download" if request.args.get("download") == "1" else "attachment_view", record_id,
                 {"attachment_id": attachment.id, "filename": attachment.filename})
    db.session.commit()
    response = send_file(BytesIO(attachment.data), mimetype=attachment.content_type,
                         download_name=attachment.filename, as_attachment=request.args.get("download") == "1", max_age=0)
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@records_bp.delete("/<int:record_id>/attachments/<int:attachment_id>")
@login_required
def delete_attachment(record_id, attachment_id):
    record = owned_record(record_id)
    if not record:
        return jsonify({"message": "Health record not found."}), 404
    if not record.is_editable or record_privacy_payload(record.id)["archived"]:
        return jsonify({"message": "Attachments on provider records are read-only."}), 403
    attachment = RecordAttachment.query.filter_by(id=attachment_id, record_id=record_id).first()
    if not attachment:
        return jsonify({"message": "Attachment not found."}), 404
    expected = body().get("version", record.version)
    if not claim_version(record, expected):
        return version_conflict(record)
    append_audit(current_user.id, "attachment_deleted", record.id, {"attachment_id": attachment.id, "filename": attachment.filename, "size": attachment.size, "version": record.version})
    save_version(record, f"Attachment removed: {attachment.filename}")
    db.session.delete(attachment)
    DocumentIndex.query.filter_by(attachment_id=attachment.id).delete()
    record.updated_at = utc_now()
    db.session.commit()
    db.session.expire(record, ["attachments"])
    return jsonify({"record": record_payload(record)})


@records_bp.get("/profile")
@login_required
def get_health_profile():
    return jsonify({"profile": profile_payload(current_user.id)})


@records_bp.get("/profile/history")
@login_required
def get_health_profile_history():
    events = RecordAuditEvent.query.filter_by(user_id=current_user.id, action="health_profile_updated").order_by(RecordAuditEvent.created_at.desc(), RecordAuditEvent.id.desc()).all()
    revisions = {}
    for event in events:
        revision = event.details.get("revision")
        if revision is not None and (revision not in revisions or not revisions[revision]["snapshot"]):
            revisions[revision] = {"revision": revision, "snapshot": event.details.get("snapshot"),
                "created_at": event.created_at.isoformat() + "Z", "actor_name": event.actor_name}
        previous = event.details.get("previous_revision")
        if previous and previous not in revisions and event.details.get("previous_snapshot"):
            revisions[previous] = {"revision": previous, "snapshot": event.details["previous_snapshot"],
                "created_at": event.details.get("previous_updated_at"), "actor_name": "Your previous saved profile"}
    current = profile_payload(current_user.id)
    if current["revision"] and (current["revision"] not in revisions or not revisions[current["revision"]]["snapshot"]):
        revisions[current["revision"]] = {"revision": current["revision"], "snapshot": current["sections"],
            "created_at": current["updated_at"], "actor_name": current_user.full_name}
    return jsonify({"revisions": sorted(revisions.values(), key=lambda item: item["revision"], reverse=True)})


@records_bp.put("/profile")
@login_required
def save_health_profile():
    data = body()
    sections = data.get("sections")
    if not isinstance(sections, dict) or set(sections) != set(PROFILE_SECTIONS):
        return jsonify({"message": "Provide all four health profile sections."}), 400
    cleaned = {}
    fields_by_section = {
        "past_history": {"name", "detail", "start_date", "end_date"},
        "family_history": {"name", "detail", "relationship"},
        "medications": {"name", "detail", "dose", "frequency", "start_date", "end_date"},
        "allergies": {"name", "detail", "severity"},
    }
    for key in PROFILE_SECTIONS:
        section = sections[key]
        if not isinstance(section, dict) or not isinstance(section.get("status"), str) or section.get("status") not in {"unknown", "none", "recorded"}:
            return jsonify({"message": "Choose unknown, none known or recorded for each section."}), 400
        items = section.get("items", [])
        if not isinstance(items, list) or len(items) > 100 or bool(items) != (section["status"] == "recorded"):
            return jsonify({"message": "Recorded sections need at least one entry; unknown or none known must have no entries. Maximum 100 per section."}), 400
        rows, ids = [], set()
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("sensitive", False), bool):
                return jsonify({"message": "Provide valid profile entries and sensitivity flags."}), 400
            entry = {field: str(item.get(field) or "").strip() for field in fields_by_section[key]}
            if not entry["name"] or len(entry["name"]) > 160 or any(len(value) > 1000 for value in entry.values()):
                return jsonify({"message": "Each entry needs a name up to 160 characters; other fields allow up to 1,000."}), 400
            for date_key in ("start_date", "end_date"):
                if entry.get(date_key):
                    try:
                        entry[date_key] = parse_date(entry[date_key]).isoformat()
                    except ValueError:
                        return jsonify({"message": "Enter valid dates in the health profile."}), 400
            if entry.get("start_date") and entry.get("end_date") and entry["end_date"] < entry["start_date"]:
                return jsonify({"message": "End date cannot be before start date."}), 400
            if key == "family_history" and not entry["relationship"]:
                return jsonify({"message": "Add the relative or relationship for family history."}), 400
            entry_id = str(item.get("id") or uuid4())[:80]
            if entry_id in ids:
                return jsonify({"message": "Profile entry identifiers must be unique."}), 400
            ids.add(entry_id)
            entry.update(id=entry_id, sensitive=item.get("sensitive", False))
            rows.append(entry)
        cleaned[key] = {"status": section["status"], "items": rows}
    expected = data.get("revision")
    if type(expected) is not int:
        return jsonify({"message": "Include the profile revision."}), 400
    previous_profile = deepcopy(profile_payload(current_user.id))
    if expected == 0:
        try:
            db.session.add(PersonalHealthProfile(user_id=current_user.id, revision=1, sections=cleaned))
            db.session.flush()
        except IntegrityError:
            db.session.rollback()
            return jsonify({"message": "Profile changed. Reload before saving.", "profile": profile_payload(current_user.id)}), 409
    else:
        changed = db.session.execute(update(PersonalHealthProfile).where(
            PersonalHealthProfile.user_id == current_user.id, PersonalHealthProfile.revision == expected
        ).values(sections=cleaned, revision=expected + 1, updated_at=utc_now()))
        if not changed.rowcount:
            db.session.rollback()
            return jsonify({"message": "Profile changed. Reload before saving.", "profile": profile_payload(current_user.id)}), 409
    append_audit(current_user.id, "health_profile_updated", details={"revision": expected + 1, "snapshot": cleaned,
        "previous_revision": previous_profile["revision"], "previous_snapshot": previous_profile["sections"],
        "previous_updated_at": previous_profile["updated_at"]})
    db.session.commit()
    return jsonify({"profile": profile_payload(current_user.id)})


@records_bp.patch("/<int:record_id>/archive")
@login_required
def archive_record(record_id):
    record = owned_record(record_id)
    if not record:
        return jsonify({"message": "Health record not found."}), 404
    data = body()
    if not isinstance(data.get("archived"), bool):
        return jsonify({"message": "Choose archive or restore."}), 400
    if not claim_version(record, data.get("version")):
        return version_conflict(record)
    lifecycle = db.session.get(RecordLifecycle, record.id)
    if not lifecycle:
        lifecycle = RecordLifecycle(record_id=record.id)
        db.session.add(lifecycle)
    lifecycle.archived_at = utc_now() if data["archived"] else None
    lifecycle.archive_reason = str(data.get("reason") or "").strip()[:240]
    action = "record_archived" if data["archived"] else "record_restored"
    save_version(record, "Record archived" if data["archived"] else "Record restored")
    append_audit(current_user.id, action, record.id, {"reason": lifecycle.archive_reason, "version": record.version})
    db.session.commit()
    return jsonify({"record": record_payload(record)})


@records_bp.patch("/<int:record_id>/privacy")
@login_required
def set_record_privacy(record_id):
    record = owned_record(record_id)
    if not record:
        return jsonify({"message": "Health record not found."}), 404
    data = body()
    fields = data.get("sensitive_fields", [])
    allowed = {"title", "record_type", "record_date", "source_name", "condition", "content"}
    if not isinstance(data.get("sensitive"), bool) or not isinstance(fields, list) or any(not isinstance(field, str) or field not in allowed for field in fields):
        return jsonify({"message": "Choose valid sensitivity settings."}), 400
    if not claim_version(record, data.get("version")):
        return version_conflict(record)
    privacy = db.session.get(RecordPrivacy, record.id)
    if not privacy:
        privacy = RecordPrivacy(record_id=record.id)
        db.session.add(privacy)
    privacy.sensitive = data["sensitive"]
    privacy.sensitive_fields = sorted(set(fields))
    save_version(record, "Privacy labels updated")
    append_audit(current_user.id, "privacy_updated", record.id, {"sensitive": privacy.sensitive, "sensitive_fields": privacy.sensitive_fields, "version": record.version})
    db.session.commit()
    return jsonify({"record": record_payload(record)})


@records_bp.post("/<int:record_id>/annotations")
@login_required
def add_annotation(record_id):
    record = owned_record(record_id)
    if not record:
        return jsonify({"message": "Health record not found."}), 404
    data = body()
    kind = data.get("kind", "note")
    content = str(data.get("content") or "").strip()
    if not isinstance(kind, str) or kind not in {"note", "correction"} or not 3 <= len(content) <= 2000:
        return jsonify({"message": "Choose a note or correction request and enter 3–2,000 characters."}), 400
    annotation = RecordAnnotation(record_id=record.id, user_id=current_user.id, kind=kind,
        content=content, status="awaiting_review" if kind == "correction" else "saved")
    db.session.add(annotation)
    db.session.flush()
    append_audit(current_user.id, f"{kind}_added", record.id, {"annotation_id": annotation.id})
    db.session.commit()
    return jsonify({"record": record_payload(record), "message": "Saved locally. No information was sent to a provider."}), 201


@records_bp.post("/<int:record_id>/annotations/<int:annotation_id>/simulate-response")
@login_required
def simulate_correction_response(record_id, annotation_id):
    if not current_app.config.get("DEMO_FEATURES_ENABLED", True):
        return jsonify({"error": "not_connected", "message": "Simulated provider responses are disabled in this environment."}), 503
    record = owned_record(record_id)
    annotation = RecordAnnotation.query.filter_by(id=annotation_id, record_id=record_id, user_id=current_user.id, kind="correction").first() if record else None
    if not annotation:
        return jsonify({"message": "Correction request not found."}), 404
    if annotation.status != "awaiting_review":
        return jsonify({"record": record_payload(record)})
    annotation.status = "simulated_response"
    annotation.response = "Demonstration response: your correction has been noted for review. The original provider record remains unchanged. No provider received this request."
    annotation.updated_at = utc_now()
    append_audit(current_user.id, "correction_response", record.id, {"annotation_id": annotation.id}, source="simulation", actor_name="Simulated provider")
    db.session.commit()
    return jsonify({"record": record_payload(record)})


@records_bp.get("/audit")
@login_required
def personal_audit():
    events = RecordAuditEvent.query.filter_by(user_id=current_user.id).order_by(RecordAuditEvent.created_at.desc(), RecordAuditEvent.id.desc()).limit(300).all()
    return jsonify({"events": [event.to_dict() for event in events]})


def demo_import_items():
    rows = hospital_samples()
    results = []
    for row in rows:
        suggestion, reason = row["record_type"], "Uses the type supplied by the simulated hospital. Personal classification can be changed; the original file is preserved."
        results.append({**{key: value for key, value in row.items() if key != "display_zh"}, "sample_display": sample_display(row["external_id"], row), "suggested_type": suggestion, "classification_reason": reason,
            "status": "ready", "attempts": 0,
            "selected_type": suggestion, "record_id": None, "error": ""})
    return results


def classify_text(title, content):
    text = f"{title} {content}".casefold()
    rules = [("Allergy", ("allergy", "allergic", "过敏")),
             ("Medication", ("medication", "prescription", "处方", "药物")),
             ("Imaging", ("x-ray", "mri", "ultrasound", "影像", "超声")),
             ("Lab Report", ("blood test", "laboratory", "lab report", "化验", "检验")),
             ("Visit Summary", ("follow-up", "visit summary", "consultation", "就诊", "复诊"))]
    for category, terms in rules:
        match = next((term for term in terms if term in text), None)
        if match:
            return category, f"Keyword rule matched '{match}'. Confirm the suggested category manually."
    return "Other", "No category keyword matched. Confirm the type manually."


@records_bp.post("/classify")
@login_required
def classify_record():
    data = body()
    title, content = str(data.get("title") or "")[:160], str(data.get("content") or "")[:30000]
    category, reason = classify_text(title, content)
    return jsonify({"record_type": category, "reason": reason, "method": "keyword_rules", "requires_confirmation": True})


def import_job_payload(job):
    payload = job.to_dict()
    payload["items"] = [{**item, "sample_display": sample_display(item["external_id"], item)} for item in payload["items"]]
    return payload


@records_bp.get("/imports")
@login_required
def list_imports():
    jobs = RecordImportJob.query.filter_by(user_id=current_user.id).order_by(RecordImportJob.created_at.desc()).limit(30).all()
    return jsonify({"jobs": [import_job_payload(job) for job in jobs]})


@records_bp.post("/imports")
@login_required
def preview_import():
    if not current_app.config.get("DEMO_FEATURES_ENABLED", True):
        return jsonify({"error": "not_connected", "message": "Simulated provider imports are disabled in this environment."}), 503
    job = RecordImportJob(user_id=current_user.id, items=demo_import_items())
    db.session.add(job)
    db.session.commit()
    return jsonify({"job": import_job_payload(job), "message": "Simulated provider batch. Review classifications before importing. No hospital connection is made."}), 201


@records_bp.get("/imports/samples/<external_id>")
@login_required
def preview_hospital_sample(external_id):
    if not current_app.config.get("DEMO_FEATURES_ENABLED", True):
        return jsonify({"message": "模拟医院功能已关闭。"}), 503
    item = next((item for item in demo_import_items() if item["external_id"] == external_id), None)
    if not item:
        return jsonify({"message": "找不到样本。"}), 404
    content = (Path(__file__).parents[1] / "hospital_samples" / item["filename"]).read_bytes()
    return send_file(BytesIO(content), mimetype="application/pdf", download_name=item["filename"], max_age=0)


def process_import(job_id, retry=False):
    if not current_app.config.get("DEMO_FEATURES_ENABLED", True):
        return jsonify({"error": "not_connected", "message": "Simulated provider imports are disabled in this environment."}), 503
    job = RecordImportJob.query.filter_by(id=job_id, user_id=current_user.id).first()
    if not job:
        return jsonify({"message": "Import batch not found."}), 404
    data = body()
    if type(data.get("revision")) is not int:
        return jsonify({"message": "Include the batch revision."}), 400
    selections = data.get("selections", {})
    ready_ids = {item["external_id"] for item in job.items if item["status"] == "ready"}
    if not retry and (not isinstance(selections, dict) or any(not isinstance(selections.get(key), str) or selections.get(key) not in RECORD_TYPES for key in ready_ids)):
        return jsonify({"message": "Confirm a record type for every ready item."}), 400
    claimed = db.session.execute(update(RecordImportJob).where(RecordImportJob.id == job.id,
        RecordImportJob.revision == data["revision"]).values(revision=RecordImportJob.revision + 1, updated_at=utc_now()),
        execution_options={"synchronize_session": False})
    if not claimed.rowcount:
        db.session.rollback()
        db.session.refresh(job)
        return jsonify({"message": "This batch changed. Reload its latest results.", "job": import_job_payload(job)}), 409
    db.session.refresh(job)
    items = deepcopy(job.items)
    for item in items:
        if item["status"] != ("failed" if retry else "ready"):
            continue
        item["selected_type"] = item["selected_type"] if retry else selections[item["external_id"]]
        existing = ProviderImportReference.query.filter_by(user_id=current_user.id, provider="demo_hospital", external_id=item["external_id"]).first()
        if existing:
            item.update(status="duplicate", record_id=existing.record_id, error="Already imported. Existing record preserved, including any archive state.")
            continue
        item["attempts"] += 1
        if data.get("simulate_failure_once") is True and item["external_id"] == "hospital-care" and item["attempts"] == 1:
            item.update(status="failed", error="Simulated temporary provider failure. Retry this item; successful items are preserved.")
            continue
        record = HealthRecord(user_id=current_user.id, title=item["title"], record_type=item["selected_type"],
            condition=item["condition"], content=item["content"], record_date=parse_date(item["record_date"]),
            source_type="hospital", source_name=item.get("source_name", "Maple Grove General Hospital (simulation)"), synced_at=utc_now())
        db.session.add(record)
        db.session.flush()
        sample = next((row for row in demo_import_items() if row["external_id"] == item["external_id"]), None)
        if sample:
            pdf = (Path(__file__).parents[1] / "hospital_samples" / sample["filename"]).read_bytes()
            attachment = RecordAttachment(record_id=record.id, filename=sample["filename"], content_type="application/pdf", size=len(pdf), data=pdf)
            db.session.add(attachment)
            db.session.flush()
            index = index_attachment(attachment, record)
            item.update(attachment_id=attachment.id, index_status=index.status,
                        pending_extractions=pending_extractions(record.id, current_user.id))
        db.session.add(ProviderImportReference(user_id=current_user.id, record_id=record.id,
            provider="demo_hospital", external_id=item["external_id"]))
        save_version(record, "Simulated provider import; classification confirmed by owner")
        append_audit(current_user.id, "record_imported", record.id, {"batch_id": job.id, "external_id": item["external_id"]}, source="simulation", actor_name="Simulated provider")
        item.update(status="imported", record_id=record.id, error="")
    job.items = items
    db.session.commit()
    return jsonify({"job": import_job_payload(job)})


@records_bp.post("/imports/<int:job_id>/confirm")
@login_required
def confirm_import(job_id):
    return process_import(job_id)


@records_bp.post("/imports/<int:job_id>/retry")
@login_required
def retry_import(job_id):
    return process_import(job_id, retry=True)
