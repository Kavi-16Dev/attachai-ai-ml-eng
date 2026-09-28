from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_member
from app.db import get_db
from app.models import Member, MemberAttribute

router = APIRouter(prefix="/introductions", tags=["introductions"])


@router.get("/{member_a_id}/{member_b_id}")
def generate_reason(
    member_a_id: int,
    member_b_id: int,
    reason: str,
    db: Session = Depends(get_db),
    member: Member = Depends(get_current_member),
):
    if member_a_id == member_b_id:
        raise HTTPException(status_code=400, detail="an introduction needs two different members")

    # get_current_member only authenticates the caller. Nothing above ties
    # the two ids in the URL to the caller, so scope them explicitly: both
    # must belong to the caller's own club. "Missing" and "other club" get
    # the same 404 so the endpoint can't be used to probe which ids exist.
    in_club = (
        db.query(Member.id)
        .filter(Member.id.in_([member_a_id, member_b_id]), Member.club_id == member.club_id)
        .all()
    )
    if len(in_club) != 2:
        raise HTTPException(status_code=404, detail="member not found")

    # A member may only request introductions they are part of; admins may
    # request any within their own club.
    if member.role != "admin" and member.id not in (member_a_id, member_b_id):
        raise HTTPException(status_code=403, detail="you are not a party to this introduction")

    def attribute_text(member_id: int) -> str:
        # Restricted attributes (health, clinical, psychometric) never go
        # into generated text; club_id is re-applied on the query itself.
        attrs = (
            db.query(MemberAttribute)
            .filter(
                MemberAttribute.member_id == member_id,
                MemberAttribute.club_id == member.club_id,
                MemberAttribute.restricted == False,  # noqa: E712
            )
            .all()
        )
        return "; ".join(a.text for a in attrs)

    a_text = attribute_text(member_a_id)
    b_text = attribute_text(member_b_id)
    if not a_text or not b_text:
        # With restricted attributes excluded a member may have nothing left
        # to draw on; say so rather than emit a sentence with a blank side.
        return {"reason_text": "insufficient basis for an introduction"}
    return {"reason_text": f"Because {a_text} and {b_text} — a good {reason} match."}
