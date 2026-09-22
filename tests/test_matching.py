from fastapi.testclient import TestClient

from app.embeddings import embedding_client
from app.main import app
from app.models import Club, Member, MemberAttribute
from app.services.matching_service import build_member_profile_text

client = TestClient(app)


def test_rank_candidates_returns_sorted_list(db):
    db.add(Club(id="riverside", name="Riverside"))
    m1 = Member(club_id="riverside", name="A", email="a@example.com", token="tok-a", role="member")
    m2 = Member(club_id="riverside", name="B", email="b@example.com", token="tok-b", role="member")
    db.add_all([m1, m2])
    db.commit()

    db.add(MemberAttribute(member_id=m1.id, club_id="riverside", kind="need", text="needs a CFO", confidence=0.9))
    db.add(MemberAttribute(member_id=m2.id, club_id="riverside", kind="offer", text="offers CFO services", confidence=0.9))
    db.commit()

    m2.profile_embedding = embedding_client.embed(build_member_profile_text(m2, db))
    db.commit()

    resp = client.get(
        f"/members/{m1.id}/candidates",
        params={"reason": "business"},
        headers={"X-Member-Token": "tok-a"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["member_id"] == m2.id
