"""Fixed sharing content, with live privacy revocation on every access."""
from copy import deepcopy
from datetime import date
import hashlib
import json

from .extensions import db
from .models import HealthRecord, HealthMeasurement, RecordAttachment
from .record_models import PROFILE_SECTIONS, profile_payload, record_privacy_payload
from .insight_models import MeasurementDisposition
from .extraction_models import measurement_source_payload
from .sample_catalog import with_record_display

FIELDS = {"title", "record_type", "record_date", "source_name", "condition", "content"}
SECTION_LABELS = {"past_history": "既往病史", "family_history": "家族病史", "medications": "用药情况", "allergies": "过敏情况"}
PROFILE_FIELDS = {"id", "name", "detail", "start_date", "end_date", "relationship", "dose", "frequency", "severity"}


def digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def integer_ids(data, key, maximum=200):
    values = data.get(key, [])
    if not isinstance(values, list) or len(values) > maximum or any(type(value) is not int or value < 1 for value in values):
        raise ValueError(f"{key}: 请提供最多 {maximum} 个有效对象编号。")
    return list(dict.fromkeys(values))


def measurement_visible(measurement, owner_id):
    if not measurement or measurement.user_id != owner_id or db.session.get(MeasurementDisposition, measurement.id):
        return False
    source = measurement_source_payload(measurement.id)
    if source:
        privacy = record_privacy_payload(source["record_id"])
        # A hidden source field could contain the same value; never bypass its lock via a reading.
        if privacy["sensitive"] or privacy["archived"] or privacy["sensitive_fields"]:
            return False
    return True


def build_scope(owner_id, data, records, fields):
    scope = {"version": 1, "records": [], "attachments": [], "profile": [], "measurements": [], "measurement_period": None}
    for record in records:
        privacy = record_privacy_payload(record.id)
        if privacy["sensitive"] or privacy["archived"]:
            raise ValueError("敏感或已归档的档案不能共享。")
        values = record.to_dict()
        selected = {field: values[field] for field in fields if field not in privacy["sensitive_fields"]}
        if fields and not selected:
            raise ValueError("这份档案的所选字段已全部隐藏。")
        if selected:
            scope["records"].append({"id": record.id, "version": record.version, "values": selected})
    attachment_ids = integer_ids(data, "attachment_ids")
    if attachment_ids and data.get("acknowledge_original_files") is not True:
        raise ValueError("请确认：原始 PDF/图片按完整原件共享，文字字段隐藏不会对原文件打码。")
    attachments = RecordAttachment.query.join(HealthRecord).filter(HealthRecord.user_id == owner_id, RecordAttachment.id.in_(attachment_ids)).all() if attachment_ids else []
    if len(attachments) != len(attachment_ids):
        raise ValueError("所选原文件不属于当前账号或已经删除。")
    for attachment in sorted(attachments, key=lambda item: item.id):
        privacy = record_privacy_payload(attachment.record_id)
        if privacy["sensitive"] or privacy["archived"] or privacy["sensitive_fields"]:
            raise ValueError("原文件所属档案存在敏感或隐藏字段，不能共享完整原件；请只共享允许的文字摘要。")
        scope["attachments"].append({"id": attachment.id, "record_id": attachment.record_id,
            "filename": attachment.filename, "content_type": attachment.content_type, "size": attachment.size,
            "sha256": hashlib.sha256(attachment.data).hexdigest()})
    profile = profile_payload(owner_id)
    sections = data.get("profile_sections", [])
    items = data.get("profile_items", [])
    if not isinstance(sections, list) or any(section not in PROFILE_SECTIONS for section in sections) or not isinstance(items, list) or len(items) > 400:
        raise ValueError("请选择有效的健康史类别或条目。")
    selected_items = {section: set() for section in PROFILE_SECTIONS}
    for selection in items:
        if not isinstance(selection, dict) or selection.get("section") not in PROFILE_SECTIONS or not isinstance(selection.get("item_id"), str):
            raise ValueError("请选择有效的健康史条目。")
        selected_items[selection["section"]].add(selection["item_id"])
    for key in PROFILE_SECTIONS:
        section = profile["sections"][key]
        available = {item.get("id", f"legacy-{index}"): {**item, "id": item.get("id", f"legacy-{index}")} for index, item in enumerate(section["items"])}
        if any(identifier not in available or available[identifier].get("sensitive") for identifier in selected_items[key]):
            raise ValueError("健康史条目已删除或被标记为敏感，请重新选择。")
        ids = selected_items[key] | ({identifier for identifier, item in available.items() if not item.get("sensitive")} if key in sections else set())
        if ids or (key in sections and section["status"] != "recorded"):
            scope["profile"].append({"section": key, "label": SECTION_LABELS[key], "revision": profile["revision"],
                "status": section["status"], "items": [{k: v for k, v in available[identifier].items() if k in PROFILE_FIELDS} for identifier in sorted(ids)]})
    measurement_ids = integer_ids(data, "measurement_ids", 500)
    if measurement_ids:
        period = data.get("measurement_period")
        try:
            first = date.fromisoformat(period["from"])
            last = date.fromisoformat(period["to"])
            if last < first:
                raise ValueError()
        except (TypeError, KeyError, ValueError):
            raise ValueError("请选择要共享的指标日期范围。") from None
        measurements = HealthMeasurement.query.filter(HealthMeasurement.user_id == owner_id, HealthMeasurement.id.in_(measurement_ids)).order_by(HealthMeasurement.measured_at, HealthMeasurement.id).all()
        if len(measurements) != len(measurement_ids) or any(not first <= item.measured_at.date() <= last or not measurement_visible(item, owner_id) for item in measurements):
            raise ValueError("所选指标超出日期范围、已作废/更正，或其来源已设为私密。")
        scope["measurement_period"] = {"from": first.isoformat(), "to": last.isoformat(), "timezone": "UTC"}
        # The source report text, OCR evidence and personal notes are not part of a reading permission.
        allowed = {"id", "metric_type", "value", "secondary_value", "unit", "context", "measured_at", "source_type", "source_name"}
        scope["measurements"] = [{key: value for key, value in item.to_dict().items() if key in allowed} for item in measurements]
    if not any(scope[key] for key in ("records", "attachments", "profile", "measurements")):
        raise ValueError("请至少选择一项可共享的资料。")
    return scope


def visible_scope(scope, owner_id):
    visible = {"records": [], "attachments": [], "profile": [], "measurements": [], "excluded_count": 0,
               "measurement_period": scope.get("measurement_period"), "scope_mode": "fixed_snapshot"}
    for saved in scope["records"]:
        record = db.session.get(HealthRecord, saved["id"])
        privacy = record_privacy_payload(saved["id"])
        if not record or record.user_id != owner_id or privacy["sensitive"] or privacy["archived"]:
            visible["excluded_count"] += 1
            continue
        values = {key: value for key, value in saved["values"].items() if key not in privacy["sensitive_fields"]}
        if values:
            visible["records"].append(with_record_display(record, values))
        else:
            visible["excluded_count"] += 1
    for saved in scope["attachments"]:
        attachment, _ = permitted_attachment(saved, owner_id)
        if attachment:
            visible["attachments"].append({key: value for key, value in saved.items() if key != "sha256"})
        else:
            visible["excluded_count"] += 1
    current = profile_payload(owner_id)
    for saved in scope["profile"]:
        section = current["sections"][saved["section"]]
        allowed = {item.get("id", f"legacy-{index}") for index, item in enumerate(section["items"]) if not item.get("sensitive")}
        items = [deepcopy(item) for item in saved["items"] if item["id"] in allowed]
        if items or (not saved["items"] and section["status"] == saved["status"]):
            visible["profile"].append({**saved, "items": items})
        else:
            visible["excluded_count"] += 1
    for saved in scope["measurements"]:
        if measurement_visible(db.session.get(HealthMeasurement, saved["id"]), owner_id):
            visible["measurements"].append(deepcopy(saved))
        else:
            visible["excluded_count"] += 1
    visible["attachments_included"] = bool(visible["attachments"])
    return visible


def permitted_attachment(saved, owner_id):
    attachment = db.session.get(RecordAttachment, saved["id"])
    if not attachment or attachment.record_id != saved["record_id"] or attachment.record.user_id != owner_id:
        return None, "file_unavailable"
    privacy = record_privacy_payload(attachment.record_id)
    if privacy["sensitive"] or privacy["archived"] or privacy["sensitive_fields"]:
        return None, "scope_private_or_archived"
    if hashlib.sha256(attachment.data).hexdigest() != saved["sha256"]:
        return None, "file_version_changed"
    return attachment, "allowed"


def scope_objects(scope):
    objects = []
    for key, label in [("records", "档案摘要"), ("attachments", "原始文件"), ("profile", "健康史类别"), ("measurements", "指标读数")]:
        if scope.get(key):
            objects.append({"kind": key, "count": len(scope[key]), "label": f"{len(scope[key])} 项{label}"})
    return objects
