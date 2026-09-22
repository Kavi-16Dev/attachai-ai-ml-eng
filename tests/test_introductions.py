from fastapi.testclient import TestClient

from app.main import app
from app.models import Club, Member, MemberAttribute

client = TestClient(app)


def test_generate_reason_includes_attributes(db):
    db.add(Club(id="riverside", name="Riverside"))
    m1 = Member(club_id="riverside", name="A", email="a@example.com", token="tok-a", role="member")
    m2 = Member(club_id="riverside", name="B", email="b@example.com", token="tok-b", role="member")
    db.add_all([m1, m2])
    db.commit()

    db.add(MemberAttribute(member_id=m1.id, club_id="riverside", kind="need", text="needs a CFO", confidence=0.9))
    db.add(MemberAttribute(member_id=m2.id, club_id="riverside", kind="offer", text="offers CFO services", confidence=0.9))
    db.commit()

    resp = client.get(
        f"/introductions/{m1.id}/{m2.id}",
        params={"reason": "business"},
        headers={"X-Member-Token": "tok-a"},
    )
    assert resp.status_code == 200
    assert "CFO" in resp.json()["reason_text"]
