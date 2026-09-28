import logging
from functools import lru_cache

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import require_club_admin
from app.db import get_db
from app.llm_client import LLMClient
from app.llm_errors import PermanentLLMError
from app.models import ConversationMessage, Member, MemberAttribute

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/clubs", tags=["extraction"])


class ExtractAttributesIn(BaseModel):
    message_ids: list[int]


@lru_cache(maxsize=1)
def _default_llm_client() -> LLMClient:
    # Built lazily so importing this module (and running the tests, which
    # override get_llm_client) never requires OPENAI_API_KEY.
    from app.llm_providers.openai_client import OpenAILLMClient

    return OpenAILLMClient()


def get_llm_client() -> LLMClient:
    return _default_llm_client()


def _process_message(db: Session, llm_client: LLMClient, club_id: str, message_id: int) -> dict:
    # Row lock on the message: a concurrent request for the same message
    # blocks here until we commit, then sees our attribute rows below and
    # skips. Without it two requests could both pass the check and insert
    # duplicates (there is no unique constraint to catch that, and we may
    # not add one).
    message = (
        db.query(ConversationMessage)
        .filter(ConversationMessage.id == message_id, ConversationMessage.club_id == club_id)
        .with_for_update()
        .first()
    )
    if message is None:
        db.rollback()
        return {"message_id": message_id, "status": "not_found"}

    # Idempotency key: an existing MemberAttribute whose source_message_id
    # equals this message's id means it has already been processed.
    already_processed = (
        db.query(MemberAttribute.id)
        .filter(MemberAttribute.source_message_id == message.id)
        .first()
    )
    if already_processed is not None:
        db.rollback()  # release the row lock
        return {"message_id": message_id, "status": "already_processed", "attributes_created": 0}

    try:
        extracted = llm_client.extract_attributes(message.body)
    except PermanentLLMError as exc:
        db.rollback()
        return {"message_id": message_id, "status": "failed", "error": str(exc)}

    for attr in extracted:
        db.add(
            MemberAttribute(
                member_id=message.member_id,
                club_id=club_id,
                kind=attr["kind"],
                text=attr["text"],
                confidence=attr["confidence"],
                restricted=attr["restricted"],
                source_message_id=message.id,
            )
        )
    db.commit()  # one commit per message: a later failure can't undo this one
    return {"message_id": message_id, "status": "created", "attributes_created": len(extracted)}


@router.post("/{club_id}/extract-attributes")
def extract_attributes(
    club_id: str,
    payload: ExtractAttributesIn,
    admin: Member = Depends(require_club_admin),  # listed first: authz runs before the LLM client is built
    db: Session = Depends(get_db),
    llm_client: LLMClient = Depends(get_llm_client),
):
    results = []
    for message_id in payload.message_ids:
        try:
            results.append(_process_message(db, llm_client, club_id, message_id))
        except Exception as exc:  # noqa: BLE001 - isolate one message from the batch
            db.rollback()
            logger.exception("extraction failed for message %s", message_id)
            results.append(
                {"message_id": message_id, "status": "failed", "error": f"{type(exc).__name__}: {exc}"}
            )
    return {"results": results}
