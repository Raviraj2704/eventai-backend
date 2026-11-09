# ============================================================================
# Favourites (sessions and speakers you bookmarked)
# File: app/routes/favourites.py
# Mounted at /api/v1/favourites
#
# GET    /                       both lists in one response
# DELETE /sessions/{session_id}  remove a bookmarked session
# DELETE /speakers/{speaker_id}  remove a bookmarked speaker
# ============================================================================

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.models import Session as SessionModel, Speaker, User
from app.routes.auth import get_current_user
from app.routes.session_hub import SessionBookmark
from app.routes.speaker_interactions import SpeakerBookmark

logger = logging.getLogger(__name__)
router = APIRouter()

HIDDEN_SESSION_STATES = ("deleted", "draft", "proposed", "rejected")


def _me(current_user: Any) -> int:
    user_id = getattr(current_user, "id", None)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid user session")
    return user_id


def _full_name(user: User) -> str:
    return f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username or "Speaker"


@router.get("/")
def list_favourites(
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _me(current_user)

    # Sessions you bookmarked that are still published
    session_rows = (
        db.query(SessionModel)
        .join(SessionBookmark, SessionBookmark.session_id == SessionModel.id)
        .filter(
            SessionBookmark.user_id == me,
            SessionModel.status.notin_(HIDDEN_SESSION_STATES),
        )
        .order_by(SessionModel.start_time.asc())
        .all()
    )
    sessions = [
        {
            "id": s.id,
            "title": s.title,
            "start_time": s.start_time.isoformat() if s.start_time else None,
            "end_time": s.end_time.isoformat() if s.end_time else None,
            "location": s.location or "",
        }
        for s in session_rows
    ]

    # Speakers you bookmarked
    speaker_rows = (
        db.query(Speaker, User)
        .join(SpeakerBookmark, SpeakerBookmark.speaker_id == Speaker.id)
        .join(User, User.id == Speaker.user_id)
        .filter(SpeakerBookmark.user_id == me)
        .all()
    )
    speakers = [
        {
            "id": speaker.id,
            "user_id": user.id,
            "name": _full_name(user),
            "avatar_url": user.avatar_url,
            "job_title": user.job_title,
            "company": user.company,
        }
        for speaker, user in speaker_rows
    ]

    return {
        "status": "success",
        "data": {"sessions": sessions, "speakers": speakers},
    }


@router.delete("/sessions/{session_id}")
def remove_session_favourite(
    session_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _me(current_user)
    row = (
        db.query(SessionBookmark)
        .filter(SessionBookmark.user_id == me, SessionBookmark.session_id == session_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="This session is not in your favourites")

    try:
        db.delete(row)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Remove session favourite failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not remove this favourite")

    return {"status": "success", "message": "Removed from favourites"}


@router.delete("/speakers/{speaker_id}")
def remove_speaker_favourite(
    speaker_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _me(current_user)
    row = (
        db.query(SpeakerBookmark)
        .filter(SpeakerBookmark.user_id == me, SpeakerBookmark.speaker_id == speaker_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="This speaker is not in your favourites")

    try:
        db.delete(row)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Remove speaker favourite failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not remove this favourite")

    return {"status": "success", "message": "Removed from favourites"}