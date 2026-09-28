"""Add fictional discussions to the dedicated demo without resetting its users."""
from datetime import timedelta

from flask import current_app

from .extensions import db
from .models import (CommunityCircle, CommunityComment, CommunityLike,
                     CommunityMembership, CommunityPost, CommunityProfile, User, utc_now)


GUIDANCE = "Share personal experiences, respect privacy, and leave diagnosis and treatment decisions to qualified professionals. Join to meet members who choose to be discoverable."
COMMUNITY_CATALOG = [
    {"name": "Daily routines", "aliases": ["日常小习惯", "Small healthy habits"], "topic": "Everyday wellbeing",
     "authors": ["jamie", "alex", "riley", "alex"], "responders": ["morgan", "casey", "jamie", "morgan"],
     "description": "Share the small routines that make daily life easier, celebrate progress, and encourage each other.", "entries": [
        ("jamie", False, "I started keeping my walking shoes by the door. It makes it easier to choose a short walk when I have a little energy. Some days I only reach the end of the street, and I am learning to count that too.", "I like the idea of making the first step easier. I have been leaving a water bottle beside my bag."),
        ("alex", False, "This week I tried writing down one thing that went well at the end of each day. Yesterday it was simply getting outside for a few minutes. What small win would you like to share?", "Mine was preparing tomorrow's breakfast before bed. It felt good to have one less decision in the morning."),
        ("jamie", True, "My energy has been unpredictable lately. I used to feel guilty when plans changed, but I am getting better at telling friends when I need a quieter day. It helps when people listen without trying to fix everything.", "Thank you for sharing that. Having permission to change plans has helped me too."),
        ("alex", False, "A follow-up to my small-wins post: I kept the notes for a whole week. Looking back, I can see good moments I would otherwise have forgotten. I am going to keep the list short so it stays manageable.", "That sounds like a kind way to look back on the week. Short and manageable works best for me too."),
     ]},
    {"name": "Keeping track of health", "aliases": ["一起记录健康", "Keeping track together"], "topic": "Records and appointments",
     "authors": ["casey", "morgan", "jamie", "riley"], "responders": ["alex", "riley", "casey", "jamie"],
     "description": "Exchange practical experiences of organising reports, preparing questions, and keeping personal records.", "entries": [
        ("jamie", False, "Before my last appointment I put the report date in each file name and made a short list of questions. I spent less time looking for documents and more time asking what I needed to understand.", "I use dates in file names too. I also keep the original report so I can check a detail later."),
        ("alex", False, "I noticed I had saved the same report twice under different names. Now I check the report date and hospital before adding another copy. Does anyone else have a simple way to keep their collection tidy?", "I add a short topic to the name, like annual review, and check for an existing copy first."),
        ("jamie", True, "I sometimes forget what I wanted to ask when an appointment starts. Writing three questions in advance helped me feel more prepared. I leave space beside each one for the answer.", "I do something similar and ask whether I can take notes. It helps me remember the conversation afterwards."),
        ("alex", False, "After trying the question-list idea, I added a note about what I did not understand in my report. I asked my clinician to explain those words instead of guessing from a search result. That made the next steps clearer for me.", "It is reassuring to hear that asking for plain language helped. I am adding that to my next question list."),
     ]},
    {"name": "Living with long-term conditions", "aliases": [], "topic": "Peer support",
     "authors": ["riley", "morgan", "casey", "jamie"], "responders": ["jamie", "alex", "morgan", "casey"],
     "description": "A space to discuss the day-to-day experience of ongoing care and feeling supported, without giving treatment instructions.", "entries": [
        ("jamie", False, "I have been learning how to explain my appointments to friends without making every conversation about health. A simple 'I have a check-up this week and might be tired afterwards' has been enough for me.", "That wording feels practical. I appreciate when friends ask what kind of support would help."),
        ("alex", True, "Waiting for a follow-up can leave me distracted. I wrote down my questions, then made plans for something ordinary that I enjoy. It did not answer everything, but it gave the day some structure.", "I can relate to the waiting. A familiar activity and someone to talk to can make the day feel less lonely."),
        ("jamie", False, "One thing I appreciate in this circle is being able to share a difficult day without receiving a new treatment plan. Sometimes I just want someone to say they understand. Thank you to everyone who listens.", "Listening matters. I try to ask whether a friend wants company, practical help, or simply space to talk."),
        ("alex", False, "A small update after my follow-up: I have a clearer list of questions for next time and know which documents to bring. I am keeping the plan from my care team in one place so I can refer back to it.", "Glad the visit helped you feel more prepared. Keeping the questions and reports together sounds useful."),
     ]},
]

LEGACY_POSTS = (
    "I keep a short list of questions with my reports so I can find them before appointments. What helps you stay organised?",
    "我会把想问医生的问题和报告放在一起，就诊前比较容易找到。大家平时怎么整理自己的资料？",
)
SOCIAL_NAMES = ("alex", "jamie", "morgan", "riley", "casey")


def _demo_users():
    return {name: User.query.filter_by(email=f"{name}@example.test", role="patient").first() for name in SOCIAL_NAMES}


def _matching_post(circle, sample, position, users):
    legacy, anonymous, body, _ = sample["entries"][position]
    author_ids = [users[name].id for name in {legacy, sample["authors"][position]} if users.get(name)]
    return CommunityPost.query.filter(CommunityPost.circle_id == circle.id,
        CommunityPost.user_id.in_(author_ids), CommunityPost.body == body,
        CommunityPost.anonymous.is_(anonymous)).order_by(CommunityPost.id).first()


def _matching_reply(post, sample, position, users):
    legacy_author, _, _, reply = sample["entries"][position]
    legacy_responder = "alex" if legacy_author == "jamie" else "jamie"
    author_ids = [users[name].id for name in {legacy_responder, sample["responders"][position]} if users.get(name)]
    return CommunityComment.query.filter(CommunityComment.post_id == post.id,
        CommunityComment.user_id.in_(author_ids), CommunityComment.body == reply,
        CommunityComment.anonymous.is_(False)).order_by(CommunityComment.id).first()


def _matching_legacy_post(circle, users):
    # The old seed created one short Jamie post in each of its two circles.
    # Match both languages together so later copies cannot become fixtures.
    return CommunityPost.query.filter(CommunityPost.circle_id == circle.id,
        CommunityPost.user_id == users["jamie"].id,
        CommunityPost.body.in_(LEGACY_POSTS),
        CommunityPost.anonymous.is_(False)).order_by(CommunityPost.id).first()


def protected_demo_community_ids():
    """Read-only exact fixture IDs for reset; never protect arbitrary account content."""
    protected = {key: set() for key in ("circles", "posts", "comments", "likes", "memberships")}
    if not current_app.config.get("DEMO_DATASET"):
        return protected
    users = _demo_users()
    if not users.get("alex") or not users.get("jamie"):
        return protected
    for sample in COMMUNITY_CATALOG:
        circles = CommunityCircle.query.filter(CommunityCircle.name.in_([sample["name"], *sample["aliases"]])).all()
        for circle in circles:
            protected["circles"].add(circle.id)
            ids = [user.id for user in users.values() if user]
            protected["memberships"].update(item.id for item in CommunityMembership.query.filter(
                CommunityMembership.circle_id == circle.id, CommunityMembership.user_id.in_(ids)).all())
            for position in range(len(sample["entries"])):
                post = _matching_post(circle, sample, position, users)
                if not post:
                    continue
                protected["posts"].add(post.id)
                reply = _matching_reply(post, sample, position, users)
                if reply:
                    protected["comments"].add(reply.id)
                legacy_author = sample["entries"][position][0]
                legacy_responder = "alex" if legacy_author == "jamie" else "jamie"
                # The canonical responder has priority after a catalog upgrade.
                for name in dict.fromkeys([sample["responders"][position], legacy_responder]):
                    if users.get(name):
                        like = CommunityLike.query.filter_by(post_id=post.id, user_id=users[name].id).first()
                        if like:
                            protected["likes"].add(like.id)
                            break
            if sample in COMMUNITY_CATALOG[:2]:
                post = _matching_legacy_post(circle, users)
                if post:
                    protected["posts"].add(post.id)
    return protected


def ensure_demo_community_catalog():
    """Idempotently extend known synthetic accounts; never reopen their community."""
    added = {"circles": 0, "memberships": 0, "posts": 0, "comments": 0, "likes": 0}
    if not current_app.config.get("DEMO_DATASET"):
        return added
    users = _demo_users()
    if not users.get("alex") or not users.get("jamie"):
        return added
    from .demo_data import ensure_demo_accounts
    created_accounts = ensure_demo_accounts()
    users = _demo_users()
    now = utc_now().replace(second=0, microsecond=0)
    circles = []
    for sample in COMMUNITY_CATALOG:
        circle = CommunityCircle.query.filter_by(name=sample["name"]).first()
        if not circle and sample["aliases"]:
            circle = CommunityCircle.query.filter(CommunityCircle.name.in_(sample["aliases"])).order_by(CommunityCircle.id).first()
        new_circle = circle is None
        if new_circle:
            circle = CommunityCircle(name=sample["name"], topic=sample["topic"], description=sample["description"], guidance=GUIDANCE)
            db.session.add(circle)
            db.session.flush()
            added["circles"] += 1
        elif circle.name in sample["aliases"]:
            # Reuse the legacy ID, retaining all posts, memberships and activity.
            circle.name, circle.topic = sample["name"], sample["topic"]
            circle.description, circle.guidance = sample["description"], GUIDANCE
        if sample in COMMUNITY_CATALOG[:2]:
            legacy_post = _matching_legacy_post(circle, users)
            if legacy_post and legacy_post.body == LEGACY_POSTS[1]:
                legacy_post.body = LEGACY_POSTS[0]
        # Only a newly created circle/person gets initial memberships. Existing
        # absent or left memberships and disabled profiles remain user choices.
        for user in users.values():
            if not new_circle and user.id not in created_accounts:
                continue
            profile = CommunityProfile.query.filter_by(user_id=user.id).first()
            if profile and profile.enabled and not CommunityMembership.query.filter_by(user_id=user.id, circle_id=circle.id).first():
                db.session.add(CommunityMembership(user_id=user.id, circle_id=circle.id))
                added["memberships"] += 1
        circles.append((circle, sample))
    for position in range(4):
        for circle_number, (circle, sample) in enumerate(circles):
            legacy_author, anonymous, body, reply = sample["entries"][position]
            author_key = sample["authors"][position]
            author = users[author_key]
            responder = users[sample["responders"][position]]
            legacy_responder = users["alex" if legacy_author == "jamie" else "jamie"]
            # Include deleted posts in the match: restarting must not restore them.
            post = _matching_post(circle, sample, position, users)
            if not post:
                posted_at = now - timedelta(days=8 - position * 2, hours=2 - circle_number)
                post = CommunityPost(user_id=author.id, circle_id=circle.id, anonymous=anonymous, body=body, created_at=posted_at)
                db.session.add(post)
                db.session.flush()
                added["posts"] += 1
                db.session.add(CommunityLike(post_id=post.id, user_id=responder.id))
                added["likes"] += 1
            else:
                post.user_id = author.id
                old_like = CommunityLike.query.filter_by(post_id=post.id, user_id=legacy_responder.id).first()
                if old_like and not CommunityLike.query.filter_by(post_id=post.id, user_id=responder.id).first():
                    old_like.user_id = responder.id
            existing_reply = _matching_reply(post, sample, position, users)
            if existing_reply:
                existing_reply.user_id = responder.id
            elif post.status == "published":
                db.session.add(CommunityComment(post_id=post.id, user_id=responder.id, anonymous=False, body=reply, created_at=post.created_at + timedelta(hours=2)))
                added["comments"] += 1
    db.session.commit()
    return added
