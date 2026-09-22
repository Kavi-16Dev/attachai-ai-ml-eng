from sqlalchemy.orm import Session

from app.embeddings import embedding_client
from app.models import Member
from app.services.matching_service import build_member_profile_text


def refresh_member_embedding(member: Member, db: Session) -> None:
    text = build_member_profile_text(member, db)
    member.profile_embedding = embedding_client.embed(text)
    db.add(member)
    db.commit()
