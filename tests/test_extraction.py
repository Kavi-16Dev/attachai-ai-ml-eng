from fastapi.testclient import TestClient

from app.llm_client import FakeLLMClient
from app.llm_errors import PermanentLLMError
from app.main import app
from app.models import Club, ConversationMessage, Member, MemberAttribute
from app.routers.extraction import get_llm_client

client = TestClient(app)


def _seed_basic(db):
    db.add(Club(id="riverside", name="Riverside"))
    admin = Member(club_id="riverside", name="Admin", email="admin@example.com", token="tok-admin", role="admin")
    member = Member(club_id="riverside", name="A", email="a@example.com", token="tok-a", role="member")
    db.add_all([admin, member])
    db.commit()
    msg = ConversationMessage(member_id=member.id, club_id="riverside", body="I need a fractional CFO.")
    db.add(msg)
    db.commit()
    return admin, member, msg


def test_extraction_happy_path(db):
    admin, member, msg = _seed_basic(db)

    fake = FakeLLMClient(
        canned_response=[
            {"kind": "need", "text": "needs a fractional CFO", "confidence": 0.9, "restricted": False}
        ]
    )
    app.dependency_overrides[get_llm_client] = lambda: fake
    try:
        resp = client.post(
            "/clubs/riverside/extract-attributes",
            json={"message_ids": [msg.id]},
            headers={"X-Member-Token": "tok-admin"},
        )
    finally:
        app.dependency_overrides.pop(get_llm_client, None)

    assert resp.status_code == 200
    result = resp.json()["results"][0]
    assert result["status"] == "created"
    assert result["attributes_created"] == 1

    saved = db.query(MemberAttribute).filter(MemberAttribute.source_message_id == msg.id).all()
    assert len(saved) == 1
    assert saved[0].kind == "need"
    assert saved[0].restricted is False


def test_extraction_is_idempotent(db):
    admin, member, msg = _seed_basic(db)

    fake = FakeLLMClient(
        canned_response=[{"kind": "need", "text": "needs a CFO", "confidence": 0.9, "restricted": False}]
    )
    app.dependency_overrides[get_llm_client] = lambda: fake
    try:
        first = client.post(
            "/clubs/riverside/extract-attributes",
            json={"message_ids": [msg.id]},
            headers={"X-Member-Token": "tok-admin"},
        )
        second = client.post(
            "/clubs/riverside/extract-attributes",
            json={"message_ids": [msg.id]},
            headers={"X-Member-Token": "tok-admin"},
        )
    finally:
        app.dependency_overrides.pop(get_llm_client, None)

    assert first.json()["results"][0]["status"] == "created"
    assert second.json()["results"][0]["status"] == "already_processed"

    # No duplicate rows, and the LLM was only ever called once.
    saved = db.query(MemberAttribute).filter(MemberAttribute.source_message_id == msg.id).all()
    assert len(saved) == 1
    assert len(fake.calls) == 1


def test_extraction_requires_admin(db):
    admin, member, msg = _seed_basic(db)

    resp = client.post(
        "/clubs/riverside/extract-attributes",
        json={"message_ids": [msg.id]},
        headers={"X-Member-Token": "tok-a"},  # ordinary member, not admin
    )
    assert resp.status_code == 403


def test_extraction_rejects_cross_club_admin(db):
    db.add(Club(id="riverside", name="Riverside"))
    db.add(Club(id="oakhurst", name="Oakhurst"))
    other_admin = Member(
        club_id="oakhurst", name="Other Admin", email="oa@example.com", token="tok-other-admin", role="admin"
    )
    member = Member(club_id="riverside", name="A", email="a@example.com", token="tok-a", role="member")
    db.add_all([other_admin, member])
    db.commit()
    msg = ConversationMessage(member_id=member.id, club_id="riverside", body="hello")
    db.add(msg)
    db.commit()

    resp = client.post(
        "/clubs/riverside/extract-attributes",
        json={"message_ids": [msg.id]},
        headers={"X-Member-Token": "tok-other-admin"},
    )
    assert resp.status_code == 403


def test_extraction_isolates_per_message_failure(db):
    admin, member, msg1 = _seed_basic(db)
    msg2 = ConversationMessage(member_id=member.id, club_id="riverside", body="A second message.")
    db.add(msg2)
    db.commit()

    class FlakyClient:
        def __init__(self):
            self.calls = []

        def extract_attributes(self, message_text):
            self.calls.append(message_text)
            if "second" in message_text:
                return [{"kind": "context", "text": "ok", "confidence": 0.8, "restricted": False}]
            raise PermanentLLMError("simulated permanent failure")

    flaky = FlakyClient()
    app.dependency_overrides[get_llm_client] = lambda: flaky
    try:
        resp = client.post(
            "/clubs/riverside/extract-attributes",
            json={"message_ids": [msg1.id, msg2.id]},
            headers={"X-Member-Token": "tok-admin"},
        )
    finally:
        app.dependency_overrides.pop(get_llm_client, None)

    results = {r["message_id"]: r for r in resp.json()["results"]}
    assert results[msg1.id]["status"] == "failed"
    assert results[msg2.id]["status"] == "created"


def test_restricted_attribute_is_stored_but_never_reaches_matching(db):
    """Extraction writes restricted rows into the same table matching reads.
    Prove the row exists, is flagged, and is absent from the text that gets
    embedded for ranking."""
    from app.services.matching_service import build_member_profile_text

    admin, member, msg = _seed_basic(db)
    fake = FakeLLMClient(
        canned_response=[
            {"kind": "need", "text": "needs a fractional CFO", "confidence": 0.9, "restricted": False},
            {"kind": "context", "text": "in therapy for anxiety", "confidence": 0.9, "restricted": True},
        ]
    )
    app.dependency_overrides[get_llm_client] = lambda: fake
    try:
        client.post(
            "/clubs/riverside/extract-attributes",
            json={"message_ids": [msg.id]},
            headers={"X-Member-Token": "tok-admin"},
        )
    finally:
        app.dependency_overrides.pop(get_llm_client, None)

    rows = db.query(MemberAttribute).filter(MemberAttribute.member_id == member.id).all()
    assert {r.text: r.restricted for r in rows} == {
        "needs a fractional CFO": False,
        "in therapy for anxiety": True,
    }

    profile_text = build_member_profile_text(member, db)
    assert "fractional CFO" in profile_text
    assert "therapy" not in profile_text and "anxiety" not in profile_text
