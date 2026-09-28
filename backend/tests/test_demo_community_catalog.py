from datetime import timedelta

import pytest

from app import create_app
from app.community_models import CommunityConnection, CommunityIdentity
from app.demo_community_catalog import COMMUNITY_CATALOG, LEGACY_POSTS, ensure_demo_community_catalog, protected_demo_community_ids
from app.extensions import db
from app.models import (AccountProfile, CommunityCircle, CommunityComment, CommunityLike,
                        CommunityMembership, CommunityPost, CommunityProfile, User, utc_now)


@pytest.fixture
def demo():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "DEMO_DATASET": "catalog-regression"})
    with app.app_context():
        users = []
        for name in ("alex", "jamie"):
            user = User(full_name=name.title(), email=f"{name}@example.test", role="patient")
            user.set_password("Patient123")
            db.session.add(user)
            db.session.flush()
            db.session.add(CommunityProfile(user_id=user.id, enabled=True))
            db.session.add(CommunityIdentity(user_id=user.id, nickname=f"Custom {name}", discoverable=False, invite_code=f"PERSONAL-{name}"))
            db.session.add(AccountProfile(user_id=user.id, phone="+1 555 0109"))
            users.append(user.id)
        db.session.commit()
        yield app, users


def test_helper_only_runs_for_known_demo_accounts(demo):
    app, (alex, jamie) = demo
    app.config["DEMO_DATASET"] = ""
    assert not any(ensure_demo_community_catalog().values())
    assert CommunityCircle.query.count() == CommunityPost.query.count() == 0
    app.config["DEMO_DATASET"] = "catalog-regression"
    db.session.get(User, jamie).email = "different@example.test"
    db.session.commit()
    assert not any(ensure_demo_community_catalog().values())
    assert CommunityCircle.query.count() == 0


@pytest.mark.parametrize("legacy_names", [("日常小习惯", "一起记录健康"), ("Small healthy habits", "Keeping track together")])
def test_legacy_upgrade_keeps_ids_personal_posts_friendships_and_community_choices(demo, legacy_names):
    _, (alex, jamie) = demo
    old = []
    for name in legacy_names:
        circle = CommunityCircle(name=name, topic="Old topic", description="Old description")
        db.session.add(circle)
        db.session.flush()
        old.append(circle)
    left_at = utc_now() - timedelta(days=1)
    db.session.add(CommunityMembership(circle_id=old[0].id, user_id=alex, left_at=left_at))
    db.session.add(CommunityMembership(circle_id=old[0].id, user_id=jamie))
    old[1].active = False
    db.session.add(CommunityMembership(circle_id=old[1].id, user_id=jamie, left_at=left_at))
    db.session.get(CommunityProfile, jamie).enabled = False
    personal = CommunityPost(circle_id=old[0].id, user_id=alex, body="My own discussion must remain unchanged.", anonymous=True)
    db.session.add(personal)
    db.session.add(CommunityConnection(first_id=min(alex, jamie), second_id=max(alex, jamie), requester_id=alex, status="accepted", accepted_at=utc_now()))
    db.session.commit()
    identifiers = [item.id for item in old]
    result = ensure_demo_community_catalog()
    assert result == {"circles": 1, "memberships": 10, "posts": 12, "comments": 12, "likes": 12}
    assert [CommunityCircle.query.filter_by(name=sample["name"]).one().id for sample in COMMUNITY_CATALOG[:2]] == identifiers
    assert CommunityCircle.query.count() == 3
    assert db.session.get(CommunityCircle, identifiers[1]).active is False
    assert CommunityMembership.query.filter_by(user_id=alex, circle_id=identifiers[0]).one().left_at == left_at
    assert CommunityMembership.query.filter_by(user_id=alex, circle_id=identifiers[1]).first() is None
    assert CommunityMembership.query.filter_by(user_id=jamie).count() == 2
    assert db.session.get(CommunityProfile, jamie).enabled is False
    assert db.session.get(CommunityIdentity, alex).nickname == "Custom alex"
    assert db.session.get(CommunityIdentity, alex).discoverable is False
    assert db.session.get(AccountProfile, alex).phone == "+1 555 0109"
    assert CommunityConnection.query.one().status == "accepted"
    assert db.session.get(CommunityPost, personal.id).body == "My own discussion must remain unchanged."
    assert not any(ensure_demo_community_catalog().values())
    assert CommunityPost.query.count() == 13


def test_restart_is_idempotent_and_does_not_restore_deleted_content_or_removed_likes(demo):
    _, (alex, jamie) = demo
    assert ensure_demo_community_catalog() == {"circles": 3, "memberships": 15, "posts": 12, "comments": 12, "likes": 12}
    post = CommunityPost.query.order_by(CommunityPost.id).first()
    comment = CommunityComment.query.filter_by(post_id=post.id).one()
    original_time = post.created_at
    post.status, comment.status = "deleted", "deleted"
    CommunityLike.query.filter_by(post_id=post.id).delete()
    circle_id = post.circle_id
    membership = CommunityMembership.query.filter_by(circle_id=circle_id, user_id=alex).one()
    membership.left_at = utc_now()
    db.session.get(CommunityProfile, jamie).enabled = False
    db.session.commit()
    assert not any(ensure_demo_community_catalog().values())
    assert CommunityPost.query.count() == 12 and CommunityComment.query.count() == 12
    assert post.status == comment.status == "deleted"
    assert post.created_at == original_time
    assert CommunityLike.query.filter_by(post_id=post.id).count() == 0
    assert membership.left_at is not None
    assert db.session.get(CommunityProfile, jamie).enabled is False


def test_protected_ids_keep_only_original_fixtures_and_not_user_copies(demo):
    ensure_demo_community_catalog()
    original = protected_demo_community_ids()
    assert {key: len(value) for key, value in original.items()} == {
        'circles': 3, 'posts': 12, 'comments': 12, 'likes': 12, 'memberships': 15}
    assert len({post.user_id for post in CommunityPost.query.all()}) == 5
    post = CommunityPost.query.order_by(CommunityPost.id).first()
    comment = CommunityComment.query.filter_by(post_id=post.id).first()
    copied_post = CommunityPost(circle_id=post.circle_id, user_id=post.user_id, body=post.body, anonymous=post.anonymous)
    copied_comment = CommunityComment(post_id=post.id, user_id=comment.user_id, body=comment.body, anonymous=False)
    extra_comment = CommunityComment(post_id=post.id, user_id=comment.user_id, body='This is my own test reply.', anonymous=False)
    other_user = User.query.filter_by(email='casey@example.test').one()
    extra_like = CommunityLike(post_id=post.id, user_id=other_user.id)
    starter = User.query.filter_by(email='start@example.test').one()
    test_membership = CommunityMembership(circle_id=post.circle_id, user_id=starter.id)
    db.session.add_all([copied_post, copied_comment, extra_comment, extra_like, test_membership])
    db.session.commit()
    protected = protected_demo_community_ids()
    assert protected == original
    assert copied_post.id not in protected['posts']
    assert copied_comment.id not in protected['comments'] and extra_comment.id not in protected['comments']
    assert extra_like.id not in protected['likes'] and test_membership.id not in protected['memberships']


def test_legacy_translation_preserves_fourteen_fixtures_without_translating_or_protecting_copies(demo):
    _, (_, jamie) = demo
    originals, copies = [], []
    original_time = utc_now() - timedelta(days=30)
    for position, sample in enumerate(COMMUNITY_CATALOG[:2]):
        circle = CommunityCircle(name=sample['aliases'][0], topic='Legacy seed', description='Original demo circle')
        db.session.add(circle)
        db.session.flush()
        original = CommunityPost(circle_id=circle.id, user_id=jamie, body=LEGACY_POSTS[1],
            anonymous=False, status='deleted' if position else 'published', created_at=original_time)
        db.session.add(original)
        db.session.flush()
        originals.append((original.id, original.status))
        for body in LEGACY_POSTS:
            copied = CommunityPost(circle_id=circle.id, user_id=jamie, body=body, anonymous=False)
            db.session.add(copied)
            copies.append((copied, body))
    db.session.commit()
    assert protected_demo_community_ids()['posts'] == {post_id for post_id, _ in originals}

    assert ensure_demo_community_catalog()['posts'] == 12
    protected = protected_demo_community_ids()['posts']
    assert len(protected) == 14
    for post_id, original_status in originals:
        post = db.session.get(CommunityPost, post_id)
        assert post.id in protected
        assert post.body == LEGACY_POSTS[0]
        assert post.user_id == jamie and post.status == original_status
        assert post.created_at == original_time
    for copied, original_body in copies:
        assert copied.id not in protected
        assert copied.body == original_body

    assert not any(ensure_demo_community_catalog().values())
    assert protected_demo_community_ids()['posts'] == protected
    assert all(copied.body == original_body for copied, original_body in copies)
