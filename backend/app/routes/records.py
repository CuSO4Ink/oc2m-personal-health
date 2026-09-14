from datetime import date

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import or_

from ..extensions import db
from ..models import HealthRecord, HealthRecordVersion, utc_now


records_bp = Blueprint("records", __name__)
RECORD_TYPES = {"Lab Report", "Visit Summary", "Medication", "Allergy", "Imaging", "Other"}


def body():
    return request.get_json(silent=True) or {}


def parse_date(value, field_name="record date"):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise ValueError(f"Enter a valid {field_name}.") from None


def validate_record(data):
    title = str(data.get("title") or "").strip()
    record_type = str(data.get("record_type") or "").strip()
    content = str(data.get("content") or "").strip()
    if len(title) < 2:
        return None, "Enter a record title."
    if record_type not in RECORD_TYPES:
        return None, "Select a valid record type."
    if not content:
        return None, "Enter the record details."
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


@records_bp.get("")
@login_required
def list_records():
    query = HealthRecord.query.filter_by(user_id=current_user.id)
    keyword = str(request.args.get("q") or "").strip()
    record_type = str(request.args.get("type") or "").strip()
    source_type = str(request.args.get("source") or "").strip()

    if keyword:
        term = f"%{keyword}%"
        query = query.filter(or_(
            HealthRecord.title.ilike(term),
            HealthRecord.condition.ilike(term),
            HealthRecord.content.ilike(term),
            HealthRecord.source_name.ilike(term),
        ))
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

    records = query.order_by(HealthRecord.record_date.desc(), HealthRecord.updated_at.desc()).all()
    return jsonify({"records": [record.to_dict() for record in records], "count": len(records)})


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
    db.session.commit()
    return jsonify({"record": record.to_dict()}), 201


@records_bp.get("/<int:record_id>")
@login_required
def get_record(record_id):
    record = owned_record(record_id)
    if not record:
        return jsonify({"error": "not_found", "message": "Health record not found."}), 404
    return jsonify({"record": record.to_dict()})


@records_bp.patch("/<int:record_id>")
@login_required
def update_record(record_id):
    record = owned_record(record_id)
    if not record:
        return jsonify({"error": "not_found", "message": "Health record not found."}), 404
    if not record.is_editable:
        return jsonify({"error": "read_only", "message": "Hospital-synced records preserve the source document and cannot be edited directly."}), 403
    data = body()
    if data.get("version") != record.version:
        return jsonify({
            "error": "version_conflict",
            "message": "This record changed since you opened it. Refresh before saving again.",
            "record": record.to_dict(),
        }), 409
    values, error = validate_record(data)
    if error:
        return jsonify({"error": "invalid_record", "message": error}), 400
    for field, value in values.items():
        setattr(record, field, value)
    record.version += 1
    record.updated_at = utc_now()
    db.session.add(HealthRecordVersion(
        record_id=record.id,
        version=record.version,
        snapshot=snapshot(record),
        changed_by=current_user.full_name,
        change_note=str(data.get("change_note") or "Record updated").strip()[:240],
    ))
    db.session.commit()
    return jsonify({"record": record.to_dict()})


@records_bp.get("/<int:record_id>/history")
@login_required
def record_history(record_id):
    record = owned_record(record_id)
    if not record:
        return jsonify({"error": "not_found", "message": "Health record not found."}), 404
    return jsonify({"versions": [version.to_dict() for version in record.versions]})
