from fastapi import APIRouter, Depends
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
    attrs_a = db.query(MemberAttribute).filter(MemberAttribute.member_id == member_a_id).all()
    attrs_b = db.query(MemberAttribute).filter(MemberAttribute.member_id == member_b_id).all()

    # Every attribute is stated as fact regardless of its confidence score.
    a_text = "; ".join(a.text for a in attrs_a)
    b_text = "; ".join(b.text for b in attrs_b)
    return {"reason_text": f"Because {a_text} and {b_text} — a good {reason} match."}
