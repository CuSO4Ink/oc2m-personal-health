import pytest
from datetime import timedelta

from app import create_app
from app.extensions import db
from app.models import CommunityCircle, CommunityComment, Notification, User
from app.models import utc_now
from app.community_models import CommunityConnection
from sqlalchemy import update


@pytest.fixture
def community():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    clients = [app.test_client() for _ in range(3)]
    profiles = []
    for index, client in enumerate(clients):
        response = client.post("/api/auth/register", json={"full_name": f"Private legal name {index}", "email": f"friend-{index}@example.com", "password": "Patient123"})
        assert response.status_code == 201
        assert client.get("/api/community/connections").status_code == 403
        client.patch("/api/community/profile", json={"enabled": True})
        response = client.patch("/api/community/identity", json={"nickname": f"Community Pal {index}", "discoverable": index == 1})
        profiles.append(response.get_json()["profile"])
    return app, clients, profiles


def connect(first, second, profile):
    response = first.post("/api/community/connections", json={"invite_code": profile["invite_code"]})
    assert response.status_code == 201
    identifier = response.get_json()["connection"]["id"]
    assert second.patch(f"/api/community/connections/{identifier}", json={"action": "accept"}).status_code == 200
    return identifier


def test_friend_consent_withdraw_reject_discovery_and_identity(community):
    app, (first, second, third), profiles = community
    discovered = first.get("/api/community/members?q=Community").get_json()["members"]
    assert discovered == [{"nickname": "Community Pal 1", "public_id": profiles[1]["public_id"]}]
    assert third.post("/api/community/connections", json={"public_id": profiles[0]["public_id"]}).status_code == 404
    result = first.post("/api/community/connections", json={"public_id": profiles[1]["public_id"]})
    connection = result.get_json()["connection"]
    key = connection["id"]
    assert "user_id" not in connection and "email" not in connection
    assert "Private legal name" not in result.get_data(as_text=True)
    assert first.patch(f"/api/community/connections/{key}", json={"action": "accept"}).status_code == 409
    assert first.post(f"/api/community/connections/{key}/messages", json={"body": "No consent yet"}).status_code == 404
    assert third.patch(f"/api/community/connections/{key}", json={"action": "accept"}).status_code == 404
    assert first.patch(f"/api/community/connections/{key}", json={"action": "withdraw"}).status_code == 200
    assert second.get("/api/community/connections").get_json()["incoming"] == []
    assert first.post("/api/community/connections", json={"invite_code": profiles[1]["invite_code"]}).status_code == 429
    with app.app_context():
        db.session.get(CommunityConnection, key).updated_at = utc_now() - timedelta(minutes=6)
        db.session.commit()
    assert first.post("/api/community/connections", json={"invite_code": profiles[1]["invite_code"]}).status_code == 201
    assert second.patch(f"/api/community/connections/{key}", json={"action": "reject"}).status_code == 200
    assert first.post("/api/community/connections", json={"invite_code": profiles[1]["invite_code"]}).status_code == 429
    assert second.get("/api/notifications?category=community").get_json()["notifications"] == []


def test_two_user_messages_pagination_isolation_and_unread(community):
    _, (first, second, third), profiles = community
    key = connect(first, second, profiles[1])
    ids = []
    for text in ["Hello", "I enjoyed my walk today", "Hope you are doing well"]:
        response = first.post(f"/api/community/connections/{key}/messages", json={"body": text})
        assert response.status_code == 201
        ids.append(response.get_json()["message"]["id"])
    assert third.get(f"/api/community/connections/{key}/messages").status_code == 404
    assert third.post(f"/api/community/connections/{key}/messages", json={"body": "Intruder"}).status_code == 404
    recent = second.get(f"/api/community/connections/{key}/messages?limit=2").get_json()
    assert [item["id"] for item in recent["messages"]] == ids[1:]
    assert recent["has_more"] is True
    older = second.get(f"/api/community/connections/{key}/messages?before_id={ids[1]}&limit=2").get_json()
    assert [item["id"] for item in older["messages"]] == ids[:1]
    assert second.get("/api/community/connections").get_json()["unread"] == 3
    notifications = second.get("/api/notifications?category=community").get_json()
    assert len(notifications["notifications"]) == 3
    assert all(item["action_path"] == f"/community?tab=connections&conversation={key}" for item in notifications["notifications"])
    assert second.patch(f"/api/community/connections/{key}/messages/read", json={"through_id": ids[1]}).status_code == 200
    assert second.get("/api/community/connections").get_json()["unread"] == 1
    assert second.get("/api/notifications/summary").get_json()["summary"]["unread_by_category"]["community"] == 1
    assert third.post(f"/api/community/messages/{ids[0]}/reports", json={"reason": "privacy"}).status_code == 404
    assert first.post(f"/api/community/messages/{ids[0]}/reports", json={"reason": "privacy"}).status_code == 404


def test_closing_community_stops_contact_and_does_not_restore_old_badges(community):
    _, (first, second, third), profiles = community
    key = connect(first, second, profiles[1])
    first.post(f"/api/community/connections/{key}/messages", json={"body": "Unread before closing"})
    third.post("/api/community/connections", json={"invite_code": profiles[1]["invite_code"]})
    assert second.get("/api/notifications/summary").get_json()["summary"]["unread_by_category"]["community"] == 2
    assert second.patch("/api/community/profile", json={"enabled": False}).status_code == 200
    assert second.get("/api/community/connections").status_code == 403
    assert first.post(f"/api/community/connections/{key}/messages", json={"body": "Should be rejected"}).status_code == 404
    assert second.get("/api/notifications?category=community").get_json()["notifications"] == []
    second.patch("/api/community/profile", json={"enabled": True})
    connections = second.get("/api/community/connections").get_json()
    assert connections["unread"] == 0 and connections["incoming"] == []
    assert second.get("/api/notifications/summary").get_json()["summary"]["unread_by_category"]["community"] == 0
    assert all(item["read"] for item in second.get(f"/api/community/connections/{key}/messages").get_json()["messages"])
    first.post(f"/api/community/connections/{key}/messages", json={"body": "New after reopening"})
    assert second.get("/api/community/connections").get_json()["unread"] == 1


def test_block_remove_and_message_report_simulation(community):
    app, (first, second, third), profiles = community
    key = connect(first, second, profiles[1])
    item = first.post(f"/api/community/connections/{key}/messages", json={"body": "Message submitted for review"}).get_json()["message"]
    reported = second.post(f"/api/community/messages/{item['id']}/reports", json={"reason": "harassment", "details": "Please review"})
    assert reported.status_code == 201
    report_key = reported.get_json()["report"]["id"]
    assert third.post(f"/api/community/reports/{report_key}/simulate-review").status_code == 404
    first_stage = second.post(f"/api/community/reports/{report_key}/simulate-review").get_json()["reports"][0]
    assert first_stage["status"] == "submitted" and first_stage["simulation_stage"] == "in_review"
    final_stage = second.post(f"/api/community/reports/{report_key}/simulate-review").get_json()["reports"][0]
    assert final_stage["simulation_stage"] == "closed_demo"
    assert "No moderator" in final_stage["simulation_note"]
    assert second.post(f"/api/community/connections/{key}/block").status_code == 201
    assert first.get(f"/api/community/connections/{key}/messages").status_code == 404
    assert second.get(f"/api/community/connections/{key}/messages").status_code == 404
    assert first.get("/api/community/connections").get_json()["friends"] == []
    assert first.post("/api/community/connections", json={"invite_code": profiles[1]["invite_code"]}).status_code == 404
    assert first.get("/api/notifications?category=community").get_json()["notifications"] == []
    block = second.get("/api/community").get_json()["blocks"][0]
    assert second.delete(f"/api/community/blocks/{block['id']}").status_code == 200
    assert first.post(f"/api/community/connections/{key}/messages", json={"body": "Unblock is not consent"}).status_code == 404
    with app.app_context():
        db.session.get(CommunityConnection, key).updated_at = utc_now() - timedelta(minutes=6)
        db.session.commit()
    key = connect(first, second, profiles[1])
    assert second.patch(f"/api/community/connections/{key}", json={"action": "remove"}).status_code == 200
    assert first.post(f"/api/community/connections/{key}/messages", json={"body": "Removed friend"}).status_code == 404


def test_anonymous_post_never_discloses_account_or_friend_key(community):
    app, (first, second, _), profiles = community
    with app.app_context():
        circle = CommunityCircle(name="Friendly circle", topic="Wellbeing", description="Share experiences")
        db.session.add(circle)
        db.session.commit()
        key = circle.id
    for client in (first, second):
        client.post(f"/api/community/circles/{key}/membership")
    post = second.post("/api/community/posts", json={"circle_id": key, "body": "My personal experience", "anonymous": True, "acknowledged": True}).get_json()["post"]
    viewed = first.get("/api/community/posts").get_json()["posts"][0]
    assert viewed["author_name"] == "Anonymous member" and viewed["can_connect"] is False
    assert "public_id" not in viewed and "user_id" not in viewed and "invite_code" not in viewed
    assert profiles[1]["nickname"] not in str(viewed)
    assert first.post("/api/community/connections", json={"post_id": post["id"]}).status_code == 404
    comment = second.post(f"/api/community/posts/{post['id']}/comments", json={"body": "A nickname comment", "anonymous": False}).get_json()["post"]["comments"][0]
    assert comment["author_name"] == profiles[1]["nickname"]
    assert "Private legal name" not in str(comment)


def test_rotating_invite_and_input_validation(community):
    _, (first, second, _), profiles = community
    old = profiles[1]["invite_code"]
    new = second.post("/api/community/identity/rotate-invite").get_json()["invite_code"]
    assert old != new
    assert first.post("/api/community/connections", json={"invite_code": old}).status_code == 404
    assert second.patch("/api/community/identity", json={"nickname": "x"}).status_code == 400
    assert second.patch("/api/community/identity", json={"nickname": "A nickname", "discoverable": "true"}).status_code == 400
    assert first.post("/api/community/connections", json=[]).status_code == 404


def test_message_delivery_nonce_prevents_duplicate_retries(community):
    _, (first, second, _), profiles = community
    key = connect(first, second, profiles[1])
    payload = {"body": "One delivery even if the response is lost", "client_nonce": "same-client-attempt-123"}
    initial = first.post(f"/api/community/connections/{key}/messages", json=payload)
    replay = first.post(f"/api/community/connections/{key}/messages", json=payload)
    assert initial.status_code == 201 and replay.status_code == 200
    assert initial.get_json()["message"]["id"] == replay.get_json()["message"]["id"]
    assert replay.get_json()["replayed"] is True
    assert len(second.get(f"/api/community/connections/{key}/messages").get_json()["messages"]) == 1
    assert first.post(f"/api/community/connections/{key}/messages", json={**payload, "body": "A different body"}).status_code == 409


def test_real_request_withdrawal_wins_over_stale_acceptance(tmp_path, monkeypatch):
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///" + (tmp_path / "community-race.sqlite").as_posix()})
    first, second = app.test_client(), app.test_client()
    for index, client in enumerate([first, second]):
        client.post("/api/auth/register", json={"full_name": f"Race User {index}", "email": f"race-{index}@example.com", "password": "Patient123"})
        client.patch("/api/community/profile", json={"enabled": True})
    code = second.get("/api/community").get_json()["profile"]["invite_code"]
    key = first.post("/api/community/connections", json={"invite_code": code}).get_json()["connection"]["id"]
    execute = db.session.execute
    injected = False

    def concurrent_withdrawal(statement, *args, **kwargs):
        nonlocal injected
        if not injected and getattr(getattr(statement, "table", None), "name", None) == "community_connections":
            injected = True
            # Another database connection commits after the recipient's read but before its UPDATE.
            with db.engine.begin() as connection:
                connection.execute(update(CommunityConnection).where(CommunityConnection.id == key).values(status="withdrawn", updated_at=utc_now()))
        return execute(statement, *args, **kwargs)

    monkeypatch.setattr(db.session, "execute", concurrent_withdrawal)
    response = second.patch(f"/api/community/connections/{key}", json={"action": "accept"})
    assert injected and response.status_code == 409
    with app.app_context():
        assert db.session.get(CommunityConnection, key).status == "withdrawn"


def test_simulated_review_is_disabled_outside_demo_mode(community):
    app, (first, second, _), profiles = community
    key = connect(first, second, profiles[1])
    item = first.post(f"/api/community/connections/{key}/messages", json={"body": "A reported message"}).get_json()["message"]
    report = second.post(f"/api/community/messages/{item['id']}/reports", json={"reason": "privacy"}).get_json()["report"]
    app.config["DEMO_FEATURES_ENABLED"] = False
    response = second.post(f"/api/community/reports/{report['id']}/simulate-review")
    assert response.status_code == 503 and response.get_json()["error"] == "not_connected"
    assert second.get("/api/community").get_json()["reports"][0]["status"] == "submitted"


def test_comments_received_while_disabled_do_not_reappear_as_notifications(community):
    app, (first, second, _), _profiles = community
    with app.app_context():
        circle = CommunityCircle(name="Quiet circle", topic="Wellbeing", description="A quiet circle")
        db.session.add(circle)
        db.session.commit()
        key = circle.id
    for client in (first, second):
        client.post(f"/api/community/circles/{key}/membership")
    post = first.post("/api/community/posts", json={"circle_id": key, "body": "An experience worth sharing", "anonymous": True, "acknowledged": True}).get_json()["post"]
    second.post(f"/api/community/posts/{post['id']}/comments", json={"body": "Before closing", "anonymous": True})
    assert first.get("/api/notifications/summary").get_json()["summary"]["unread_by_category"]["community"] == 1
    first.patch("/api/community/profile", json={"enabled": False})
    with app.app_context():
        author = CommunityComment.query.first().user_id
        db.session.add(CommunityComment(post_id=post["id"], user_id=author, body="While community is off", anonymous=True))
        db.session.commit()
    first.patch("/api/community/profile", json={"enabled": True})
    assert first.get("/api/notifications?category=community").get_json()["notifications"] == []
    assert first.get("/api/community").get_json()["posts"][0]["comment_count"] == 2


def test_notification_history_over_100_rows_pagination_filters_and_isolation(community):
    app, (first, second, _), _profiles = community
    with app.app_context():
        owner = User.query.filter_by(email="friend-0@example.com").first()
        for index in range(125):
            db.session.add(Notification(user_id=owner.id, category="system", title=f"{'Archive' if index < 5 else 'History'} {index:03d}", message="Synthetic pagination fixture", dedupe_key=f"pagination-{index}", created_at=utc_now() - timedelta(minutes=125 - index)))
        db.session.commit()
    initial = first.get("/api/notifications").get_json()
    assert initial["total"] == initial["summary"]["total"] == initial["summary"]["unread"] == 125
    assert initial["page"] == 1 and initial["page_size"] == 20 and len(initial["notifications"]) == 20
    seen = set()
    for page in range(1, 8):
        result = first.get(f"/api/notifications?page={page}&page_size=20").get_json()
        identifiers = {item["id"] for item in result["notifications"]}
        assert not identifiers.intersection(seen)
        seen.update(identifiers)
        assert result["summary"]["total"] == 125
    assert len(seen) == 125
    last = first.get("/api/notifications?page=999&page_size=20").get_json()
    assert last["page"] == 7 and len(last["notifications"]) == 5
    filtered = first.get("/api/notifications?q=Archive&page=7").get_json()
    assert filtered["page"] == 1 and filtered["total"] == 5 and filtered["summary"]["total"] == 125
    assert first.get("/api/notifications?page=0").status_code == 400
    assert first.get("/api/notifications?page_size=101").status_code == 400
    assert second.get("/api/notifications?page=2").get_json()["total"] == 0
    assert second.patch(f"/api/notifications/{next(iter(seen))}/read", json={"read": True}).status_code == 404
