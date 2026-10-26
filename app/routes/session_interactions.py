# ============================================================================
# Session Interactions - Questions & Feedback (Production Ready)
# File: app/routes/session_interactions.py
#
# Endpoints (mounted at /api/v1/sessions in main.py):
#   POST /{session_id}/questions  -> ask a question about a session
#   GET  /{session_id}/questions  -> list questions for a session
#   POST /{session_id}/feedback   -> submit feedback for a session
# ============================================================================

import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.models import Base, Session as SessionModel, User
from app.routes.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# Database Models
# ============================================================================

class SessionQuestion(Base):
    __tablename__ = "session_questions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        Integer,
        ForeignKey(f"{SessionModel.__tablename__}.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        Integer,
        ForeignKey(f"{User.__tablename__}.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    content = Column(Text, nullable=False)
    is_answered = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class SessionFeedback(Base):
    __tablename__ = "session_feedback"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        Integer,
        ForeignKey(f"{SessionModel.__tablename__}.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        Integer,
        ForeignKey(f"{User.__tablename__}.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    rating = Column(Integer, nullable=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


# ============================================================================
# Request Schemas
# ============================================================================

class QuestionCreate(BaseModel):
    content: str = Field(..., min_length=3, max_length=1000)


class FeedbackCreate(BaseModel):
    content: str = Field(..., min_length=3, max_length=2000)
    rating: Optional[int] = Field(default=None, ge=1, le=5)


# ============================================================================
# Helpers
# ============================================================================

def _get_user_id(current_user: Any) -> int:
    user_id = getattr(current_user, "id", None)
    if user_id is None and isinstance(current_user, dict):
        user_id = current_user.get("id")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid user session")
    return user_id


def _ensure_session_exists(db: DBSession, session_id: int) -> None:
    exists = db.query(SessionModel.id).filter(SessionModel.id == session_id).first()
    if not exists:
        raise HTTPException(status_code=404, detail="Session not found")


def _question_payload(q: SessionQuestion) -> dict:
    return {
        "id": q.id,
        "session_id": q.session_id,
        "user_id": q.user_id,
        "content": q.content,
        "is_answered": q.is_answered,
        "created_at": q.created_at.isoformat() if q.created_at else None,
    }


def _feedback_payload(f: SessionFeedback) -> dict:
    return {
        "id": f.id,
        "session_id": f.session_id,
        "user_id": f.user_id,
        "rating": f.rating,
        "content": f.content,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/{session_id}/questions", status_code=status.HTTP_201_CREATED)
def ask_session_question(
    session_id: int,
    payload: QuestionCreate,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    _ensure_session_exists(db, session_id)
    user_id = _get_user_id(current_user)

    try:
        question = SessionQuestion(
            session_id=session_id,
            user_id=user_id,
            content=payload.content.strip(),
        )
        db.add(question)
        db.commit()
        db.refresh(question)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Failed to save question for session %s: %s", session_id, exc)
        raise HTTPException(status_code=500, detail="Could not save your question")

    return {
        "status": "success",
        "message": "Your question was submitted successfully",
        "data": _question_payload(question),
    }


@router.get("/{session_id}/questions")
def list_session_questions(
    session_id: int,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    _ensure_session_exists(db, session_id)

    rows = (
        db.query(SessionQuestion)
        .filter(SessionQuestion.session_id == session_id)
        .order_by(SessionQuestion.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "status": "success",
        "data": [_question_payload(q) for q in rows],
    }


@router.post("/{session_id}/feedback", status_code=status.HTTP_201_CREATED)
def submit_session_feedback(
    session_id: int,
    payload: FeedbackCreate,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    _ensure_session_exists(db, session_id)
    user_id = _get_user_id(current_user)

    try:
        feedback = SessionFeedback(
            session_id=session_id,
            user_id=user_id,
            rating=payload.rating,
            content=payload.content.strip(),
        )
        db.add(feedback)
        db.commit()
        db.refresh(feedback)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Failed to save feedback for session %s: %s", session_id, exc)
        raise HTTPException(status_code=500, detail="Could not save your feedback")

    return {
        "status": "success",
        "message": "Your feedback submitted successfully",
        "data": _feedback_payload(feedback),
    }