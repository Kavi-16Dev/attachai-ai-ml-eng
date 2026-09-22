from fastapi.testclient import TestClient

from app.main import app
from app.models import Club, Member

client = TestClient(app)


def test_session_books_end_to_end(db):
    db.add(Club(id="riverside", name="Riverside"))
    m = Member(club_id="riverside", name="A", email="a@example.com", token="tok-a", role="member")
    db.add(m)
    db.commit()

    resp = client.post("/sessions", headers={"X-Member-Token": "tok-a"})
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]

    resp = client.post(
        f"/sessions/{session_id}/turn",
        json={"intent": "book", "party_size": 2},
        headers={"X-Member-Token": "tok-a"},
    )
    assert resp.json()["status"] == "awaiting_confirmation"

    resp = client.post(
        f"/sessions/{session_id}/turn",
        json={"intent": "affirm", "amount_cents": 4000},
        headers={"X-Member-Token": "tok-a"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "confirmed"


def test_refund_dispute_escalates(db):
    db.add(Club(id="riverside", name="Riverside"))
    m = Member(club_id="riverside", name="A", email="a@example.com", token="tok-a", role="member")
    db.add(m)
    db.commit()

    session_id = client.post("/sessions", headers={"X-Member-Token": "tok-a"}).json()["session_id"]

    resp = client.post(
        f"/sessions/{session_id}/turn",
        json={"intent": "refund_dispute"},
        headers={"X-Member-Token": "tok-a"},
    )
    assert resp.json()["status"] == "escalated"
