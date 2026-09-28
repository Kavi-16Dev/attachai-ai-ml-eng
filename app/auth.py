from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Member


def get_current_member(
    x_member_token: str = Header(..., alias="X-Member-Token"),
    db: Session = Depends(get_db),
) -> Member:
    member = db.query(Member).filter(Member.token == x_member_token).first()
    if not member:
        raise HTTPException(status_code=401, detail="invalid member token")
    return member


def require_admin(member: Member = Depends(get_current_member)) -> Member:
    if member.role != "admin":
        raise HTTPException(status_code=403, detail="admin role required")
    return member


def require_club_admin(club_id: str, admin: Member = Depends(require_admin)) -> Member:
    """Admin of *this* club. require_admin alone only proves the caller is
    an admin somewhere; without this scoping an admin of one club could act
    on another club's data."""
    if admin.club_id != club_id:
        raise HTTPException(status_code=403, detail="admin of a different club")
    return admin
