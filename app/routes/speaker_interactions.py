# ============================================================================
# Speaker Follow, Bookmarks, and Direct Messages (Production Ready)
# File: app/routes/speaker_interactions.py
#
# follow_router -> mounted at /api/v1/speakers
#   GET    /me/following            speaker IDs the current user follows
#   POST   /{speaker_id}/follow     follow a speaker (safe to repeat)
#   DELETE /{speaker_id}/follow     unfollow a speaker
#   GET    /me/bookmarks            speaker IDs the current user bookmarked
#   POST   /{speaker_id}/bookmark   bookmark a speaker (safe to repeat)
#   DELETE /{speaker_id}/bookmark   remove a bookmark
#
# chat_router -> mounted at /api/v1/chat
#   GET  /inbox                              conversations for the current user
#   GET  /users/{partner_user_id}/messages   conversation with a user
#   POST /users/{partner_user_id}/messages   send a message to a user
#   GET  /speakers/{speaker_id}/messages     conversation with a speaker's account
#   POST /speakers/{speaker_id}/messages     send a message to a speaker's account
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


class SpeakerBookmark(Base):
    __tablename__ = "speaker_bookmarks"
    __table_args__ = (
        UniqueConstraint("user_id", "speaker_id", name="uq_speaker_bookmark"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
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


def _ensure_user_exists(db: DBSession, user_id: int) -> None:
    exists = db.query(User.id).filter(User.id == user_id).first()
    if exists is None:
        raise HTTPException(status_code=404, detail="User not found")


def _message_payload(m: DirectMessage) -> dict:
    return {
        "id": m.id,
        "sender_id": m.sender_id,
        "recipient_id": m.recipient_id,
        "content": m.content,
        "is_read": m.is_read,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def _speaker_display_name(speaker: Speaker) -> str:
    name = getattr(speaker, "name", None)
    if name:
        return name
    first = getattr(speaker, "first_name", "") or ""
    last = getattr(speaker, "last_name", "") or ""
    return f"{first} {last}".strip() or "Speaker"


def _send_direct_message(db: DBSession, sender_id: int, recipient_id: int, content: str) -> DirectMessage:
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
            content=content.strip(),
        )
        db.add(message)
        db.commit()
        db.refresh(message)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Failed to save message %s -> %s: %s", sender_id, recipient_id, exc)
        raise HTTPException(status_code=500, detail="Could not send your message")

    return message


def _conversation_query(db: DBSession, me: int, other: int):
    return (
        db.query(DirectMessage)
        .filter(
            or_(
                and_(DirectMessage.sender_id == me, DirectMessage.recipient_id == other),
                and_(DirectMessage.sender_id == other, DirectMessage.recipient_id == me),
            )
        )
        .order_by(DirectMessage.created_at.asc(), DirectMessage.id.asc())
    )


# ============================================================================
# Follow and Bookmark Endpoints
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
    return {"status": "success", "data": {"speaker_ids": [row[0] for row in rows]}}


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


@follow_router.get("/me/bookmarks")
def list_my_bookmarked_speakers(
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    user_id = _current_user_id(current_user)
    rows = (
        db.query(SpeakerBookmark.speaker_id)
        .filter(SpeakerBookmark.user_id == user_id)
        .all()
    )
    return {"status": "success", "data": {"speaker_ids": [row[0] for row in rows]}}


@follow_router.post("/{speaker_id}/bookmark", status_code=status.HTTP_200_OK)
def bookmark_speaker(
    speaker_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    user_id = _current_user_id(current_user)
    _get_speaker_or_404(db, speaker_id)

    already = (
        db.query(SpeakerBookmark)
        .filter(
            SpeakerBookmark.user_id == user_id,
            SpeakerBookmark.speaker_id == speaker_id,
        )
        .first()
    )
    if already:
        return {"status": "success", "bookmarked": True, "message": "Already saved"}

    try:
        db.add(SpeakerBookmark(user_id=user_id, speaker_id=speaker_id))
        db.commit()
    except IntegrityError:
        db.rollback()
        return {"status": "success", "bookmarked": True, "message": "Already saved"}
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Failed to bookmark speaker %s: %s", speaker_id, exc)
        raise HTTPException(status_code=500, detail="Could not save speaker")

    return {"status": "success", "bookmarked": True, "message": "Speaker saved"}


@follow_router.delete("/{speaker_id}/bookmark", status_code=status.HTTP_200_OK)
def remove_speaker_bookmark(
    speaker_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    user_id = _current_user_id(current_user)
    _get_speaker_or_404(db, speaker_id)

    try:
        db.query(SpeakerBookmark).filter(
            SpeakerBookmark.user_id == user_id,
            SpeakerBookmark.speaker_id == speaker_id,
        ).delete(synchronize_session=False)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Failed to remove bookmark %s: %s", speaker_id, exc)
        raise HTTPException(status_code=500, detail="Could not remove saved speaker")

    return {"status": "success", "bookmarked": False, "message": "Removed from saved"}


# ============================================================================
# Chat Endpoints
# ============================================================================

@chat_router.get("/inbox")
def list_inbox(
    limit: int = Query(50, ge=1, le=100),
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _current_user_id(current_user)

    rows = (
        db.query(DirectMessage)
        .filter(or_(DirectMessage.sender_id == me, DirectMessage.recipient_id == me))
        .order_by(DirectMessage.created_at.desc(), DirectMessage.id.desc())
        .limit(500)
        .all()
    )

    # Keep the newest message for each person you have talked with
    latest = {}
    for m in rows:
        partner = m.recipient_id if m.sender_id == me else m.sender_id
        if partner not in latest:
            latest[partner] = m
        if len(latest) >= limit:
            break

    partner_ids = list(latest.keys())
    users = {}
    speakers = {}
    if partner_ids:
        users = {u.id: u for u in db.query(User).filter(User.id.in_(partner_ids)).all()}
        speakers = {
            s.user_id: s
            for s in db.query(Speaker).filter(Speaker.user_id.in_(partner_ids)).all()
        }

    items = []
    for partner_id, m in latest.items():
        speaker = speakers.get(partner_id)
        user = users.get(partner_id)
        if speaker is not None:
            name = _speaker_display_name(speaker)
        else:
            name = getattr(user, "email", None) or "User"
        items.append({
            "partner_user_id": partner_id,
            "speaker_id": speaker.id if speaker is not None else None,
            "name": name,
            "last_message": m.content,
            "last_sender_id": m.sender_id,
            "last_at": m.created_at.isoformat() if m.created_at else None,
        })

    return {"status": "success", "data": items}


@chat_router.get("/users/{partner_user_id}/messages")
def list_user_conversation(
    partner_user_id: int,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _current_user_id(current_user)
    _ensure_user_exists(db, partner_user_id)

    rows = _conversation_query(db, me, partner_user_id).offset(offset).limit(limit).all()
    return {"status": "success", "data": [_message_payload(m) for m in rows]}


@chat_router.post("/users/{partner_user_id}/messages", status_code=status.HTTP_201_CREATED)
def send_message_to_user(
    partner_user_id: int,
    payload: MessageCreate,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _current_user_id(current_user)
    _ensure_user_exists(db, partner_user_id)

    message = _send_direct_message(db, me, partner_user_id, payload.content)
    return {
        "status": "success",
        "message": "Message sent",
        "data": _message_payload(message),
    }


@chat_router.get("/speakers/{speaker_id}/messages")
def list_speaker_conversation(
    speaker_id: int,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _current_user_id(current_user)
    speaker = _get_speaker_or_404(db, speaker_id)

    rows = _conversation_query(db, me, speaker.user_id).offset(offset).limit(limit).all()
    return {"status": "success", "data": [_message_payload(m) for m in rows]}


@chat_router.post("/speakers/{speaker_id}/messages", status_code=status.HTTP_201_CREATED)
def send_message_to_speaker(
    speaker_id: int,
    payload: MessageCreate,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _current_user_id(current_user)
    speaker = _get_speaker_or_404(db, speaker_id)

    message = _send_direct_message(db, me, speaker.user_id, payload.content)
    return {
        "status": "success",
        "message": "Message sent",
        "data": _message_payload(message),
    }