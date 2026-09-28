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


def _two_clubs(db):
    db.add(Club(id="riverside", name="Riverside"))
    db.add(Club(id="oakhurst", name="Oakhurst"))
    a = Member(club_id="riverside", name="A", email="a@example.com", token="tok-a", role="member")
    b = Member(club_id="riverside", name="B", email="b@example.com", token="tok-b", role="member")
    c = Member(club_id="riverside", name="C", email="c@example.com", token="tok-c", role="member")
    admin = Member(club_id="riverside", name="Adm", email="adm@example.com", token="tok-adm", role="admin")
    other = Member(club_id="oakhurst", name="O", email="o@example.com", token="tok-o", role="member")
    db.add_all([a, b, c, admin, other])
    db.commit()
    return a, b, c, admin, other


def test_introduction_never_includes_restricted_attributes(db):
    a, b, *_ = _two_clubs(db)
    db.add(MemberAttribute(member_id=a.id, club_id="riverside", kind="need", text="needs a CFO", confidence=0.9))
    db.add(
        MemberAttribute(
            member_id=a.id, club_id="riverside", kind="context", text="in therapy for anxiety",
            confidence=0.9, restricted=True,
        )
    )
    db.add(MemberAttribute(member_id=b.id, club_id="riverside", kind="offer", text="offers CFO services", confidence=0.9))
    db.commit()

    resp = client.get(f"/introductions/{a.id}/{b.id}", params={"reason": "business"}, headers={"X-Member-Token": "tok-b"})
    assert resp.status_code == 200
    text = resp.json()["reason_text"]
    assert "CFO" in text
    assert "therapy" not in text and "anxiety" not in text


def test_introduction_rejects_member_from_another_club(db):
    a, _, _, _, other = _two_clubs(db)
    db.add(MemberAttribute(member_id=other.id, club_id="oakhurst", kind="need", text="secret oakhurst fact", confidence=0.9))
    db.commit()

    resp = client.get(f"/introductions/{a.id}/{other.id}", params={"reason": "business"}, headers={"X-Member-Token": "tok-a"})
    assert resp.status_code == 404
    assert "secret oakhurst fact" not in resp.text


def test_introduction_rejects_member_who_is_not_a_party(db):
    a, b, c, *_ = _two_clubs(db)
    resp = client.get(f"/introductions/{a.id}/{b.id}", params={"reason": "business"}, headers={"X-Member-Token": "tok-c"})
    assert resp.status_code == 403


def test_admin_can_request_introduction_within_own_club(db):
    a, b, *_ = _two_clubs(db)
    resp = client.get(f"/introductions/{a.id}/{b.id}", params={"reason": "business"}, headers={"X-Member-Token": "tok-adm"})
    assert resp.status_code == 200


def test_introduction_with_only_restricted_attributes_has_insufficient_basis(db):
    a, b, *_ = _two_clubs(db)
    db.add(
        MemberAttribute(
            member_id=a.id, club_id="riverside", kind="context", text="in therapy",
            confidence=0.9, restricted=True,
        )
    )
    db.add(MemberAttribute(member_id=b.id, club_id="riverside", kind="offer", text="offers CFO services", confidence=0.9))
    db.commit()

    resp = client.get(f"/introductions/{a.id}/{b.id}", params={"reason": "business"}, headers={"X-Member-Token": "tok-a"})
    assert resp.status_code == 200
    assert resp.json()["reason_text"] == "insufficient basis for an introduction"
    assert "therapy" not in resp.text
