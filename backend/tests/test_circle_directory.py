import pytest

from app import create_app
from app.extensions import db
from app.models import CommunityCircle


@pytest.fixture
def circle_members():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    clients = [app.test_client() for _ in range(4)]
    identities = []
    for index, client in enumerate(clients):
        assert client.post("/api/auth/register", json={"full_name": f"Private account {index}", "email": f"circle-{index}@example.test", "password": "Patient123"}).status_code == 201
        client.patch("/api/community/profile", json={"enabled": True})
        identities.append(client.patch("/api/community/identity", json={"nickname": f"Circle Pal {index}", "discoverable": index in (1, 3)}).get_json()["profile"])
    with app.app_context():
        circle = CommunityCircle(name="Everyday support", topic="Routines", description="Share everyday experiences.", guidance="Respect privacy.")
        db.session.add(circle)
        db.session.commit()
        circle_id = circle.id
    for client in clients[:3]:
        assert client.post(f"/api/community/circles/{circle_id}/membership").status_code == 201
    return clients, identities, circle_id


def directory(client, circle_id):
    response = client.get(f"/api/community/circles/{circle_id}/members")
    assert response.status_code == 200
    payload = response.get_json()
    circle = client.get(f"/api/community/circles/{circle_id}").get_json()["circle"]
    listed = next(item for item in client.get('/api/community').get_json()['circles'] if item['id'] == circle_id)
    assert circle['member_count_scope'] == listed['member_count_scope'] == 'visible'
    assert circle['member_count'] == listed['member_count'] == payload['total']
    return payload["members"]


def test_directory_requires_membership_and_respects_discovery_and_anonymity(circle_members):
    (viewer, public, private, outsider), identities, circle_id = circle_members
    introduction = outsider.get(f"/api/community/circles/{circle_id}").get_json()["circle"]
    assert introduction["description"] == "Share everyday experiences."
    assert introduction["guidance"] == "Respect privacy."
    assert introduction["joined"] is False
    assert introduction["member_count"] == 1
    assert outsider.get(f"/api/community/circles/{circle_id}/members").status_code == 403
    anonymous = public.post("/api/community/posts", json={"circle_id": circle_id, "body": "A private everyday experience.", "anonymous": True, "acknowledged": True}).get_json()["post"]
    assert anonymous["author_name"] == "Anonymous member"
    assert not anonymous.get("public_id") and not anonymous.get("author_public_id")
    assert anonymous["can_connect"] is False
    members = directory(viewer, circle_id)
    assert {member["nickname"] for member in members} == {"Circle Pal 0", "Circle Pal 1"}
    own = next(member for member in members if member["public_id"] == identities[0]["public_id"])
    visible = next(member for member in members if member["public_id"] == identities[1]["public_id"])
    assert own["connection_status"] == "self" and own["can_request"] is False
    assert visible["can_request"] is True
    assert all(set(member) == {"nickname", "public_id", "connection_status", "can_request", "connection_id"} for member in members)
    assert all(identities[2]["public_id"] != member["public_id"] for member in members)
    assert {member["nickname"] for member in directory(private, circle_id)} == {"Circle Pal 1", "Circle Pal 2"}
    assert viewer.get(f"/api/community/circles/{circle_id}/members?page=0").status_code == 400
    assert viewer.get(f"/api/community/circles/{circle_id}/members?page=bad").status_code == 400
    assert directory(viewer, circle_id) == members


def test_circle_connection_validates_both_memberships_and_opt_in(circle_members):
    (viewer, public, private, outsider), identities, circle_id = circle_members
    def request(sender, index, source=circle_id):
        return sender.post("/api/community/connections", json={"circle_id": source, "public_id": identities[index]["public_id"]})
    assert request(outsider, 1).status_code == 404
    assert request(viewer, 3).status_code == 404
    assert request(viewer, 2).status_code == 404
    assert request(viewer, 0).status_code == 404
    assert request(viewer, 1, True).status_code == 404
    public.delete(f"/api/community/circles/{circle_id}/membership")
    assert request(viewer, 1).status_code == 404
    public.post(f"/api/community/circles/{circle_id}/membership")
    public.patch("/api/community/identity", json={"nickname": "Circle Pal 1", "discoverable": False})
    assert request(viewer, 1).status_code == 404
    public.patch("/api/community/identity", json={"nickname": "Circle Pal 1", "discoverable": True})
    public.patch("/api/community/profile", json={"enabled": False})
    assert request(viewer, 1).status_code == 404
    assert all(member["nickname"] != "Circle Pal 1" for member in directory(viewer, circle_id))


def test_circle_requests_require_acceptance_for_chat_and_hide_blocked_members(circle_members):
    (viewer, public, private, outsider), identities, circle_id = circle_members
    result = viewer.post("/api/community/connections", json={"circle_id": circle_id, "public_id": identities[1]["public_id"]})
    assert result.status_code == 201
    connection_id = result.get_json()["connection"]["id"]
    entry = next(member for member in directory(viewer, circle_id) if member["public_id"] == identities[1]["public_id"])
    assert entry["connection_status"] == "outgoing" and entry["can_request"] is False
    # Discovery is a privacy preference even when a request exists.
    assert not any(member["public_id"] == identities[0]["public_id"] for member in directory(public, circle_id))
    viewer.patch("/api/community/identity", json={"nickname": "Circle Pal 0", "discoverable": True})
    incoming = next(member for member in directory(public, circle_id) if member["public_id"] == identities[0]["public_id"])
    assert incoming["connection_status"] == "incoming"
    assert viewer.post(f"/api/community/connections/{connection_id}/messages", json={"body": "Before consent"}).status_code == 404
    assert outsider.patch(f"/api/community/connections/{connection_id}", json={"action": "accept"}).status_code == 404
    assert public.patch(f"/api/community/connections/{connection_id}", json={"action": "accept"}).status_code == 200
    friend = next(member for member in directory(viewer, circle_id) if member["public_id"] == identities[1]["public_id"])
    assert friend["connection_status"] == "friends" and friend["connection_id"] == connection_id
    assert viewer.post(f"/api/community/connections/{connection_id}/messages", json={"body": "Thanks for accepting."}).status_code == 201
    assert public.post(f"/api/community/connections/{connection_id}/block").status_code == 201
    assert all(member["public_id"] != identities[1]["public_id"] for member in directory(viewer, circle_id))
    assert all(member["public_id"] != identities[0]["public_id"] for member in directory(public, circle_id))
    assert viewer.post("/api/community/connections", json={"circle_id": circle_id, "public_id": identities[1]["public_id"]}).status_code == 404
    assert viewer.get(f"/api/community/connections/{connection_id}/messages").status_code == 404


def test_fresh_demo_has_coherent_discussions_without_creating_friendships(tmp_path):
    from run_demo import prepare_demo
    from app.models import CommunityComment, CommunityPost
    from app.community_models import CommunityConnection

    app, _ = prepare_demo(demo_root=tmp_path)
    with app.app_context():
        circles = CommunityCircle.query.all()
        assert len(circles) == 3
        assert all(circle.description and circle.guidance for circle in circles)
        posts = CommunityPost.query.order_by(CommunityPost.id).all()
        assert len(posts) == 12 and sum(post.anonymous for post in posts) == 3
        assert len({post.body for post in posts}) == 12
        assert all(len(post.body) > 100 for post in posts)
        assert all(posts[index].created_at <= posts[index + 1].created_at for index in range(len(posts) - 1))
        assert CommunityComment.query.count() == 12
        assert len({post.user_id for post in posts}) == 5
        assert CommunityConnection.query.count() == 0
