from datetime import timedelta
from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import or_

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
    utc_now,
)


community_bp = Blueprint("community", __name__)
REPORT_REASONS = {"medical_advice", "unsafe_content", "harassment", "privacy", "spam", "other"}


def body():
    return request.get_json(silent=True) or {}


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


def serialize_post(post):
    result = post.to_dict(current_user.id)
    blocked = blocked_ids()
    comments = [comment for comment in post.comments if comment.status == "published" and comment.user_id not in blocked]
    result["comments"] = [comment.to_dict(current_user.id) for comment in comments]
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
        ).order_by(CommunityPost.created_at.desc()).limit(50).all()
    return jsonify({
        "profile": profile.to_dict(),
        "circles": [circle.to_dict(current_user.id) for circle in circles],
        "posts": [serialize_post(post) for post in posts],
        "blocks": [{"id": block.id, "label": block.label, "created_at": block.created_at.isoformat() + "Z"} for block in CommunityBlock.query.filter_by(user_id=current_user.id).all()],
        "reports": report_history(),
        "safety": {
            "health_records_connected": False,
            "message": "Community posts are manually written and never import your health records.",
        },
    })


@community_bp.patch("/profile")
@login_required
def update_profile():
    data = body()
    if not isinstance(data.get("enabled"), bool):
        return jsonify({"error": "invalid_preference", "message": "Choose whether Community is on or off."}), 400
    profile = profile_for_user()
    profile.enabled = data["enabled"]
    if profile.enabled and not profile.joined_at:
        profile.joined_at = utc_now()
    profile.updated_at = utc_now()
    db.session.commit()
    return jsonify({"profile": profile.to_dict()})


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
    return jsonify({"circle": circle.to_dict(current_user.id)}), 201


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
    return jsonify({"circle": circle.to_dict(current_user.id)})


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
    posts = query.order_by(CommunityPost.created_at.desc()).limit(50).all()
    return jsonify({"posts": [serialize_post(post) for post in posts]})


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
    for model, kind in [(CommunityReport, "post"), (CommunityCommentReport, "comment")]:
        for report in model.query.filter_by(reporter_id=current_user.id).all():
            results.append({"id": f"{kind}-{report.id}", "target_type": kind, "reason": report.reason, "details": report.details,
                            "status": report.status, "created_at": report.created_at.isoformat() + "Z"})
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
    block = CommunityBlock(user_id=current_user.id, target_id=target.user_id, label="Anonymous member" if target.anonymous else target.user.full_name)
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
