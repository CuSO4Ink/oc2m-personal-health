"""Explicit report fields awaiting human confirmation; no disease inference."""
from copy import deepcopy
from datetime import datetime
import hashlib
import re
from uuid import uuid4

from sqlalchemy import update

from .extensions import db
from .models import utc_now
from .record_models import PersonalHealthProfile, profile_payload
from .record_audit import append_audit
from .report_parser import parse_candidates


class ExtractionFacts(db.Model):
    __tablename__ = 'extraction_facts'
    extraction_id = db.Column(db.Integer, db.ForeignKey('report_extractions.id'), primary_key=True)
    facts = db.Column(db.JSON, nullable=False, default=list)


class ProfileFactSource(db.Model):
    __tablename__ = 'profile_fact_sources'
    __table_args__ = (db.UniqueConstraint('user_id', 'source_digest', 'candidate_key', name='uq_confirmed_profile_fact'),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    profile_item_id = db.Column(db.String(80), nullable=False, index=True)
    section = db.Column(db.String(30), nullable=False)
    extraction_id = db.Column(db.Integer, db.ForeignKey('report_extractions.id'), nullable=False)
    record_id = db.Column(db.Integer, db.ForeignKey('health_records.id'), nullable=False)
    attachment_id = db.Column(db.Integer)
    source_digest = db.Column(db.String(64), nullable=False)
    candidate_key = db.Column(db.String(24), nullable=False)
    evidence = db.Column(db.Text, nullable=False)
    page = db.Column(db.Integer)
    original_values = db.Column(db.JSON, nullable=False)
    confirmed_values = db.Column(db.JSON, nullable=False)
    linked_existing = db.Column(db.Boolean, nullable=False, default=False)
    confirmed_at = db.Column(db.DateTime, nullable=False, default=utc_now)


FIELDS = {
    'past_history': {'name', 'detail', 'start_date', 'end_date'},
    'family_history': {'name', 'detail', 'relationship'},
    'medications': {'name', 'detail', 'dose', 'frequency', 'start_date', 'end_date'},
    'allergies': {'name', 'detail', 'severity'},
}
FACT_LABEL = re.compile(r'^\s*(?P<label>confirmed diagnosis|final diagnosis|discharge diagnosis|diagnosis|current medication|medication|confirmed allergy|allergy|allergies|family history|确诊|出院诊断|诊断|当前用药|用药|药物|过敏|过敏史|家族史)\s*[:：]\s*(?P<value>.+)$', re.I)
UNCERTAIN = re.compile(r'\b(?:no|not|none|negative|denies|denied|suspected|suspect|possible|possibly|probable|consider|considered|exclude|excluded|rule\s*out|ruled\s*out|screening|nkda)\b|否认|排除|待排|疑似|考虑|可能|未见|没有|无|待查|筛查|\?', re.I)
FIELD_ALIASES = {'dose': 'dose', '剂量': 'dose', 'frequency': 'frequency', '频次': 'frequency', 'reaction': 'detail', '反应': 'detail', 'detail': 'detail', '备注': 'detail', 'severity': 'severity', '严重程度': 'severity', 'relationship': 'relationship', '亲属': 'relationship', 'date': 'start_date', '日期': 'start_date', 'start_date': 'start_date', 'end_date': 'end_date'}
TIME_LABEL = re.compile(r'^\s*(?:measurement\s+(?:date(?:\s*(?:/|and)\s*time)?|time)|collection\s+(?:date|time)|测量时间|采样时间|检测时间)\s*[:：]\s*(\d{4}[-/]\d{2}[-/]\d{2}[ T]\d{2}:\d{2}(?::\d{2})?(?:\s*(?:Z|[+-]\d{2}:\d{2}))?)\s*$', re.I)
PAGE = re.compile(r'^\[Page (\d+)\]$')


def report_candidates(text):
    """Preserve source lines/pages; prefill only explicitly labelled complete times."""
    page, line_pages, page_times, all_times = None, {}, {}, set()
    for number, line in enumerate(text.splitlines(), 1):
        marker = PAGE.match(line.strip())
        if marker:
            page = int(marker.group(1))
        line_pages[number] = page
        match = TIME_LABEL.match(line)
        if match:
            raw = match.group(1).replace('/', '-').replace(' ', 'T', 1).replace(' ', '')
            try:
                value = datetime.fromisoformat(raw.replace('Z', '+00:00')).isoformat()
                page_times.setdefault(page, set()).add(value); all_times.add(value)
            except ValueError:
                pass
    readings = parse_candidates(text)
    for item in readings:
        item['page'] = line_pages.get(item['line_number'])
        times = page_times.get(item['page'], set()) or (all_times if len(all_times) == 1 else set())
        item['measured_at'] = next(iter(times)) if len(times) == 1 else None
        item['time_source'] = 'explicit_report_measurement_time' if item['measured_at'] else None
    facts, seen = [], set()
    for number, line in enumerate(text.splitlines(), 1):
        match = FACT_LABEL.match(line)
        if not match or UNCERTAIN.search(match.group('value')):
            continue
        label = match.group('label').casefold()
        section = 'family_history' if label in {'family history', '家族史'} else 'medications' if label in {'current medication', 'medication', '当前用药', '用药', '药物'} else 'allergies' if label in {'confirmed allergy', 'allergy', 'allergies', '过敏', '过敏史'} else 'past_history'
        fragments = re.split(r'\s*[|；;]\s*', match.group('value'))
        name = fragments[0].strip()
        if not name or len(name) > 160:
            continue
        values = {field: '' for field in FIELDS[section]}; values['name'] = name
        for fragment in fragments[1:]:
            pieces = re.split(r'[:：]', fragment, maxsplit=1)
            field = FIELD_ALIASES.get(pieces[0].strip().casefold())
            if len(pieces) == 2 and field in FIELDS[section]:
                values[field] = pieces[1].strip()[:1000]
        key = hashlib.sha256(f'{section}|{line.strip().casefold()}'.encode()).hexdigest()[:24]
        if key in seen:
            continue
        seen.add(key)
        facts.append({'id': key, 'section': section, **values, 'sensitive': False, 'evidence': line.strip(), 'line_number': number, 'page': line_pages.get(number)})
        if len(facts) >= 30:
            break
    return readings, facts


def fact_sources_payload(user_id):
    profile = profile_payload(user_id)
    entries = {item['id']: item for section in profile['sections'].values() for item in section['items']}
    result = []
    for source in ProfileFactSource.query.filter_by(user_id=user_id).order_by(ProfileFactSource.confirmed_at.desc()).all():
        current = entries.get(source.profile_item_id)
        result.append({'id': source.id, 'profile_item_id': source.profile_item_id, 'section': source.section,
            'record_id': source.record_id, 'attachment_id': source.attachment_id, 'extraction_id': source.extraction_id,
            'evidence': source.evidence, 'page': source.page, 'original_values': source.original_values,
            'confirmed_values': source.confirmed_values, 'linked_existing': source.linked_existing,
            'current_item_matches': bool(current and all(current.get(key, '') == value for key, value in source.confirmed_values.items() if key != 'id')),
            'current_item_exists': current is not None, 'confirmed_at': source.confirmed_at.isoformat() + 'Z',
            'record_path': f'/records/{source.record_id}', 'review_path': f'/records/{source.record_id}?extraction={source.extraction_id}'})
    return {'sources': result, 'profile_revision': profile['revision']}


def validate_fact(selection, candidate):
    section = candidate['section']
    if selection.get('section', section) != section:
        raise ValueError('请在原文中校对类别，不能把一种事实直接改成另一种。')
    result = {key: str(selection.get(key, candidate.get(key, '')) or '').strip() for key in FIELDS[section]}
    if not result['name'] or len(result['name']) > 160 or any(len(value) > 1000 for value in result.values()):
        raise ValueError('事实需要 1–160 字的名称，其他字段最多 1,000 字。')
    if UNCERTAIN.search(result['name']):
        raise ValueError('否定、待排或不确定的描述不能作为已确认健康史导入；可保留在档案备注中。')
    for key in ('start_date', 'end_date'):
        if result.get(key):
            try:
                result[key] = datetime.strptime(result[key], '%Y-%m-%d').date().isoformat()
            except ValueError:
                raise ValueError('健康史日期请使用 YYYY-MM-DD。') from None
    if result.get('start_date') and result.get('end_date') and result['end_date'] < result['start_date']:
        raise ValueError('结束日期不能早于开始日期。')
    if section == 'family_history' and not result['relationship']:
        raise ValueError('请确认家族史中的亲属关系。')
    if not isinstance(selection.get('sensitive', False), bool):
        raise ValueError('请选择有效的敏感信息标记。')
    result['sensitive'] = selection.get('sensitive', False)
    return result


class ProfileConflict(Exception):
    pass


def confirm_profile_facts(draft, facts, expected_revision):
    """Append or link exact names with an atomic revision claim; never replace user entries."""
    previous = deepcopy(profile_payload(draft.user_id))
    if type(expected_revision) is not int or expected_revision != previous['revision']:
        raise ProfileConflict()
    sections = deepcopy(previous['sections'])
    additions, duplicates = [], []
    for candidate, values in facts:
        existing_source = ProfileFactSource.query.filter_by(user_id=draft.user_id, source_digest=draft.source_digest, candidate_key=candidate['id']).first()
        if existing_source:
            duplicates.append({'candidate_id': candidate['id'], 'profile_item_id': existing_source.profile_item_id}); continue
        section = sections[candidate['section']]
        matching = next((item for item in section['items'] if item['name'].strip().casefold() == values['name'].strip().casefold()
            and (candidate['section'] != 'family_history' or item.get('relationship', '').casefold() == values.get('relationship', '').casefold())), None)
        if matching:
            saved = deepcopy(matching)
            duplicates.append({'candidate_id': candidate['id'], 'profile_item_id': saved['id'], 'reason': 'same_name_preserved'})
        else:
            if len(section['items']) >= 100:
                raise ValueError('该健康史类别已达到 100 条，请整理后再导入。')
            saved = {**values, 'id': str(uuid4())}
            section['items'].append(saved); section['status'] = 'recorded'
        source = ProfileFactSource(user_id=draft.user_id, profile_item_id=saved['id'], section=candidate['section'],
            extraction_id=draft.id, record_id=draft.record_id, attachment_id=draft.attachment_id, source_digest=draft.source_digest,
            candidate_key=candidate['id'], evidence=candidate['evidence'], page=candidate.get('page'),
            original_values={field: candidate.get(field, '') for field in FIELDS[candidate['section']]},
            confirmed_values=saved, linked_existing=bool(matching))
        db.session.add(source); additions.append(source)
    if sections != previous['sections']:
        if expected_revision == 0:
            db.session.add(PersonalHealthProfile(user_id=draft.user_id, revision=1, sections=sections)); db.session.flush()
        else:
            claimed = db.session.execute(update(PersonalHealthProfile).where(PersonalHealthProfile.user_id == draft.user_id,
                PersonalHealthProfile.revision == expected_revision).values(sections=sections, revision=expected_revision + 1, updated_at=utc_now()), execution_options={'synchronize_session': False})
            if not claimed.rowcount:
                raise ProfileConflict()
        append_audit(draft.user_id, 'health_profile_updated', details={'revision': expected_revision + 1, 'snapshot': sections,
            'previous_revision': previous['revision'], 'previous_snapshot': previous['sections'], 'previous_updated_at': previous['updated_at'], 'extraction_id': draft.id})
        db.session.expire_all()
    return additions, duplicates
