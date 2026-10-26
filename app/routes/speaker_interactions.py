# ============================================================================
# Speaker Follow + Direct Messages (Production Ready)
# File: app/routes/speaker_interactions.py
#
# follow_router -> mount at /api/v1/speakers
#   GET    /me/following          speaker IDs the current user follows
#   POST   /{speaker_id}/follow   follow a speaker (safe to repeat)
#   DELETE /{speaker_id}/follow   unfollow a speaker
#
# chat_router -> mount at /api/v1/chat
#   POST /speakers/{speaker_id}/messages   send a message to a speaker
#   GET  /speakers/{speaker_id}/messages   conversation with a speaker
# ============================================================================

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Index, Integer, Text,
    UniqueConstraint, and_, or_,
)
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.models import Base, NotificationPreference, Speaker, User
from app.routes.auth import get_current_user

logger = logging.getLogger(__name__)

follow_router = APIRouter()
chat_router = APIRouter()


# ============================================================================
# Database Models
# ============================================================================

class SpeakerFollow(Base):
    __tablename__ = "speaker_follows"
    __table_args__ = (
        UniqueConstraint("follower_user_id", "speaker_id", name="uq_speaker_follow"),
    )

    id = Column(Integer, primary_key=True, index=True)
    follower_user_id = Column(
        Integer,
        ForeignKey(f"{User.__tablename__}.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    speaker_id = Column(
        Integer,
        ForeignKey(f"{Speaker.__tablename__}.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class DirectMessage(Base):
    __tablename__ = "direct_messages"
    __table_args__ = (
        Index("idx_direct_message_pair", "sender_id", "recipient_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(
        Integer,
        ForeignKey(f"{User.__tablename__}.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recipient_id = Column(
        Integer,
        ForeignKey(f"{User.__tablename__}.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content = Column(Text, nullable=False)
    is_read = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


# ============================================================================
# Schemas
# ============================================================================

class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)


# ============================================================================
# Helpers
# ============================================================================

def _current_user_id(current_user: Any) -> int:
    user_id = getattr(current_user, "id", None)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid user session")
    return user_id


def _get_speaker_or_404(db: DBSession, speaker_id: int) -> Speaker:
    speaker = db.query(Speaker).filter(Speaker.id == speaker_id).first()
    if speaker is None:
        raise HTTPException(status_code=404, detail="Speaker not found")
    return speaker


def _message_payload(m: DirectMessage) -> dict:
    return {
        "id": m.id,
        "sender_id": m.sender_id,
        "recipient_id": m.recipient_id,
        "content": m.content,
        "is_read": m.is_read,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


# ============================================================================
# Follow Endpoints
# ============================================================================

@follow_router.get("/me/following")
def list_my_followed_speakers(
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    user_id = _current_user_id(current_user)
    rows = (
        db.query(SpeakerFollow.speaker_id)
        .filter(SpeakerFollow.follower_user_id == user_id)
        .all()
    )
    return {
        "status": "success",
        "data": {"speaker_ids": [row[0] for row in rows]},
    }


@follow_router.post("/{speaker_id}/follow", status_code=status.HTTP_200_OK)
def follow_speaker(
    speaker_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    user_id = _current_user_id(current_user)
    speaker = _get_speaker_or_404(db, speaker_id)

    if speaker.user_id == user_id:
        raise HTTPException(status_code=400, detail="You cannot follow yourself")

    already = (
        db.query(SpeakerFollow)
        .filter(
            SpeakerFollow.follower_user_id == user_id,
            SpeakerFollow.speaker_id == speaker_id,
        )
        .first()
    )
    if already:
        return {"status": "success", "following": True, "message": "Already following"}

    try:
        db.add(SpeakerFollow(follower_user_id=user_id, speaker_id=speaker_id))
        db.commit()
    except IntegrityError:
        # Another request saved the same follow first; the result is the same
        db.rollback()
        return {"status": "success", "following": True, "message": "Already following"}
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Failed to follow speaker %s: %s", speaker_id, exc)
        raise HTTPException(status_code=500, detail="Could not follow speaker")

    return {"status": "success", "following": True, "message": "Speaker followed"}


@follow_router.delete("/{speaker_id}/follow", status_code=status.HTTP_200_OK)
def unfollow_speaker(
    speaker_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    user_id = _current_user_id(current_user)
    _get_speaker_or_404(db, speaker_id)

    try:
        deleted = (
            db.query(SpeakerFollow)
            .filter(
                SpeakerFollow.follower_user_id == user_id,
                SpeakerFollow.speaker_id == speaker_id,
            )
            .delete(synchronize_session=False)
        )
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Failed to unfollow speaker %s: %s", speaker_id, exc)
        raise HTTPException(status_code=500, detail="Could not unfollow speaker")

    return {
        "status": "success",
        "following": False,
        "message": "Speaker unfollowed" if deleted else "You were not following this speaker",
    }


# ============================================================================
# Chat Endpoints
# ============================================================================

@chat_router.post("/speakers/{speaker_id}/messages", status_code=status.HTTP_201_CREATED)
def send_message_to_speaker(
    speaker_id: int,
    payload: MessageCreate,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    sender_id = _current_user_id(current_user)
    speaker = _get_speaker_or_404(db, speaker_id)
    recipient_id = speaker.user_id

    if recipient_id == sender_id:
        raise HTTPException(status_code=400, detail="You cannot message yourself")

    prefs = (
        db.query(NotificationPreference)
        .filter(NotificationPreference.user_id == recipient_id)
        .first()
    )
    if prefs is not None and prefs.enable_messages is False:
        raise HTTPException(
            status_code=403,
            detail="This user is currently not available for chat",
        )

    try:
        message = DirectMessage(
            sender_id=sender_id,
            recipient_id=recipient_id,
            content=payload.content.strip(),
        )
        db.add(message)
        db.commit()
        db.refresh(message)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Failed to send message to speaker %s: %s", speaker_id, exc)
        raise HTTPException(status_code=500, detail="Could not send your message")

    return {
        "status": "success",
        "message": "Message sent",
        "data": _message_payload(message),
    }


@chat_router.get("/speakers/{speaker_id}/messages")
def list_speaker_conversation(
    speaker_id: int,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    user_id = _current_user_id(current_user)
    speaker = _get_speaker_or_404(db, speaker_id)
    other_id = speaker.user_id

    rows = (
        db.query(DirectMessage)
        .filter(
            or_(
                and_(DirectMessage.sender_id == user_id, DirectMessage.recipient_id == other_id),
                and_(DirectMessage.sender_id == other_id, DirectMessage.recipient_id == user_id),
            )
        )
        .order_by(DirectMessage.created_at.asc(), DirectMessage.id.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "status": "success",
        "data": [_message_payload(m) for m in rows],
    }