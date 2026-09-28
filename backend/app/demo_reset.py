"""Transactional personal reset, restricted to the explicitly dedicated demo DB.

No filesystem cleanup, schema reset, account deletion or public-catalog mutation.
The service can be called by the authenticated route or a local demo administrator.
"""
from flask import current_app
from sqlalchemy import and_, case, delete, or_, select, update

from .extensions import db
from .models import utc_now


SCOPE = [
    'Your health history, reports, attachments, imported data, measurements and alerts.',
    'Your AI advice and cloud-analysis consent, sharing permissions and access history.',
    'Your appointments, reminders, notifications, phone number and date of birth.',
    'Your added community posts, replies, likes and memberships, excluding original examples.',
    'Your friend relationships and their complete private conversations, including messages from both participants.',
]
PRESERVED = [
    'Your sign-in account, name, email, password and active login sessions.',
    'Your language, community settings and notification preferences.',
    'Original community circles, example members, posts, replies and likes.',
    'Public hospital PDF samples and the care provider directory.',
    'Other accounts\' health data and unrelated community activity.',
]


class DemoResetError(Exception):
    def __init__(self, code, message, status=403):
        self.code, self.message, self.status = code, message, status


def reset_scope():
    return {'available': bool(current_app.config.get('DEMO_DATASET') and current_app.config.get('DEMO_FEATURES_ENABLED')),
            'scope': SCOPE, 'preserved': PRESERVED}


def reset_demo_account(user_id):
    """Commit one current/demo account reset; rollback all work on any error.

    `user_id` is supplied by trusted local code, never accepted from request JSON.
    Related replies/messages are removed with their deleted post/conversation;
    an unrelated owner's data and blocks against this account are not removed.
    Returns per-table deletion counts and the disclosed preservation scope.
    """
    if not reset_scope()['available']:
        raise DemoResetError('demo_reset_unavailable', 'Account reset is available only in the dedicated demo environment.')
    if type(user_id) is not int or user_id <= 0:
        raise DemoResetError('invalid_account', 'A valid demo account is required.', 400)
    tables = db.metadata.tables

    def table(name):
        return tables[name]

    def owned(name, field='user_id'):
        return table(name).c[field] == user_id

    def identifiers(name, condition, column='id'):
        return list(db.session.execute(select(table(name).c[column]).where(condition)).scalars())

    try:
        # Acquire the SQLite writer before collecting IDs, so simultaneous resets
        # cannot each release the same appointment capacity. Other DBs lock this row.
        users = table('users')
        changed = db.session.execute(update(users).where(users.c.id == user_id).values(full_name=users.c.full_name)).rowcount
        if not changed:
            raise DemoResetError('account_not_found', 'Account not found.', 404)
        from .demo_community_catalog import protected_demo_community_ids
        protected = protected_demo_community_ids()
        record_ids = identifiers('health_records', owned('health_records'))
        reading_ids = identifiers('health_measurements', owned('health_measurements'))
        extraction_ids = identifiers('report_extractions', owned('report_extractions'))
        grant_ids = identifiers('share_grants', owned('share_grants'))
        access_ids = identifiers('access_events', owned('access_events'))
        reminder_ids = identifiers('health_reminders', owned('health_reminders'))
        appointment_ids = identifiers('appointments', owned('appointments'))
        notification_ids = identifiers('notifications', owned('notifications'))
        post_ids = identifiers('community_posts', and_(owned('community_posts'), table('community_posts').c.id.notin_(protected['posts'])))
        comment_ids = identifiers('community_comments', or_(table('community_comments').c.post_id.in_(post_ids), and_(owned('community_comments'), table('community_comments').c.id.notin_(protected['comments']))))
        connections = table('community_connections')
        connection_ids = identifiers('community_connections', or_(connections.c.first_id == user_id, connections.c.second_id == user_id))
        message_ids = identifiers('community_messages', table('community_messages').c.connection_id.in_(connection_ids))
        post_report_ids = identifiers('community_reports', or_(owned('community_reports', 'reporter_id'), table('community_reports').c.post_id.in_(post_ids)))
        comment_report_ids = identifiers('community_comment_reports', or_(owned('community_comment_reports', 'reporter_id'), table('community_comment_reports').c.comment_id.in_(comment_ids)))
        message_report_ids = identifiers('community_message_reports', or_(owned('community_message_reports', 'reporter_id'), table('community_message_reports').c.message_id.in_(message_ids)))

        predicates = {name: owned(name) for name in (
            'personal_health_profiles', 'record_import_jobs', 'provider_import_references', 'record_audit_events', 'record_annotations',
            'report_extractions', 'document_indexes', 'measurement_sources', 'profile_fact_sources', 'health_alerts', 'health_measurements',
            'health_records', 'advice_states', 'advice_results', 'share_grants', 'access_events', 'share_scope_access_events',
            'appointments', 'health_reminders', 'notifications', 'security_events')}
        for name in ('record_attachments', 'health_record_versions', 'record_privacy', 'record_lifecycles'):
            predicates[name] = table(name).c.record_id.in_(record_ids)
        for name in ('measurement_contexts', 'measurement_dispositions'):
            predicates[name] = table(name).c.measurement_id.in_(reading_ids)
        predicates['extraction_facts'] = table('extraction_facts').c.extraction_id.in_(extraction_ids)
        for name in ('share_grant_records', 'share_field_settings', 'share_scope_snapshots'):
            predicates[name] = table(name).c.grant_id.in_(grant_ids)
        for name in ('access_reviews', 'simulated_access_events'):
            predicates[name] = table(name).c.event_id.in_(access_ids)
        for name in ('reminder_schedules', 'reminder_cancellations'):
            predicates[name] = table(name).c.reminder_id.in_(reminder_ids)
        predicates['appointment_sharing'] = table('appointment_sharing').c.appointment_id.in_(appointment_ids)
        predicates['notification_resolutions'] = table('notification_resolutions').c.notification_id.in_(notification_ids)
        predicates['community_posts'] = table('community_posts').c.id.in_(post_ids)
        predicates['community_comments'] = table('community_comments').c.id.in_(comment_ids)
        predicates['community_likes'] = or_(table('community_likes').c.post_id.in_(post_ids), and_(owned('community_likes'), table('community_likes').c.id.notin_(protected['likes'])))
        predicates['community_memberships'] = and_(owned('community_memberships'), table('community_memberships').c.id.notin_(protected['memberships']))
        predicates['community_connections'] = connections.c.id.in_(connection_ids)
        predicates['community_messages'] = table('community_messages').c.id.in_(message_ids)
        predicates['community_message_deliveries'] = or_(owned('community_message_deliveries'), table('community_message_deliveries').c.message_id.in_(message_ids))
        predicates['community_blocks'] = owned('community_blocks')
        predicates['community_reports'] = table('community_reports').c.id.in_(post_report_ids)
        predicates['community_comment_reports'] = table('community_comment_reports').c.id.in_(comment_report_ids)
        predicates['community_message_reports'] = table('community_message_reports').c.id.in_(message_report_ids)
        reviews = table('community_report_reviews')
        predicates['community_report_reviews'] = or_(owned('community_report_reviews', 'reporter_id'),
            and_(reviews.c.target_type == 'post', reviews.c.report_id.in_(post_report_ids)),
            and_(reviews.c.target_type == 'comment', reviews.c.report_id.in_(comment_report_ids)),
            and_(reviews.c.target_type == 'message', reviews.c.report_id.in_(message_report_ids)))

        appointments = table('appointments')
        slots = table('appointment_slots')
        slot_counts = {}
        for slot_id in db.session.execute(select(appointments.c.slot_id).where(owned('appointments'), appointments.c.status == 'confirmed')).scalars():
            slot_counts[slot_id] = slot_counts.get(slot_id, 0) + 1
        for slot_id, count in slot_counts.items():
            db.session.execute(update(slots).where(slots.c.id == slot_id).values(booked_count=case((slots.c.booked_count >= count, slots.c.booked_count - count), else_=0)))

        deleted = {}
        # Explicitly selected tables only; the reverse FK order also works with
        # SQLite foreign_keys=ON, without depending on ORM relationship cascades.
        for item in reversed(db.metadata.sorted_tables):
            if item.name in predicates:
                deleted[item.name] = db.session.execute(delete(item).where(predicates[item.name])).rowcount
        profile = table('account_profiles')
        db.session.execute(update(profile).where(owned('account_profiles')).values(phone='', date_of_birth=None, updated_at=utc_now()))
        identity = table('community_identities')
        db.session.execute(update(identity).where(owned('community_identities')).values(notification_since=utc_now()))
        db.session.commit()
        db.session.expire_all()
        return {'reset': True, 'deleted': deleted, 'scope': SCOPE, 'preserved': PRESERVED,
                'message': 'Your personal demo data has been reset. Your sign-in and original shared examples are preserved.'}
    except Exception:
        db.session.rollback()
        raise
