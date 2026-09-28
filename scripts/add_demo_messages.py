"""Adds NEW conversation messages for the Part 3 demo. Seed data is left
untouched - but every seeded message already has an attribute row, so under
the idempotency rule they would all be skipped and no LLM call would happen.
Safe to re-run: a message with the same member+body is not added twice.

    python -m scripts.add_demo_messages     # prints the message ids to use
"""
from app.db import SessionLocal
from app.models import ConversationMessage, Member

DEMO = [
    "Looking to hire a head of product for my Series B startup, any recommendations?",
    "I spent ten years in commercial real estate and can advise on lease negotiations.",
    "I've been dealing with burnout and my doctor has me on a lighter schedule.",
    "Anyone up for a Sunday sailing trip this month?",
    "I might look at angel investing next year, but nothing concrete yet.",
]


def main() -> None:
    db = SessionLocal()
    members = (
        db.query(Member)
        .filter(Member.club_id == "riverside", Member.role == "member")
        .order_by(Member.id)
        .all()
    )
    ids = []
    for member, body in zip(members, DEMO):
        existing = (
            db.query(ConversationMessage)
            .filter(ConversationMessage.member_id == member.id, ConversationMessage.body == body)
            .first()
        )
        if existing is None:
            existing = ConversationMessage(member_id=member.id, club_id="riverside", body=body)
            db.add(existing)
            db.commit()
            db.refresh(existing)
        ids.append(existing.id)
    print("riverside demo message ids:", ids)
    print('body to send: {"message_ids": %s}' % ids)


if __name__ == "__main__":
    main()
