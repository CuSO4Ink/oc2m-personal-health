import hashlib
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import HealthMeasurement, HealthRecord, RecordAttachment, utc_now
from ..insight_models import MeasurementContext
from ..record_models import profile_payload, record_privacy_payload
from ..record_audit import append_audit
from ..extraction_models import MeasurementSource, ReportExtraction
from ..report_parser import MAX_PAGES, MAX_TEXT, OCR_TIMEOUT, extract_attachment, ocr_capabilities
from ..health_facts import (ExtractionFacts, ProfileFactSource, ProfileConflict, confirm_profile_facts,
                          fact_sources_payload, report_candidates, validate_fact)
from .insights import alert_for, serialize_measurement, validate_measurement

extraction_bp = Blueprint("extraction", __name__)


def body():
    value = request.get_json(silent=True)
    return value if isinstance(value, dict) else {}


def owned_record(record_id):
    return HealthRecord.query.filter_by(id=record_id, user_id=current_user.id).first() if type(record_id) is int else None


def owned_extraction(extraction_id):
    return ReportExtraction.query.filter_by(id=extraction_id, user_id=current_user.id).first()


def extraction_payload(draft):
    result = draft.to_dict()
    imported = {source.candidate_key: source for source in MeasurementSource.query.filter_by(
        user_id=current_user.id, source_digest=draft.source_digest).all()}
    result["candidates"] = [{**candidate, "existing_measurement_id": imported[candidate["id"]].measurement_id if candidate["id"] in imported else None,
        "confirmed_values": imported[candidate["id"]].confirmed_values if candidate["id"] in imported else None} for candidate in draft.candidates]
    result["text_edited"] = draft.original_text != draft.reviewed_text
    result["record_path"] = f"/records/{draft.record_id}"
    result["attachment_available"] = bool(draft.attachment_id and RecordAttachment.query.filter_by(id=draft.attachment_id, record_id=draft.record_id).first())
    fact_row = db.session.get(ExtractionFacts, draft.id)
    sources = {source.candidate_key: source for source in ProfileFactSource.query.filter_by(user_id=draft.user_id, source_digest=draft.source_digest).all()}
    result['facts'] = [{**item, 'existing_profile_item_id': sources[item['id']].profile_item_id if item['id'] in sources else None,
        'confirmed_values': sources[item['id']].confirmed_values if item['id'] in sources else None} for item in (fact_row.facts if fact_row else [])]
    result['fact_count'] = len(result['facts'])
    result['profile_revision'] = profile_payload(draft.user_id)['revision']
    return result


def pending_candidate_count(draft):
    return pending_candidate_counts(draft)['total']


def pending_candidate_counts(draft):
    facts = db.session.get(ExtractionFacts, draft.id)
    saved_readings = {item.candidate_key for item in MeasurementSource.query.filter_by(user_id=draft.user_id, source_digest=draft.source_digest).all()}
    saved_facts = {item.candidate_key for item in ProfileFactSource.query.filter_by(user_id=draft.user_id, source_digest=draft.source_digest).all()}
    measurements = sum(item['id'] not in saved_readings for item in draft.candidates)
    fact_count = sum(item['id'] not in saved_facts for item in (facts.facts if facts else []))
    return {'measurement_count': measurements, 'fact_count': fact_count, 'total': measurements + fact_count}


def create_draft_from_document(record, attachment, index):
    """Called by indexing/sync: flush only; caller commits. Never confirms health data."""
    field = (lambda key, default=None: index.get(key, default)) if isinstance(index, dict) else (lambda key, default=None: getattr(index, key, default))
    pages = field('pages', []) or []
    full_text = '\n\n'.join(f"[Page {page['page']}]\n{page.get('text', '')}" for page in pages if page.get('text', '').strip())
    text = full_text[:MAX_TEXT]
    digest = hashlib.sha256(attachment.data).hexdigest()
    existing = ReportExtraction.query.filter_by(user_id=record.user_id, attachment_id=attachment.id, source_digest=digest, original_text=text).order_by(ReportExtraction.id.desc()).first()
    if existing:
        return existing
    readings, facts = report_candidates(text)
    warnings = list(field('warnings', []) or [])
    if len(full_text) > MAX_TEXT:
        warnings.append('核对候选仅扫描前 60,000 字符，全文检索仍覆盖索引页面；后续内容可另行校对。')
    if field('status') != 'complete':
        warnings.append('文档尚未完整识别；这里只包含当前可读内容，可稍后重试文档处理。')
    draft = ReportExtraction(user_id=record.user_id, record_id=record.id, attachment_id=attachment.id,
        filename=attachment.filename, source_digest=digest, source_kind='attachment', method='document_index',
        original_text=text, reviewed_text=text, candidates=readings, warnings=warnings,
        page_info={'total_pages': field('total_pages'), 'processed_pages': [page['page'] for page in pages if page.get('text', '').strip()], 'status': field('status')})
    db.session.add(draft); db.session.flush()
    db.session.add(ExtractionFacts(extraction_id=draft.id, facts=facts)); db.session.flush()
    append_audit(record.user_id, 'report_extraction_prepared', record.id, {'extraction_id': draft.id, 'attachment_id': attachment.id,
        'method': 'document_index', 'candidate_count': len(readings), 'fact_count': len(facts)}, source='system', actor_name='系统提取')
    return draft


@extraction_bp.get('/profile-provenance')
@login_required
def profile_provenance():
    return jsonify(fact_sources_payload(current_user.id))


@extraction_bp.get("/capabilities")
@login_required
def capabilities():
    return jsonify({"pdf_text": True, "ocr": ocr_capabilities(), "max_pages": MAX_PAGES,
        "ocr_timeout_seconds": OCR_TIMEOUT, "max_characters": MAX_TEXT,
        "message": "Extraction runs locally. No report or image is sent to an external OCR service."})


@extraction_bp.post("")
@login_required
def start_extraction():
    data = body()
    record = owned_record(data.get("record_id"))
    if not record:
        return jsonify({"message": "Health record not found."}), 404
    if record_privacy_payload(record.id)["archived"]:
        return jsonify({"message": "Restore this record before extracting new readings."}), 409
    attachment = None
    if data.get("attachment_id") is not None:
        attachment = RecordAttachment.query.filter_by(id=data["attachment_id"], record_id=record.id).first() if type(data["attachment_id"]) is int else None
        if not attachment:
            return jsonify({"message": "Attachment not found on this record."}), 404
    language = data.get("language", "auto")
    if not isinstance(language, str) or language not in {"auto", *ocr_capabilities().get("languages", [])}:
        return jsonify({"message": "Choose an installed OCR language."}), 400
    supplied_text = data.get("text")
    if supplied_text is not None and (not isinstance(supplied_text, str) or len(supplied_text) > MAX_TEXT):
        return jsonify({"message": f"Paste text up to {MAX_TEXT:,} characters."}), 400
    source_bytes = attachment.data if attachment else record.content.encode("utf-8")
    if supplied_text is not None:
        result = {"text": supplied_text, "method": "manual_text", "warnings": ["Text was supplied manually; compare it with the original report."], "processed_pages": [], "total_pages": None}
        if not attachment:
            source_bytes = supplied_text.encode("utf-8")
    elif attachment:
        result = extract_attachment(source_bytes, attachment.content_type, language)
    else:
        result = {"text": record.content[:MAX_TEXT], "method": "record_text", "warnings": [], "processed_pages": [], "total_pages": None}
    text = result["text"]
    candidates, facts = report_candidates(text)
    warnings = result["warnings"][:]
    if not candidates and not facts:
        warnings.append("No supported labelled reading with an explicit unit was found. Correct or paste the report text below, then find candidates again. Unlabelled numbers and reference ranges are not imported.")
    if len(candidates) == 50:
        warnings.append("At most 50 candidates are shown. Review later text separately if the report contains more readings.")
    draft = ReportExtraction(user_id=current_user.id, record_id=record.id,
        attachment_id=attachment.id if attachment else None, filename=attachment.filename if attachment else "Record text",
        source_digest=hashlib.sha256(source_bytes if attachment else str(record.id).encode() + b":" + source_bytes).hexdigest(), source_kind="attachment" if attachment else "record_text",
        method=result["method"], original_text=text, reviewed_text=text, candidates=candidates, warnings=warnings,
        page_info={"total_pages": result["total_pages"], "processed_pages": result["processed_pages"]})
    db.session.add(draft)
    db.session.flush()
    db.session.add(ExtractionFacts(extraction_id=draft.id, facts=facts))
    append_audit(current_user.id, "report_extraction_prepared", record.id, {"extraction_id": draft.id,
        "attachment_id": draft.attachment_id, "method": draft.method, "candidate_count": len(candidates)})
    db.session.commit()
    return jsonify({"extraction": extraction_payload(draft), "message": "Candidates only. No health measurements have been saved."}), 201


@extraction_bp.get("/<int:extraction_id>")
@login_required
def get_extraction(extraction_id):
    draft = owned_extraction(extraction_id)
    if not draft:
        return jsonify({"message": "Extraction not found."}), 404
    return jsonify({"extraction": extraction_payload(draft)})


@extraction_bp.patch("/<int:extraction_id>/review")
@login_required
def review_text(extraction_id):
    draft = owned_extraction(extraction_id)
    if not draft:
        return jsonify({"message": "Extraction not found."}), 404
    data = body()
    text = data.get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
        return jsonify({"message": f"Enter report text up to {MAX_TEXT:,} characters."}), 400
    if type(data.get("revision")) is not int:
        return jsonify({"message": "Include the extraction revision."}), 400
    candidates, facts = report_candidates(text)
    changed = db.session.execute(update(ReportExtraction).where(ReportExtraction.id == draft.id,
        ReportExtraction.revision == data["revision"], ReportExtraction.confirmed_at.is_(None)).values(
        reviewed_text=text, candidates=candidates, revision=ReportExtraction.revision + 1),
        execution_options={"synchronize_session": False})
    if not changed.rowcount:
        db.session.rollback()
        return jsonify({"message": "This draft changed or was already confirmed. Reopen it before continuing."}), 409
    fact_row = db.session.get(ExtractionFacts, draft.id)
    if fact_row:
        fact_row.facts = facts
    else:
        db.session.add(ExtractionFacts(extraction_id=draft.id, facts=facts))
    append_audit(current_user.id, "extraction_text_reviewed", draft.record_id, {"extraction_id": draft.id})
    db.session.commit()
    db.session.refresh(draft)
    return jsonify({"extraction": extraction_payload(draft)})


def validate_selection(selection, candidate, record):
    if not isinstance(selection, dict) or selection.get("metric_type", candidate["metric_type"]) != candidate["metric_type"]:
        return None, "Use the candidate's metric type; correct the report text to change labels."
    unit = selection.get("unit")
    supported = {"blood_pressure": {"mmHg"}, "blood_glucose": {"mmol/L", "mg/dL"}, "heart_rate": {"bpm"}}
    if not isinstance(unit, str) or unit not in supported[candidate["metric_type"]]:
        return None, "Confirm a supported measurement unit."
    try:
        value = float(selection.get("value"))
    except (ValueError, TypeError):
        return None, "Confirm a numeric value."
    if type(selection.get("value")) is bool:
        return None, "Confirm a numeric value."
    if unit == "mg/dL":
        value = round(value / 18.0, 2)
    measured_at = selection.get("measured_at")
    try:
        parsed = datetime.fromisoformat(str(measured_at).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError()
        if parsed.astimezone(timezone.utc).year < 1900:
            raise ValueError()
    except (ValueError, TypeError, OverflowError):
        return None, "Confirm the measurement date and time, including its time zone."
    context = selection.get("context", "")
    if not isinstance(context, str):
        return None, "Choose a valid measurement context."
    if candidate["metric_type"] == "blood_glucose" and context not in {"fasting", "after_meal", "random"}:
        return None, "Confirm whether glucose was fasting, after a meal or random."
    special = selection.get("special_context", "general")
    if not isinstance(special, str) or special not in {"general", "pregnancy", "individual_target", "unknown"}:
        return None, "Choose a valid reference context."
    values, error = validate_measurement({"metric_type": candidate["metric_type"], "value": value,
        "secondary_value": selection.get("secondary_value"), "context": context, "measured_at": measured_at,
        "source_name": f"Confirmed report: {record.title}"[:120],
        "notes": f"Confirmed from record #{record.id}. Original candidate: {candidate['evidence']}"[:300]})
    return (values, special) if not error else (None, error)


@extraction_bp.post("/<int:extraction_id>/confirm")
@login_required
def confirm_candidates(extraction_id):
    draft = owned_extraction(extraction_id)
    if not draft:
        return jsonify({"message": "Extraction not found."}), 404
    record = owned_record(draft.record_id)
    if not record or record_privacy_payload(record.id)["archived"]:
        return jsonify({"message": "Restore the source record before importing readings."}), 409
    data = body()
    selections = data.get("selections", [])
    fact_selections = data.get('facts', [])
    if data.get("acknowledged") is not True:
        return jsonify({"message": "Confirm that you checked the selected readings against the source report."}), 400
    if type(data.get("revision")) is not int or not isinstance(selections, list) or not isinstance(fact_selections, list) or len(selections) > 50 or len(fact_selections) > 30 or not selections + fact_selections:
        return jsonify({"message": "请选择至少一条待确认内容；每批最多 50 条指标和 30 条健康史，并附带草稿版本。"}), 400
    candidates = {item["id"]: item for item in draft.candidates}
    validated, seen = [], set()
    for selection in selections:
        key = selection.get("candidate_id") if isinstance(selection, dict) else None
        if not isinstance(key, str) or key not in candidates or key in seen:
            return jsonify({"message": "Select each available candidate at most once."}), 400
        seen.add(key)
        values, special_or_error = validate_selection(selection, candidates[key], record)
        if values is None:
            return jsonify({"message": special_or_error}), 400
        validated.append((key, candidates[key], values, special_or_error, selection))
    fact_row = db.session.get(ExtractionFacts, draft.id)
    fact_candidates = {item['id']: item for item in (fact_row.facts if fact_row else [])}
    validated_facts, fact_seen = [], set()
    for selection in fact_selections:
        key = selection.get('candidate_id') if isinstance(selection, dict) else None
        if not isinstance(key, str) or key not in fact_candidates or key in fact_seen:
            return jsonify({'message': '请选择有效且不重复的健康史候选。'}), 400
        fact_seen.add(key)
        try:
            validated_facts.append((fact_candidates[key], validate_fact(selection, fact_candidates[key])))
        except ValueError as error:
            return jsonify({'message': str(error)}), 400
    changed = db.session.execute(update(ReportExtraction).where(ReportExtraction.id == draft.id,
        ReportExtraction.revision == data["revision"], ReportExtraction.confirmed_at.is_(None)).values(
        confirmed_at=utc_now(), revision=ReportExtraction.revision + 1), execution_options={"synchronize_session": False})
    if not changed.rowcount:
        db.session.rollback()
        return jsonify({"message": "This draft changed or was already confirmed. No duplicate readings were saved."}), 409
    imported, duplicates = [], []
    try:
        fact_imported, fact_duplicates = confirm_profile_facts(draft, validated_facts, data.get('profile_revision')) if validated_facts else ([], [])
        for key, candidate, values, special, selection in validated:
            existing = MeasurementSource.query.filter_by(user_id=current_user.id, source_digest=draft.source_digest, candidate_key=key).first()
            if existing:
                duplicates.append({"candidate_id": key, "measurement_id": existing.measurement_id})
                continue
            measurement = HealthMeasurement(user_id=current_user.id, **values)
            db.session.add(measurement)
            db.session.flush()
            db.session.add(MeasurementContext(measurement_id=measurement.id, special_context=special))
            source = MeasurementSource(measurement_id=measurement.id, user_id=current_user.id,
                extraction_id=draft.id, record_id=record.id, attachment_id=draft.attachment_id, filename=draft.filename,
                source_digest=draft.source_digest, candidate_key=key, evidence=candidate["evidence"][:1000],
                original_values={field: candidate.get(field) for field in ("metric_type", "value", "secondary_value", "unit", "context", "measured_at", "page", "line_number")},
                confirmed_values={"value": selection["value"], "secondary_value": selection.get("secondary_value"),
                    "unit": selection["unit"], "measured_at": values["measured_at"].isoformat() + "Z", "context": values["context"],
                    "stored_value": values["value"], "stored_unit": values["unit"], "special_context": special})
            db.session.add(source)
            alert = alert_for(measurement, special)
            if alert:
                db.session.add(alert)
            imported.append(measurement)
            append_audit(current_user.id, "report_reading_confirmed", record.id, {"extraction_id": draft.id,
                "measurement_id": measurement.id, "attachment_id": draft.attachment_id})
        db.session.commit()
    except ProfileConflict:
        db.session.rollback()
        return jsonify({'error': 'profile_conflict', 'message': '个人健康信息已在其他页面更新。本次指标和健康史均未写入，请核对最新信息后重试。', 'profile': profile_payload(current_user.id)}), 409
    except ValueError as error:
        db.session.rollback()
        return jsonify({'message': str(error)}), 400
    except IntegrityError:
        db.session.rollback()
        return jsonify({"message": "These readings were imported by another request. Reload the draft to view existing readings."}), 409
    db.session.refresh(draft)
    return jsonify({"extraction": extraction_payload(draft), "measurements": [serialize_measurement(item) for item in imported],
        'profile': profile_payload(current_user.id), 'profile_facts': [{'profile_item_id': item.profile_item_id, 'section': item.section, 'linked_existing': item.linked_existing} for item in fact_imported],
        'fact_duplicates': fact_duplicates, "duplicates": duplicates,
        "message": f"已确认 {len(imported)} 条指标、{sum(not item.linked_existing for item in fact_imported)} 条健康史；跳过或关联 {len(duplicates) + len(fact_duplicates)} 条已有内容。"})
