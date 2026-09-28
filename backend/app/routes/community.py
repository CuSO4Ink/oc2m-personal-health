from datetime import timedelta
import secrets
from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import or_, update
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import (
    CommunityCircle,
    CommunityBlock,
    CommunityCommentReport,
    CommunityComment,
    CommunityLike,
    CommunityMembership,
    CommunityPost,
    CommunityProfile,
    CommunityReport,
    Notification,
    utc_now,
)
from ..community_models import CommunityIdentity, CommunityConnection, CommunityMessage, CommunityMessageReport, CommunityReportReview, CommunityMessageDelivery


community_bp = Blueprint("community", __name__)
REPORT_REASONS = {"medical_advice", "unsafe_content", "harassment", "privacy", "spam", "other"}


def body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def identity_for(user_id):
    identity = db.session.get(CommunityIdentity, user_id)
    if not identity:
        identity = CommunityIdentity(user_id=user_id)
        db.session.add(identity)
        db.session.flush()
    return identity


def community_profile_payload(profile):
    identity = identity_for(profile.user_id)
    return {**profile.to_dict(), "nickname": identity.nickname, "discoverable": identity.discoverable,
            "public_id": identity.public_id, "invite_code": identity.invite_code}


def community_name(user_id):
    return identity_for(user_id).nickname


def user_enabled(user_id):
    profile = db.session.get(CommunityProfile, user_id)
    return bool(profile and profile.enabled)


def connection_query(user_id=None):
    user_id = user_id or current_user.id
    return CommunityConnection.query.filter(or_(CommunityConnection.first_id == user_id, CommunityConnection.second_id == user_id))


def peer_id(connection, user_id=None):
    user_id = user_id or current_user.id
    return connection.second_id if connection.first_id == user_id else connection.first_id


def suppress_pair(first_id, second_id):
    """Blocking/removal closes pending interaction and never restores old badges."""
    pair = CommunityConnection.query.filter_by(first_id=min(first_id, second_id), second_id=max(first_id, second_id)).first()
    if pair:
        pair.status = "removed"
        pair.updated_at = utc_now()
        for item in CommunityMessage.query.filter_by(connection_id=pair.id, read_at=None):
            item.read_at = utc_now()
        for item in Notification.query.filter(Notification.user_id.in_([first_id, second_id]), Notification.category == "community"):
            if item.dedupe_key.startswith(f"community-connection-{pair.id}-") or item.dedupe_key.startswith(f"community-message-{pair.id}-"):
                item.archived_at = utc_now()


def profile_for_user():
    profile = db.session.get(CommunityProfile, current_user.id)
    if not profile:
        profile = CommunityProfile(user_id=current_user.id, enabled=False)
        db.session.add(profile)
        db.session.commit()
    return profile


def require_enabled():
    profile = profile_for_user()
    if not profile.enabled:
        return None, (jsonify({
            "error": "community_disabled",
            "message": "Turn on Community before joining circles or interacting with posts.",
        }), 403)
    return profile, None


def active_membership(circle_id, user_id=None):
    membership = CommunityMembership.query.filter_by(
        user_id=user_id or current_user.id,
        circle_id=circle_id,
        left_at=None,
    ).first()
    return membership if membership and membership.circle.active else None


def visible_post(post_id):
    post = CommunityPost.query.filter_by(id=post_id, status="published").first()
    if not post or not post.circle.active or not active_membership(post.circle_id) or post.user_id in blocked_ids():
        return None
    return post


def blocked_ids():
    blocks = CommunityBlock.query.filter(or_(CommunityBlock.user_id == current_user.id, CommunityBlock.target_id == current_user.id)).all()
    return {block.target_id if block.user_id == current_user.id else block.user_id for block in blocks}


def visible_circle_members(circle_id):
    """Use one privacy-filtered set for both directory pages and circle counts."""
    return CommunityIdentity.query.join(CommunityProfile, CommunityProfile.user_id == CommunityIdentity.user_id).join(
        CommunityMembership, CommunityMembership.user_id == CommunityIdentity.user_id).filter(
        CommunityMembership.circle_id == circle_id, CommunityMembership.left_at.is_(None),
        CommunityProfile.enabled.is_(True), CommunityIdentity.user_id.notin_(blocked_ids()),
        or_(CommunityIdentity.discoverable.is_(True), CommunityIdentity.user_id == current_user.id))


def circle_payload(circle):
    return circle.to_dict(current_user.id, visible_member_count=visible_circle_members(circle.id).count())


def serialize_post(post):
    result = post.to_dict(current_user.id)
    blocked = blocked_ids()
    comments = [comment for comment in post.comments if comment.status == "published" and comment.user_id not in blocked]
    result["author_name"] = "Anonymous member" if post.anonymous else community_name(post.user_id)
    # Anonymous content never carries a stable identity or friendship lookup key.
    result["can_connect"] = bool(not post.anonymous and post.user_id != current_user.id and user_enabled(post.user_id) and identity_for(post.user_id).discoverable)
    result["comments"] = [{**comment.to_dict(current_user.id), "author_name": "Anonymous member" if comment.anonymous else community_name(comment.user_id)} for comment in comments]
    result["comment_count"] = len(comments)
    result["like_count"] = sum(like.user_id not in blocked for like in post.likes)
    return result


@community_bp.get("")
@login_required
def overview():
    profile = profile_for_user()
    circles = CommunityCircle.query.filter_by(active=True).order_by(CommunityCircle.name.asc()).all()
    joined_ids = [circle.id for circle in circles if active_membership(circle.id)]
    posts = []
    if profile.enabled and joined_ids:
        posts = CommunityPost.query.filter(
            CommunityPost.circle_id.in_(joined_ids),
            CommunityPost.status == "published",
            CommunityPost.user_id.notin_(blocked_ids()),
        ).order_by(CommunityPost.id.desc()).limit(31).all()
    result = {
        "profile": community_profile_payload(profile),
        "circles": [circle_payload(circle) for circle in circles],
        "posts": [serialize_post(post) for post in posts[:30]],
        "has_more": len(posts) > 30,
        "blocks": [{"id": block.id, "label": "Anonymous member" if block.label == "Anonymous member" else community_name(block.target_id), "created_at": block.created_at.isoformat() + "Z"} for block in CommunityBlock.query.filter_by(user_id=current_user.id).all()],
        "reports": report_history(),
        "safety": {
            "health_records_connected": False,
            "demo_review_available": bool(current_app.config.get("DEMO_FEATURES_ENABLED", True)),
            "message": "Community posts are manually written and never import your health records.",
        },
    }
    db.session.commit()
    return jsonify(result)


@community_bp.patch("/profile")
@login_required
def update_profile():
    data = body()
    if not isinstance(data.get("enabled"), bool):
        return jsonify({"error": "invalid_preference", "message": "Choose whether Community is on or off."}), 400
    profile = profile_for_user()
    identity = identity_for(current_user.id)
    if profile.enabled != data["enabled"]:
        identity.notification_since = utc_now()
        for item in Notification.query.filter_by(user_id=current_user.id, category="community", archived_at=None):
            item.read_at = utc_now()
            item.archived_at = utc_now()
        for connection in connection_query().all():
            for item in CommunityMessage.query.filter_by(connection_id=connection.id, read_at=None).filter(CommunityMessage.sender_id != current_user.id):
                item.read_at = utc_now()
            if connection.status == "pending":
                suppress_pair(connection.first_id, connection.second_id)
            else:
                connection.updated_at = utc_now()
    profile.enabled = data["enabled"]
    if profile.enabled and not profile.joined_at:
        profile.joined_at = utc_now()
    profile.updated_at = utc_now()
    result = community_profile_payload(profile)
    db.session.commit()
    return jsonify({"profile": result})


@community_bp.post("/circles/<int:circle_id>/membership")
@login_required
def join_circle(circle_id):
    _, error = require_enabled()
    if error:
        return error
    circle = CommunityCircle.query.filter_by(id=circle_id, active=True).first()
    if not circle:
        return jsonify({"error": "not_found", "message": "Community circle not found."}), 404
    membership = CommunityMembership.query.filter_by(user_id=current_user.id, circle_id=circle.id).first()
    if membership:
        membership.joined_at = utc_now()
        membership.left_at = None
    else:
        membership = CommunityMembership(user_id=current_user.id, circle_id=circle.id)
        db.session.add(membership)
    db.session.commit()
    return jsonify({"circle": circle_payload(circle)}), 201


@community_bp.get("/circles/<int:circle_id>")
@login_required
def circle_details(circle_id):
    _, error = require_enabled()
    if error:
        return error
    circle = CommunityCircle.query.filter_by(id=circle_id, active=True).first()
    if not circle:
        return jsonify({"message": "Community circle not found."}), 404
    return jsonify({"circle": circle_payload(circle)})


@community_bp.get("/circles/<int:circle_id>/members")
@login_required
def circle_members(circle_id):
    _, error = require_enabled()
    if error:
        return error
    if not active_membership(circle_id):
        return jsonify({"message": "Join this circle to see its member directory."}), 403
    try:
        page = int(request.args.get("page", 1))
        if page < 1:
            raise ValueError()
    except (TypeError, ValueError):
        return jsonify({"message": "Choose a valid member page."}), 400
    # Directory visibility uses the same opt-in as nickname/post discovery.
    # No mapping to anonymous posts, account identifiers, or private profile data.
    query = visible_circle_members(circle_id)
    total = query.count()
    members = query.order_by(CommunityIdentity.nickname, CommunityIdentity.public_id).offset((page - 1) * 20).limit(20).all()
    pairs = {peer_id(item): item for item in connection_query().filter(CommunityConnection.status.in_(["accepted", "pending"])).all()}
    result = []
    for member in members:
        pair = pairs.get(member.user_id)
        state = "self" if member.user_id == current_user.id else "friends" if pair and pair.status == "accepted" else "incoming" if pair and pair.requester_id != current_user.id else "outgoing" if pair else "available"
        result.append({"public_id": member.public_id, "nickname": member.nickname, "connection_status": state,
                       "can_request": state == "available", "connection_id": pair.id if pair else None})
    return jsonify({"members": result, "page": page, "page_size": 20, "total": total,
                    "directory_note": "Members who allow discovery are listed here. Anonymous posts never identify their author."})


@community_bp.delete("/circles/<int:circle_id>/membership")
@login_required
def leave_circle(circle_id):
    _, error = require_enabled()
    if error:
        return error
    membership = active_membership(circle_id)
    if not membership:
        return jsonify({"error": "not_found", "message": "You have not joined this circle."}), 404
    membership.left_at = utc_now()
    db.session.commit()
    circle = db.session.get(CommunityCircle, circle_id)
    return jsonify({"circle": circle_payload(circle)})


@community_bp.get("/posts")
@login_required
def list_posts():
    _, error = require_enabled()
    if error:
        return error
    joined_ids = [membership.circle_id for membership in CommunityMembership.query.filter_by(user_id=current_user.id, left_at=None).all()]
    if not joined_ids:
        return jsonify({"posts": []})
    query = CommunityPost.query.join(CommunityCircle).filter(CommunityPost.circle_id.in_(joined_ids), CommunityPost.status == "published", CommunityCircle.active.is_(True), CommunityPost.user_id.notin_(blocked_ids()))
    if request.args.get("circle_id"):
        try:
            circle_id = int(request.args["circle_id"])
        except (TypeError, ValueError):
            return jsonify({"error": "invalid_circle", "message": "Select a valid circle."}), 400
        query = query.filter(CommunityPost.circle_id == circle_id)
    keyword = str(request.args.get("q") or "").strip()
    if keyword:
        query = query.filter(CommunityPost.body.ilike(f"%{keyword}%"))
    try:
        limit = min(max(int(request.args.get("limit", 30)), 1), 100)
        before = int(request.args.get("before_id", 0))
        if before < 0:
            raise ValueError()
    except (TypeError, ValueError):
        return jsonify({"message": "Use valid post pagination values."}), 400
    if before:
        query = query.filter(CommunityPost.id < before)
    posts = query.order_by(CommunityPost.id.desc()).limit(limit + 1).all()
    payload = {"posts": [serialize_post(post) for post in posts[:limit]], "has_more": len(posts) > limit}
    db.session.commit()
    return jsonify(payload)


@community_bp.post("/posts")
@login_required
def create_post():
    _, error = require_enabled()
    if error:
        return error
    data = body()
    try:
        circle_id = int(data.get("circle_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "invalid_circle", "message": "Select a circle for this post."}), 400
    if not active_membership(circle_id):
        return jsonify({"error": "membership_required", "message": "Join this circle before posting."}), 403
    if not isinstance(data.get("anonymous", True), bool):
        return jsonify({"message": "Select a valid anonymity option."}), 400
    content = str(data.get("body") or "").strip()
    if len(content) < 3 or len(content) > 1200:
        return jsonify({"error": "invalid_post", "message": "Write between 3 and 1,200 characters."}), 400
    if data.get("acknowledged") is not True:
        return jsonify({"error": "guidance_required", "message": "Confirm that this is personal experience, not medical advice."}), 400
    recent = CommunityPost.query.filter(CommunityPost.user_id == current_user.id, CommunityPost.created_at > utc_now() - timedelta(seconds=30)).first()
    if recent:
        return jsonify({"message": "Wait 30 seconds between posts."}), 429
    post = CommunityPost(
        circle_id=circle_id,
        user_id=current_user.id,
        body=content,
        anonymous=bool(data.get("anonymous", True)),
    )
    db.session.add(post)
    db.session.commit()
    return jsonify({"post": serialize_post(post)}), 201


@community_bp.delete("/posts/<int:post_id>")
@login_required
def delete_post(post_id):
    _, error = require_enabled()
    if error:
        return error
    post = CommunityPost.query.filter_by(id=post_id, user_id=current_user.id, status="published").first()
    if not post:
        return jsonify({"error": "not_found", "message": "Post not found."}), 404
    post.status = "deleted"
    db.session.commit()
    return jsonify({"message": "Post deleted."})


@community_bp.post("/posts/<int:post_id>/like")
@login_required
def toggle_like(post_id):
    _, error = require_enabled()
    if error:
        return error
    post = visible_post(post_id)
    if not post:
        return jsonify({"error": "not_found", "message": "Post not found in your circles."}), 404
    like = CommunityLike.query.filter_by(user_id=current_user.id, post_id=post.id).first()
    if like:
        db.session.delete(like)
    else:
        db.session.add(CommunityLike(user_id=current_user.id, post_id=post.id))
    db.session.commit()
    return jsonify({"post": serialize_post(post)})


@community_bp.post("/posts/<int:post_id>/comments")
@login_required
def create_comment(post_id):
    _, error = require_enabled()
    if error:
        return error
    post = visible_post(post_id)
    if not post:
        return jsonify({"error": "not_found", "message": "Post not found in your circles."}), 404
    data = body()
    content = str(data.get("body") or "").strip()
    if not isinstance(data.get("anonymous", True), bool):
        return jsonify({"message": "Select a valid anonymity option."}), 400
    if len(content) < 2 or len(content) > 500:
        return jsonify({"error": "invalid_comment", "message": "Write between 2 and 500 characters."}), 400
    if CommunityComment.query.filter(CommunityComment.user_id == current_user.id, CommunityComment.created_at > utc_now() - timedelta(seconds=10)).first():
        return jsonify({"message": "Wait 10 seconds between comments."}), 429
    comment = CommunityComment(post_id=post.id, user_id=current_user.id, body=content, anonymous=bool(data.get("anonymous", True)))
    db.session.add(comment)
    db.session.commit()
    return jsonify({"post": serialize_post(post)}), 201


@community_bp.post("/posts/<int:post_id>/reports")
@login_required
def report_post(post_id):
    _, error = require_enabled()
    if error:
        return error
    post = visible_post(post_id)
    if not post:
        return jsonify({"error": "not_found", "message": "Post not found in your circles."}), 404
    if post.user_id == current_user.id:
        return jsonify({"error": "invalid_report", "message": "You cannot report your own post."}), 400
    data = body()
    reason = str(data.get("reason") or "").strip()
    if not isinstance(reason, str) or reason not in REPORT_REASONS:
        return jsonify({"error": "invalid_reason", "message": "Select a report reason."}), 400
    if CommunityReport.query.filter_by(reporter_id=current_user.id, post_id=post.id).first():
        return jsonify({"error": "already_reported", "message": "You already reported this post."}), 409
    report = CommunityReport(
        reporter_id=current_user.id,
        post_id=post.id,
        reason=reason,
        details=str(data.get("details") or "").strip()[:500],
    )
    db.session.add(report)
    db.session.commit()
    return jsonify({"report": {"id": report.id, "status": report.status}}), 201


def report_history():
    results = []
    for model, kind in [(CommunityReport, "post"), (CommunityCommentReport, "comment"), (CommunityMessageReport, "message")]:
        for report in model.query.filter_by(reporter_id=current_user.id).all():
            review = CommunityReportReview.query.filter_by(reporter_id=current_user.id, target_type=kind, report_id=report.id).first()
            results.append({"id": f"{kind}-{report.id}", "target_type": kind, "reason": report.reason, "details": report.details,
                            "status": report.status, "created_at": report.created_at.isoformat() + "Z",
                            "simulation_stage": review.stage if review else None,
                            "simulation_updated_at": review.updated_at.isoformat() + "Z" if review else None,
                            "simulation_note": "Demonstration only. No moderator reviewed this report and no account or content was sanctioned." if review else None})
    return sorted(results, key=lambda item: item["created_at"], reverse=True)


@community_bp.delete("/comments/<int:comment_id>")
@login_required
def delete_comment(comment_id):
    _, error = require_enabled()
    if error:
        return error
    comment = CommunityComment.query.filter_by(id=comment_id, user_id=current_user.id, status="published").first()
    if not comment:
        return jsonify({"message": "Comment not found."}), 404
    comment.status = "deleted"
    db.session.commit()
    return jsonify({"message": "Comment deleted."})


@community_bp.post("/comments/<int:comment_id>/reports")
@login_required
def report_comment(comment_id):
    _, error = require_enabled()
    if error:
        return error
    comment = CommunityComment.query.filter_by(id=comment_id, status="published").first()
    if not comment or not visible_post(comment.post_id) or comment.user_id in blocked_ids():
        return jsonify({"message": "Comment not found."}), 404
    if comment.user_id == current_user.id:
        return jsonify({"message": "You cannot report your own comment."}), 400
    reason = body().get("reason")
    if not isinstance(reason, str) or reason not in REPORT_REASONS:
        return jsonify({"message": "Select a report reason."}), 400
    if CommunityCommentReport.query.filter_by(reporter_id=current_user.id, comment_id=comment.id).first():
        return jsonify({"message": "You already reported this comment."}), 409
    report = CommunityCommentReport(reporter_id=current_user.id, comment_id=comment.id, reason=reason, details=str(body().get("details") or "")[:500])
    db.session.add(report); db.session.commit()
    return jsonify({"report": {"id": report.id, "status": report.status}}), 201


@community_bp.post("/blocks")
@login_required
def block_author():
    _, error = require_enabled()
    if error:
        return error
    data = body()
    kind, target_id = data.get("target_type"), data.get("target_id")
    target = None
    if type(target_id) is int and kind == "post":
        target = visible_post(target_id)
    elif type(target_id) is int and kind == "comment":
        target = CommunityComment.query.filter_by(id=target_id, status="published").first()
        if target and (not visible_post(target.post_id) or target.user_id in blocked_ids()):
            target = None
    if not target:
        return jsonify({"message": "Content not found."}), 404
    if target.user_id == current_user.id:
        return jsonify({"message": "You cannot block yourself."}), 400
    block = CommunityBlock(user_id=current_user.id, target_id=target.user_id, label="Anonymous member" if target.anonymous else community_name(target.user_id))
    suppress_pair(current_user.id, target.user_id)
    db.session.add(block); db.session.commit()
    return jsonify({"message": "Member blocked. Their posts and comments are hidden; interactions between your accounts are blocked."}), 201


@community_bp.delete("/blocks/<int:block_id>")
@login_required
def unblock_author(block_id):
    block = CommunityBlock.query.filter_by(id=block_id, user_id=current_user.id).first()
    if not block:
        return jsonify({"message": "Blocked member not found."}), 404
    db.session.delete(block); db.session.commit()
    return jsonify({"message": "Member unblocked."})


@community_bp.patch("/identity")
@login_required
def update_identity():
    _, error = require_enabled()
    if error:
        return error
    data = body()
    nickname = data.get("nickname")
    if not isinstance(nickname, str) or not 2 <= len(nickname.strip()) <= 40 or any(ord(c) < 32 for c in nickname):
        return jsonify({"message": "Choose a community nickname between 2 and 40 characters."}), 400
    if not isinstance(data.get("discoverable", False), bool):
        return jsonify({"message": "Choose whether your nickname is discoverable."}), 400
    identity = identity_for(current_user.id)
    identity.nickname = nickname.strip()
    identity.discoverable = data.get("discoverable", False)
    db.session.commit()
    return jsonify({"profile": community_profile_payload(profile_for_user())})


@community_bp.post("/identity/rotate-invite")
@login_required
def rotate_invite():
    _, error = require_enabled()
    if error:
        return error
    identity = identity_for(current_user.id)
    identity.invite_code = secrets.token_urlsafe(18)
    db.session.commit()
    return jsonify({"invite_code": identity.invite_code})


@community_bp.get("/members")
@login_required
def discover_members():
    _, error = require_enabled()
    if error:
        return error
    keyword = str(request.args.get("q") or "").strip()
    if not 2 <= len(keyword) <= 40:
        return jsonify({"members": []})
    escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    identities = CommunityIdentity.query.join(CommunityProfile, CommunityProfile.user_id == CommunityIdentity.user_id).filter(
        CommunityProfile.enabled.is_(True), CommunityIdentity.discoverable.is_(True),
        CommunityIdentity.user_id != current_user.id, CommunityIdentity.user_id.notin_(blocked_ids()),
        CommunityIdentity.nickname.ilike(f"%{escaped}%", escape="\\"),
    ).order_by(CommunityIdentity.nickname, CommunityIdentity.public_id).limit(20).all()
    return jsonify({"members": [{"public_id": item.public_id, "nickname": item.nickname} for item in identities]})


def connection_payload(connection):
    other = peer_id(connection)
    identity = identity_for(other)
    return {"id": connection.id, "nickname": identity.nickname, "public_id": identity.public_id,
            "status": connection.status, "incoming": connection.requester_id != current_user.id,
            "can_message": connection.status == "accepted" and user_enabled(other),
            "unread": CommunityMessage.query.filter_by(connection_id=connection.id, read_at=None).filter(CommunityMessage.sender_id != current_user.id).count(),
            "updated_at": connection.updated_at.isoformat() + "Z"}


def owned_connection(connection_id, accepted=False):
    connection = connection_query().filter_by(id=connection_id).first()
    if not connection or peer_id(connection) in blocked_ids() or (accepted and connection.status != "accepted"):
        return None
    return connection


@community_bp.get("/connections")
@login_required
def connections():
    _, error = require_enabled()
    if error:
        return error
    excluded = blocked_ids()
    items = [connection_payload(item) for item in connection_query().filter(CommunityConnection.status.in_(["pending", "accepted"])).order_by(CommunityConnection.updated_at.desc()).all() if peer_id(item) not in excluded]
    db.session.commit()
    return jsonify({"friends": [item for item in items if item["status"] == "accepted"],
                    "incoming": [item for item in items if item["status"] == "pending" and item["incoming"]],
                    "outgoing": [item for item in items if item["status"] == "pending" and not item["incoming"]],
                    "unread": sum(item["unread"] for item in items)})


@community_bp.post("/connections")
@login_required
def request_connection():
    _, error = require_enabled()
    if error:
        return error
    data = body()
    identity = None
    if "circle_id" in data:
        circle_id = data.get("circle_id")
        if type(circle_id) is not int or not active_membership(circle_id) or not isinstance(data.get("public_id"), str):
            return jsonify({"message": "This circle member is unavailable."}), 404
        identity = CommunityIdentity.query.filter_by(public_id=data["public_id"], discoverable=True).first()
        if identity and not active_membership(circle_id, identity.user_id):
            identity = None
    elif isinstance(data.get("invite_code"), str):
        identity = CommunityIdentity.query.filter_by(invite_code=data["invite_code"].strip()).first()
    elif isinstance(data.get("public_id"), str):
        identity = CommunityIdentity.query.filter_by(public_id=data["public_id"], discoverable=True).first()
    elif type(data.get("post_id")) is int:
        post = visible_post(data["post_id"])
        if post and not post.anonymous:
            candidate = identity_for(post.user_id)
            if candidate.discoverable:
                identity = candidate
    if not identity or identity.user_id == current_user.id or identity.user_id in blocked_ids() or not user_enabled(identity.user_id):
        return jsonify({"message": "This invitation or member is unavailable."}), 404
    first, second = sorted([current_user.id, identity.user_id])
    connection = CommunityConnection.query.filter_by(first_id=first, second_id=second).first()
    if connection and connection.status in {"pending", "accepted"}:
        return jsonify({"message": "A request or friendship already exists."}), 409
    if connection and connection.status == "rejected" and connection.updated_at > utc_now() - timedelta(days=1):
        return jsonify({"message": "This member declined the request. Wait at least 24 hours before trying again."}), 429
    if connection and connection.status in {"withdrawn", "removed"} and connection.updated_at > utc_now() - timedelta(minutes=5):
        return jsonify({"message": "Wait five minutes before sending another invitation to this member."}), 429
    if connection_query().filter(CommunityConnection.requester_id == current_user.id, CommunityConnection.updated_at > utc_now() - timedelta(minutes=1)).count() >= 10:
        return jsonify({"message": "Too many invitations. Try again in a minute."}), 429
    if not connection:
        connection = CommunityConnection(first_id=first, second_id=second, requester_id=current_user.id)
        db.session.add(connection)
    else:
        changed = db.session.execute(update(CommunityConnection).where(
            CommunityConnection.id == connection.id, CommunityConnection.status == connection.status,
            CommunityConnection.updated_at == connection.updated_at,
        ).values(requester_id=current_user.id, status="pending", accepted_at=None, updated_at=utc_now()), execution_options={"synchronize_session": False})
        if changed.rowcount != 1:
            db.session.rollback()
            return jsonify({"message": "This connection changed. Refresh before trying again."}), 409
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"message": "A request already exists. Refresh your connections."}), 409
    return jsonify({"connection": connection_payload(connection)}), 201


@community_bp.patch("/connections/<int:connection_id>")
@login_required
def update_connection(connection_id):
    _, error = require_enabled()
    if error:
        return error
    connection = owned_connection(connection_id)
    if not connection:
        return jsonify({"message": "Connection not found."}), 404
    action = body().get("action")
    incoming = connection.requester_id != current_user.id
    allowed = connection.status == "pending" and ((incoming and action in {"accept", "reject"}) or (not incoming and action == "withdraw"))
    allowed = allowed or (connection.status == "accepted" and action == "remove")
    if not allowed:
        return jsonify({"message": "This action is not available for this connection."}), 409
    if action == "accept" and not user_enabled(peer_id(connection)):
        return jsonify({"message": "This member is currently unavailable."}), 409
    now = utc_now()
    values = {"status": {"accept": "accepted", "reject": "rejected", "withdraw": "withdrawn", "remove": "removed"}[action], "updated_at": now}
    if action == "accept":
        values["accepted_at"] = now
    changed = db.session.execute(update(CommunityConnection).where(
        CommunityConnection.id == connection.id, CommunityConnection.status == connection.status,
        CommunityConnection.updated_at == connection.updated_at, CommunityConnection.requester_id == connection.requester_id,
    ).values(**values), execution_options={"synchronize_session": False})
    if changed.rowcount != 1:
        db.session.rollback()
        return jsonify({"message": "This request changed. Refresh before trying again."}), 409
    db.session.expire(connection)
    if action == "remove":
        suppress_pair(connection.first_id, connection.second_id)
    db.session.commit()
    return jsonify({"connection": connection_payload(connection)})


def message_payload(message):
    return {"id": message.id, "body": message.body, "is_owner": message.sender_id == current_user.id,
            "created_at": message.created_at.isoformat() + "Z", "read": message.read_at is not None}


@community_bp.get("/connections/<int:connection_id>/messages")
@login_required
def list_messages(connection_id):
    _, error = require_enabled()
    if error:
        return error
    connection = owned_connection(connection_id, accepted=True)
    if not connection:
        return jsonify({"message": "Conversation not found."}), 404
    try:
        limit = min(max(int(request.args.get("limit", 30)), 1), 100)
        before = int(request.args.get("before_id", 0))
        after = int(request.args.get("after_id", 0))
        if before < 0 or after < 0 or (before and after):
            raise ValueError()
    except (TypeError, ValueError):
        return jsonify({"message": "Use valid message pagination values."}), 400
    query = CommunityMessage.query.filter_by(connection_id=connection.id)
    if before:
        query = query.filter(CommunityMessage.id < before)
    if after:
        query = query.filter(CommunityMessage.id > after)
    items = query.order_by(CommunityMessage.id.asc() if after else CommunityMessage.id.desc()).limit(limit + 1).all()
    more = len(items) > limit
    selected = items[:limit]
    if not after:
        selected.reverse()
    return jsonify({"messages": [message_payload(item) for item in selected], "has_more": more,
                    "connection": connection_payload(connection)})


@community_bp.post("/connections/<int:connection_id>/messages")
@login_required
def send_message(connection_id):
    _, error = require_enabled()
    if error:
        return error
    connection = owned_connection(connection_id, accepted=True)
    if not connection or not user_enabled(peer_id(connection)):
        return jsonify({"message": "This conversation is unavailable."}), 404
    content = body().get("body")
    if not isinstance(content, str) or not 1 <= len(content.strip()) <= 2000:
        return jsonify({"message": "Write a message between 1 and 2,000 characters."}), 400
    nonce = body().get("client_nonce")
    if nonce is not None and (not isinstance(nonce, str) or not 8 <= len(nonce) <= 80):
        return jsonify({"message": "Use a valid message delivery key."}), 400
    if nonce:
        delivery = db.session.get(CommunityMessageDelivery, (current_user.id, nonce))
        if delivery:
            saved = db.session.get(CommunityMessage, delivery.message_id)
            if saved.connection_id != connection.id or saved.body != content.strip():
                return jsonify({"message": "This delivery key belongs to a different message."}), 409
            return jsonify({"message": message_payload(saved), "replayed": True})
    if CommunityMessage.query.filter(CommunityMessage.sender_id == current_user.id, CommunityMessage.created_at > utc_now() - timedelta(minutes=1)).count() >= 30:
        return jsonify({"message": "Please slow down. You can send up to 30 messages per minute."}), 429
    changed = db.session.execute(update(CommunityConnection).where(
        CommunityConnection.id == connection.id, CommunityConnection.status == "accepted",
        CommunityConnection.updated_at == connection.updated_at,
    ).values(updated_at=utc_now()), execution_options={"synchronize_session": False})
    if changed.rowcount != 1:
        db.session.rollback()
        return jsonify({"message": "The conversation changed. Refresh and retry your message."}), 409
    item = CommunityMessage(connection_id=connection.id, sender_id=current_user.id, body=content.strip())
    db.session.add(item)
    db.session.flush()
    if nonce:
        db.session.add(CommunityMessageDelivery(user_id=current_user.id, client_nonce=nonce, message_id=item.id))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        saved_delivery = db.session.get(CommunityMessageDelivery, (current_user.id, nonce)) if nonce else None
        if saved_delivery:
            saved = db.session.get(CommunityMessage, saved_delivery.message_id)
            if saved.connection_id == connection.id and saved.body == content.strip():
                return jsonify({"message": message_payload(saved), "replayed": True})
        return jsonify({"message": "The message could not be saved. Refresh and try again."}), 409
    return jsonify({"message": message_payload(item)}), 201


@community_bp.patch("/connections/<int:connection_id>/messages/read")
@login_required
def read_messages(connection_id):
    _, error = require_enabled()
    if error:
        return error
    connection = owned_connection(connection_id, accepted=True)
    if not connection:
        return jsonify({"message": "Conversation not found."}), 404
    through = body().get("through_id")
    if type(through) is not int or not CommunityMessage.query.filter_by(id=through, connection_id=connection.id).first():
        return jsonify({"message": "Choose a message from this conversation."}), 400
    for item in CommunityMessage.query.filter(CommunityMessage.connection_id == connection.id, CommunityMessage.sender_id != current_user.id, CommunityMessage.id <= through, CommunityMessage.read_at.is_(None)):
        item.read_at = utc_now()
    for item in Notification.query.filter_by(user_id=current_user.id, category="community", read_at=None):
        prefix = f"community-message-{connection.id}-"
        if item.dedupe_key.startswith(prefix) and int(item.dedupe_key[len(prefix):]) <= through:
            item.read_at = utc_now()
    db.session.commit()
    return jsonify({"message": "Conversation marked read."})


@community_bp.post("/connections/<int:connection_id>/block")
@login_required
def block_connection(connection_id):
    _, error = require_enabled()
    if error:
        return error
    connection = owned_connection(connection_id)
    if not connection:
        return jsonify({"message": "Connection not found."}), 404
    other = peer_id(connection)
    db.session.add(CommunityBlock(user_id=current_user.id, target_id=other, label=community_name(other)))
    suppress_pair(current_user.id, other)
    db.session.commit()
    return jsonify({"message": "Member blocked. Messages and friendship requests are stopped."}), 201


@community_bp.post("/messages/<int:message_id>/reports")
@login_required
def report_message(message_id):
    _, error = require_enabled()
    if error:
        return error
    item = db.session.get(CommunityMessage, message_id)
    # Keep reporting received history available after removing/blocking the sender.
    if not item or not connection_query().filter_by(id=item.connection_id).first() or item.sender_id == current_user.id:
        return jsonify({"message": "Received message not found."}), 404
    reason = body().get("reason")
    if not isinstance(reason, str) or reason not in REPORT_REASONS:
        return jsonify({"message": "Select a report reason."}), 400
    if CommunityMessageReport.query.filter_by(reporter_id=current_user.id, message_id=item.id).first():
        return jsonify({"message": "You already reported this message."}), 409
    report = CommunityMessageReport(reporter_id=current_user.id, message_id=item.id, reason=reason, details=str(body().get("details") or "")[:500])
    db.session.add(report)
    db.session.commit()
    return jsonify({"report": {"id": f"message-{report.id}", "status": report.status}}), 201


@community_bp.post("/reports/<string:report_key>/simulate-review")
@login_required
def simulate_review(report_key):
    _, error = require_enabled()
    if error:
        return error
    if not current_app.config.get("DEMO_FEATURES_ENABLED", True):
        return jsonify({"error": "not_connected", "message": "Demonstration review is disabled. Your report remains saved; a real moderation service is not connected."}), 503
    try:
        kind, identifier = report_key.split("-", 1)
        model = {"post": CommunityReport, "comment": CommunityCommentReport, "message": CommunityMessageReport}[kind]
        report = model.query.filter_by(id=int(identifier), reporter_id=current_user.id).first()
    except (KeyError, ValueError):
        report = None
    if not report:
        return jsonify({"message": "Report not found."}), 404
    review = CommunityReportReview.query.filter_by(reporter_id=current_user.id, target_type=kind, report_id=report.id).first()
    if not review:
        review = CommunityReportReview(reporter_id=current_user.id, target_type=kind, report_id=report.id)
        db.session.add(review)
    elif review.stage == "in_review":
        review.stage = "closed_demo"
        review.updated_at = utc_now()
    db.session.commit()
    return jsonify({"reports": report_history(), "message": "Simulated review only; no moderation action was taken."})
