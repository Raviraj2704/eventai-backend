# ============================================================================
# Session Hub (Production Ready)
# File: app/routes/session_hub.py
# Mounted at /api/v1/session-hub
#
# Browse:     GET  /days, /tracks, /sessions, /sessions/{id}
#             GET  /me/schedule, /me/bookmarks
# Personal:   POST/DELETE /sessions/{id}/schedule
#             POST/DELETE /sessions/{id}/bookmark
#             POST        /sessions/{id}/check-in
# Engagement: POST        /sessions/{id}/reactions
#             DELETE      /sessions/{id}/reactions/{kind}
#             GET/POST    /sessions/{id}/questions
#             POST        /sessions/{id}/feedback
# Live:       GET         /sessions/{id}/stream
# Organizer:  PUT         /sessions/{id}/details
#             POST        /sessions/{id}/live
# ============================================================================

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, String,
    UniqueConstraint, func, or_,
)
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.models import Base, Session as SessionModel, Speaker, User
from app.routes.auth import get_current_user
from app.routes.session_interactions import SessionFeedback, SessionQuestion

logger = logging.getLogger(__name__)
router = APIRouter()

REACTION_KINDS = ("like", "clap", "announce")


# ============================================================================
# Database models
# ============================================================================

class SessionExtras(Base):
    __tablename__ = "session_extras"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        Integer,
        ForeignKey(f"{SessionModel.__tablename__}.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    track = Column(String(100), nullable=True, index=True)
    tags = Column(String(255), nullable=True)
    image_url = Column(String(500), nullable=True)
    is_live = Column(Boolean, nullable=False, default=False)
    stream_url = Column(String(500), nullable=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class SessionSchedule(Base):
    __tablename__ = "session_schedule"
    __table_args__ = (
        UniqueConstraint("user_id", "session_id", name="uq_session_schedule"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey(f"{User.__tablename__}.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id = Column(
        Integer,
        ForeignKey(f"{SessionModel.__tablename__}.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    checked_in_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class SessionBookmark(Base):
    __tablename__ = "session_bookmarks"
    __table_args__ = (
        UniqueConstraint("user_id", "session_id", name="uq_session_bookmark"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey(f"{User.__tablename__}.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id = Column(
        Integer,
        ForeignKey(f"{SessionModel.__tablename__}.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class SessionReaction(Base):
    __tablename__ = "session_reactions"
    __table_args__ = (
        UniqueConstraint("user_id", "session_id", "kind", name="uq_session_reaction"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey(f"{User.__tablename__}.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id = Column(
        Integer,
        ForeignKey(f"{SessionModel.__tablename__}.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind = Column(String(20), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


# ============================================================================
# Schemas
# ============================================================================

class QuestionCreate(BaseModel):
    content: str = Field(..., min_length=3, max_length=1000)


class FeedbackCreate(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    content: Optional[str] = Field(default=None, max_length=2000)


class ReactionCreate(BaseModel):
    kind: str = Field(..., pattern="^(like|clap|announce)$")


class LiveUpdate(BaseModel):
    is_live: bool
    stream_url: Optional[str] = Field(default=None, max_length=500)


class DetailsUpdate(BaseModel):
    track: Optional[str] = Field(default=None, max_length=100)
    tags: Optional[List[str]] = None
    image_url: Optional[str] = Field(default=None, max_length=500)


# ============================================================================
# Helpers
# ============================================================================

def _naive(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _iso(value: Optional[datetime]) -> Optional[str]:
    value = _naive(value)
    return value.isoformat() if value else None


def _current_user_id(current_user: Any) -> int:
    user_id = getattr(current_user, "id", None)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid user session")
    return user_id


def _require_admin(current_user: Any) -> None:
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Only organizers can do this")


def _get_session_or_404(db: DBSession, session_id: int) -> SessionModel:
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def _get_extras(db: DBSession, session_id: int) -> Optional[SessionExtras]:
    return db.query(SessionExtras).filter(SessionExtras.session_id == session_id).first()


def _get_or_create_extras(db: DBSession, session_id: int) -> SessionExtras:
    extras = _get_extras(db, session_id)
    if extras is None:
        extras = SessionExtras(session_id=session_id, is_live=False)
        db.add(extras)
    return extras


def _day_label(day) -> str:
    n = day.day
    if 11 <= n % 100 <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix} {day.strftime('%b')}"


def _time_label(start: Optional[datetime], end: Optional[datetime]) -> str:
    start = _naive(start)
    end = _naive(end)
    if start is None:
        return ""
    label = start.strftime("%I:%M %p")
    if end is not None:
        label += f" - {end.strftime('%I:%M %p')}"
    return label


def _status_of(is_live: bool, end: Optional[datetime], now: datetime) -> str:
    if is_live:
        return "live"
    end = _naive(end)
    if end is not None and end < now:
        return "ended"
    return "upcoming"


def _speaker_names(db: DBSession, speaker_ids: List[Optional[int]]) -> Dict[int, str]:
    ids = {i for i in speaker_ids if i}
    if not ids:
        return {}
    names: Dict[int, str] = {}
    for sp in db.query(Speaker).filter(Speaker.id.in_(ids)).all():
        name = getattr(sp, "name", None)
        if not name:
            first = getattr(sp, "first_name", "") or ""
            last = getattr(sp, "last_name", "") or ""
            name = f"{first} {last}".strip() or "Speaker"
        names[sp.id] = name
    return names


def _build_items(db: DBSession, sessions: List[SessionModel], me_id: Optional[int], now: datetime) -> List[dict]:
    if not sessions:
        return []

    ids = [s.id for s in sessions]
    extras_map = {
        e.session_id: e
        for e in db.query(SessionExtras).filter(SessionExtras.session_id.in_(ids)).all()
    }

    scheduled = set()
    bookmarked = set()
    if me_id is not None:
        scheduled = {
            r[0] for r in db.query(SessionSchedule.session_id).filter(
                SessionSchedule.user_id == me_id,
                SessionSchedule.session_id.in_(ids),
            ).all()
        }
        bookmarked = {
            r[0] for r in db.query(SessionBookmark.session_id).filter(
                SessionBookmark.user_id == me_id,
                SessionBookmark.session_id.in_(ids),
            ).all()
        }

    counts: Dict[int, int] = {}
    avatars: Dict[int, List[str]] = {}
    attendee_rows = (
        db.query(SessionSchedule.session_id, User.avatar_url)
        .join(User, User.id == SessionSchedule.user_id)
        .filter(SessionSchedule.session_id.in_(ids))
        .order_by(SessionSchedule.created_at.asc(), SessionSchedule.id.asc())
        .all()
    )
    for session_id, avatar_url in attendee_rows:
        counts[session_id] = counts.get(session_id, 0) + 1
        bucket = avatars.setdefault(session_id, [])
        if avatar_url and len(bucket) < 4:
            bucket.append(avatar_url)

    speaker_names = _speaker_names(db, [getattr(s, "speaker_id", None) for s in sessions])

    items = []
    for s in sessions:
        extras = extras_map.get(s.id)
        is_live = bool(extras.is_live) if extras else False
        tags: List[str] = []
        if extras and extras.tags:
            tags = [t.strip() for t in extras.tags.split(",") if t.strip()]
        start = _naive(s.start_time)
        speaker_id = getattr(s, "speaker_id", None)

        items.append({
            "id": s.id,
            "title": s.title,
            "description": s.description or "",
            "location": s.location or "",
            "start_time": _iso(s.start_time),
            "end_time": _iso(s.end_time),
            "date": start.date().isoformat() if start else None,
            "time_label": _time_label(s.start_time, s.end_time),
            "track": extras.track if extras and extras.track else "General",
            "tags": tags,
            "image_url": extras.image_url if extras else None,
            "is_live": is_live,
            "status": _status_of(is_live, s.end_time, now),
            "speaker_id": speaker_id,
            "speaker_name": speaker_names.get(speaker_id),
            "is_scheduled": s.id in scheduled,
            "is_bookmarked": s.id in bookmarked,
            "attendee_count": counts.get(s.id, 0),
            "attendee_avatars": avatars.get(s.id, []),
        })
    return items


def _reaction_state(db: DBSession, session_id: int, me_id: int) -> Dict[str, Any]:
    counts = {kind: 0 for kind in REACTION_KINDS}
    rows = (
        db.query(SessionReaction.kind, func.count(SessionReaction.id))
        .filter(SessionReaction.session_id == session_id)
        .group_by(SessionReaction.kind)
        .all()
    )
    for kind, total in rows:
        if kind in counts:
            counts[kind] = int(total)
    mine = [
        r[0] for r in db.query(SessionReaction.kind).filter(
            SessionReaction.session_id == session_id,
            SessionReaction.user_id == me_id,
        ).all()
    ]
    return {"reactions": counts, "my_reactions": mine}


def _commit_or_500(db: DBSession, action: str, detail: str) -> None:
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("%s failed: %s", action, exc)
        raise HTTPException(status_code=500, detail=detail)


# ============================================================================
# Browse
# ============================================================================

@router.get("/days")
def list_days(
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    _current_user_id(current_user)
    rows = (
        db.query(SessionModel.start_time)
        .filter(SessionModel.start_time.isnot(None))
        .order_by(SessionModel.start_time.asc())
        .all()
    )
    days = []
    for (start,) in rows:
        day = _naive(start).date()
        if day not in days:
            days.append(day)
    return {
        "status": "success",
        "data": [
            {"date": d.isoformat(), "label": _day_label(d), "day_number": index + 1}
            for index, d in enumerate(days)
        ],
    }


@router.get("/tracks")
def list_tracks(
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    _current_user_id(current_user)
    rows = (
        db.query(SessionExtras.track)
        .filter(SessionExtras.track.isnot(None))
        .distinct()
        .all()
    )
    tracks = sorted({r[0].strip() for r in rows if r[0] and r[0].strip()})
    return {"status": "success", "data": tracks}


@router.get("/sessions")
def browse_sessions(
    day: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    track: Optional[str] = Query(None, max_length=100),
    status_filter: str = Query("all", alias="status", pattern="^(all|live|upcoming|ended)$"),
    live_only: bool = Query(False),
    q: Optional[str] = Query(None, max_length=100),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _current_user_id(current_user)
    now = datetime.utcnow()

    query = db.query(SessionModel).outerjoin(
        SessionExtras, SessionExtras.session_id == SessionModel.id
    )

    if day:
        try:
            day_start = datetime.strptime(day, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Use the date format YYYY-MM-DD")
        query = query.filter(
            SessionModel.start_time >= day_start,
            SessionModel.start_time < day_start + timedelta(days=1),
        )

    if track:
        query = query.filter(SessionExtras.track == track)

    if live_only or status_filter == "live":
        query = query.filter(SessionExtras.is_live.is_(True))
    elif status_filter == "upcoming":
        query = query.filter(
            SessionExtras.is_live.isnot(True),
            SessionModel.start_time > now,
        )
    elif status_filter == "ended":
        query = query.filter(
            SessionExtras.is_live.isnot(True),
            SessionModel.end_time < now,
        )

    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(
            or_(
                SessionModel.title.ilike(term),
                SessionModel.description.ilike(term),
                SessionModel.location.ilike(term),
            )
        )

    total = query.count()
    rows = (
        query.order_by(SessionModel.start_time.asc(), SessionModel.id.asc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    return {
        "status": "success",
        "total": total,
        "page": page,
        "limit": limit,
        "has_next": page * limit < total,
        "data": _build_items(db, rows, me, now),
    }


@router.get("/sessions/{session_id}")
def get_session_detail(
    session_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _current_user_id(current_user)
    now = datetime.utcnow()
    session = _get_session_or_404(db, session_id)

    item = _build_items(db, [session], me, now)[0]

    speaker_id = getattr(session, "speaker_id", None)
    names = _speaker_names(db, [speaker_id])
    speakers = [{"id": speaker_id, "name": names[speaker_id]}] if speaker_id in names else []

    checked = db.query(SessionSchedule.checked_in_at).filter(
        SessionSchedule.user_id == me,
        SessionSchedule.session_id == session_id,
    ).first()

    state = _reaction_state(db, session_id, me)
    item.update({
        "speakers": speakers,
        "reactions": state["reactions"],
        "my_reactions": state["my_reactions"],
        "is_checked_in": bool(checked and checked[0]),
        "has_stream": bool(item["is_live"]),
    })
    return {"status": "success", "data": item}


@router.get("/me/schedule")
def my_schedule(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _current_user_id(current_user)
    now = datetime.utcnow()
    query = (
        db.query(SessionModel)
        .join(SessionSchedule, SessionSchedule.session_id == SessionModel.id)
        .filter(SessionSchedule.user_id == me)
    )
    total = query.count()
    rows = (
        query.order_by(SessionModel.start_time.asc(), SessionModel.id.asc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    return {
        "status": "success",
        "total": total,
        "page": page,
        "limit": limit,
        "data": _build_items(db, rows, me, now),
    }


@router.get("/me/bookmarks")
def my_bookmarks(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _current_user_id(current_user)
    now = datetime.utcnow()
    query = (
        db.query(SessionModel)
        .join(SessionBookmark, SessionBookmark.session_id == SessionModel.id)
        .filter(SessionBookmark.user_id == me)
    )
    total = query.count()
    rows = (
        query.order_by(SessionModel.start_time.asc(), SessionModel.id.asc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    return {
        "status": "success",
        "total": total,
        "page": page,
        "limit": limit,
        "data": _build_items(db, rows, me, now),
    }


# ============================================================================
# Schedule, bookmarks, check-in
# ============================================================================

@router.post("/sessions/{session_id}/schedule")
def add_to_schedule(
    session_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _current_user_id(current_user)
    _get_session_or_404(db, session_id)

    exists = db.query(SessionSchedule.id).filter(
        SessionSchedule.user_id == me,
        SessionSchedule.session_id == session_id,
    ).first()

    if exists is None:
        try:
            db.add(SessionSchedule(user_id=me, session_id=session_id))
            db.commit()
        except IntegrityError:
            db.rollback()
        except SQLAlchemyError as exc:
            db.rollback()
            logger.error("Add to schedule failed: %s", exc)
            raise HTTPException(status_code=500, detail="Could not add this session")

    return {
        "status": "success",
        "message": "Added to your schedule",
        "data": {"is_scheduled": True},
    }


@router.delete("/sessions/{session_id}/schedule")
def remove_from_schedule(
    session_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _current_user_id(current_user)
    _get_session_or_404(db, session_id)

    try:
        db.query(SessionSchedule).filter(
            SessionSchedule.user_id == me,
            SessionSchedule.session_id == session_id,
        ).delete(synchronize_session=False)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Remove from schedule failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not remove this session")

    return {
        "status": "success",
        "message": "Removed from your schedule",
        "data": {"is_scheduled": False},
    }


@router.post("/sessions/{session_id}/bookmark")
def add_bookmark(
    session_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _current_user_id(current_user)
    _get_session_or_404(db, session_id)

    exists = db.query(SessionBookmark.id).filter(
        SessionBookmark.user_id == me,
        SessionBookmark.session_id == session_id,
    ).first()

    if exists is None:
        try:
            db.add(SessionBookmark(user_id=me, session_id=session_id))
            db.commit()
        except IntegrityError:
            db.rollback()
        except SQLAlchemyError as exc:
            db.rollback()
            logger.error("Bookmark failed: %s", exc)
            raise HTTPException(status_code=500, detail="Could not save this session")

    return {
        "status": "success",
        "message": "Saved",
        "data": {"is_bookmarked": True},
    }


@router.delete("/sessions/{session_id}/bookmark")
def remove_bookmark(
    session_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _current_user_id(current_user)
    _get_session_or_404(db, session_id)

    try:
        db.query(SessionBookmark).filter(
            SessionBookmark.user_id == me,
            SessionBookmark.session_id == session_id,
        ).delete(synchronize_session=False)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Remove bookmark failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not remove this session")

    return {
        "status": "success",
        "message": "Removed from saved",
        "data": {"is_bookmarked": False},
    }


@router.post("/sessions/{session_id}/check-in")
def check_in(
    session_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _current_user_id(current_user)
    _get_session_or_404(db, session_id)

    row = db.query(SessionSchedule).filter(
        SessionSchedule.user_id == me,
        SessionSchedule.session_id == session_id,
    ).first()
    if row is None:
        raise HTTPException(
            status_code=400,
            detail="Add this session to your schedule before checking in",
        )

    if row.checked_in_at is None:
        row.checked_in_at = datetime.utcnow()
        _commit_or_500(db, "Check in", "Could not check you in")

    return {
        "status": "success",
        "message": "Checked in",
        "data": {"is_checked_in": True, "checked_in_at": _iso(row.checked_in_at)},
    }


# ============================================================================
# Reactions
# ============================================================================

@router.post("/sessions/{session_id}/reactions")
def add_reaction(
    session_id: int,
    payload: ReactionCreate,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _current_user_id(current_user)
    _get_session_or_404(db, session_id)

    exists = db.query(SessionReaction.id).filter(
        SessionReaction.user_id == me,
        SessionReaction.session_id == session_id,
        SessionReaction.kind == payload.kind,
    ).first()

    if exists is None:
        try:
            db.add(SessionReaction(user_id=me, session_id=session_id, kind=payload.kind))
            db.commit()
        except IntegrityError:
            db.rollback()
        except SQLAlchemyError as exc:
            db.rollback()
            logger.error("Add reaction failed: %s", exc)
            raise HTTPException(status_code=500, detail="Could not save your reaction")

    return {"status": "success", "data": _reaction_state(db, session_id, me)}


@router.delete("/sessions/{session_id}/reactions/{kind}")
def remove_reaction(
    session_id: int,
    kind: str,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _current_user_id(current_user)
    if kind not in REACTION_KINDS:
        raise HTTPException(status_code=400, detail="Unknown reaction")
    _get_session_or_404(db, session_id)

    try:
        db.query(SessionReaction).filter(
            SessionReaction.user_id == me,
            SessionReaction.session_id == session_id,
            SessionReaction.kind == kind,
        ).delete(synchronize_session=False)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Remove reaction failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not remove your reaction")

    return {"status": "success", "data": _reaction_state(db, session_id, me)}


# ============================================================================
# Questions and feedback
# ============================================================================

@router.get("/sessions/{session_id}/questions")
def list_questions(
    session_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    _current_user_id(current_user)
    _get_session_or_404(db, session_id)

    rows = (
        db.query(SessionQuestion)
        .filter(SessionQuestion.session_id == session_id)
        .order_by(SessionQuestion.created_at.desc(), SessionQuestion.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    return {
        "status": "success",
        "data": [
            {
                "id": q.id,
                "content": q.content,
                "is_answered": bool(q.is_answered),
                "created_at": _iso(q.created_at),
            }
            for q in rows
        ],
    }


@router.post("/sessions/{session_id}/questions", status_code=status.HTTP_201_CREATED)
def ask_question(
    session_id: int,
    payload: QuestionCreate,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _current_user_id(current_user)
    _get_session_or_404(db, session_id)

    question = SessionQuestion(
        session_id=session_id,
        user_id=me,
        content=payload.content.strip(),
    )
    db.add(question)
    _commit_or_500(db, "Ask question", "Could not send your question")
    db.refresh(question)

    return {
        "status": "success",
        "message": "Your question has been sent",
        "data": {"id": question.id, "content": question.content},
    }


@router.post("/sessions/{session_id}/feedback", status_code=status.HTTP_201_CREATED)
def submit_feedback(
    session_id: int,
    payload: FeedbackCreate,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _current_user_id(current_user)
    _get_session_or_404(db, session_id)
    text = (payload.content or "").strip()

    existing = db.query(SessionFeedback).filter(
        SessionFeedback.session_id == session_id,
        SessionFeedback.user_id == me,
    ).first()

    if existing is not None:
        existing.rating = payload.rating
        existing.content = text or existing.content or ""
        record = existing
    else:
        record = SessionFeedback(
            session_id=session_id,
            user_id=me,
            rating=payload.rating,
            content=text,
        )
        db.add(record)

    _commit_or_500(db, "Submit feedback", "Could not save your feedback")
    db.refresh(record)

    return {
        "status": "success",
        "message": "Your feedback has been submitted",
        "data": {"id": record.id, "rating": record.rating},
    }


# ============================================================================
# Live stream (Watch)
# ============================================================================

@router.get("/sessions/{session_id}/stream")
def get_stream(
    session_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    _current_user_id(current_user)
    _get_session_or_404(db, session_id)

    extras = _get_extras(db, session_id)
    if extras is None or not extras.is_live or not extras.stream_url:
        raise HTTPException(status_code=403, detail="This session is not live right now")

    return {"status": "success", "data": {"stream_url": extras.stream_url}}


# ============================================================================
# Organizer controls
# ============================================================================

@router.put("/sessions/{session_id}/details")
def update_details(
    session_id: int,
    payload: DetailsUpdate,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    _require_admin(current_user)
    _get_session_or_404(db, session_id)

    extras = _get_or_create_extras(db, session_id)
    if payload.track is not None:
        extras.track = payload.track.strip() or None
    if payload.tags is not None:
        cleaned = ",".join(t.strip() for t in payload.tags if t.strip())
        extras.tags = cleaned[:255] or None
    if payload.image_url is not None:
        extras.image_url = payload.image_url.strip() or None
    extras.updated_at = datetime.utcnow()

    _commit_or_500(db, "Update session details", "Could not save the session details")
    return {"status": "success", "message": "Session details saved"}


@router.post("/sessions/{session_id}/live")
def set_live(
    session_id: int,
    payload: LiveUpdate,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    _require_admin(current_user)
    _get_session_or_404(db, session_id)

    extras = _get_or_create_extras(db, session_id)
    if payload.stream_url is not None:
        extras.stream_url = payload.stream_url.strip() or None

    if payload.is_live and not extras.stream_url:
        db.rollback()
        raise HTTPException(status_code=400, detail="Add a stream link before going live")

    extras.is_live = payload.is_live
    extras.updated_at = datetime.utcnow()
    _commit_or_500(db, "Set live", "Could not update the live status")

    return {
        "status": "success",
        "message": "Live status updated",
        "data": {"is_live": bool(extras.is_live)},
    }