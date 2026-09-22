from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_member
from app.db import get_db
from app.models import Member
from app.services.matching_service import rank_candidates

router = APIRouter(prefix="/members", tags=["matching"])


@router.get("/{member_id}/candidates")
def get_candidates(
    member_id: int,
    reason: str,
    member: Member = Depends(get_current_member),
    db: Session = Depends(get_db),
):
    if member_id != member.id:
        raise HTTPException(status_code=403, detail="can only rank your own candidates")
    return rank_candidates(member, reason, db)
