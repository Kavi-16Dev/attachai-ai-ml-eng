from fastapi.testclient import TestClient

from app.main import app
from app.models import Booking, Club, Member

client = TestClient(app)


def test_confirm_payment_succeeds(db):
    db.add(Club(id="riverside", name="Riverside"))
    m = Member(club_id="riverside", name="A", email="a@example.com", token="tok-a", role="member")
    db.add(m)
    db.commit()

    booking = Booking(member_id=m.id, club_id="riverside", description="Dinner", amount_cents=5000, status="pending")
    db.add(booking)
    db.commit()

    resp = client.post(
        f"/bookings/{booking.id}/confirm-payment",
        json={"amount_cents": 5000},
        headers={"X-Member-Token": "tok-a"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "succeeded"
