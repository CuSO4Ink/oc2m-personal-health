from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import or_

from ..extensions import db
from ..models import (
    CommunityCircle,
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
    return CommunityMembership.query.filter_by(
        user_id=user_id or current_user.id,
        circle_id=circle_id,
        left_at=None,
    ).first()


def visible_post(post_id):
    post = CommunityPost.query.filter_by(id=post_id, status="published").first()
    if not post or not active_membership(post.circle_id):
        return None
    return post


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
        ).order_by(CommunityPost.created_at.desc()).limit(50).all()
    return jsonify({
        "profile": profile.to_dict(),
        "circles": [circle.to_dict(current_user.id) for circle in circles],
        "posts": [post.to_dict(current_user.id) for post in posts],
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
    query = CommunityPost.query.filter(CommunityPost.circle_id.in_(joined_ids), CommunityPost.status == "published")
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
    return jsonify({"posts": [post.to_dict(current_user.id) for post in posts]})


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
    content = str(data.get("body") or "").strip()
    if len(content) < 3 or len(content) > 1200:
        return jsonify({"error": "invalid_post", "message": "Write between 3 and 1,200 characters."}), 400
    if data.get("acknowledged") is not True:
        return jsonify({"error": "guidance_required", "message": "Confirm that this is personal experience, not medical advice."}), 400
    post = CommunityPost(
        circle_id=circle_id,
        user_id=current_user.id,
        body=content,
        anonymous=bool(data.get("anonymous", True)),
    )
    db.session.add(post)
    db.session.commit()
    return jsonify({"post": post.to_dict(current_user.id)}), 201


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
    return jsonify({"post": post.to_dict(current_user.id)})


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
    if len(content) < 2 or len(content) > 500:
        return jsonify({"error": "invalid_comment", "message": "Write between 2 and 500 characters."}), 400
    comment = CommunityComment(post_id=post.id, user_id=current_user.id, body=content, anonymous=bool(data.get("anonymous", True)))
    db.session.add(comment)
    db.session.commit()
    return jsonify({"post": post.to_dict(current_user.id)}), 201


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
    if reason not in REPORT_REASONS:
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
