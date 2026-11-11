# ============================================================================
# 1-2-1 Meetings
# File: app/routes/meetings.py
# Mounted at /api/v1/meetings
#
# GET    /?tab=confirmed|invites&filter=...   my meetings (list)
# GET    /{id}                                one meeting (participants only)
# POST   /requests/{user_id}                  request a 1-2-1
# PUT    /{id}                                edit a pending request (requester)
# DELETE /{id}                                withdraw / decline / remove from my list
# POST   /{id}/accept                         accept a request or a reschedule
# POST   /{id}/reject                         reject a request or a reschedule
# POST   /{id}/reschedule                     propose a new time (409 if busy)
# POST   /{id}/cancel                         cancel an active meeting
# POST   /{id}/status                         completed | no_show, after end time
# ============================================================================

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, and_, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.models import Base, User
from app.routes.auth import get_current_user
from app.routes.blocks import is_blocked_between

logger = logging.getLogger(__name__)
router = APIRouter()

PENDING = "pending"
CONFIRMED = "confirmed"
RESCHEDULE = "reschedule_requested"
REJECTED = "rejected"
CANCELLED = "cancelled"
COMPLETED = "completed"
NO_SHOW = "no_show"

ACTIVE = (PENDING, CONFIRMED, RESCHEDULE)
OUTCOME = (COMPLETED, NO_SHOW)
CLOSED = (REJECTED, CANCELLED)


# ============================================================================
# Database model (run the ALTER TABLE statements first)
# ============================================================================

class Meeting(Base):
    __tablename__ = "meetings"

    id = Column(Integer, primary_key=True, index=True)
    requester_id = Column(Integer, ForeignKey(f"{User.__tablename__}.id", ondelete="CASCADE"), nullable=False, index=True)
    receiver_id = Column(Integer, ForeignKey(f"{User.__tablename__}.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    note = Column(Text, nullable=True)
    location = Column(String(255), nullable=True)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    status = Column(String(30), nullable=False, default=PENDING, index=True)
    proposed_start = Column(DateTime, nullable=True)
    proposed_end = Column(DateTime, nullable=True)
    proposed_note = Column(Text, nullable=True)
    proposed_by = Column(Integer, nullable=True)
    requester_hidden = Column(Boolean, nullable=False, default=False)
    receiver_hidden = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


# ============================================================================
# Schemas (all times are stored as naive UTC)
# ============================================================================

def _naive_utc(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


class MeetingCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    note: Optional[str] = Field(None, max_length=1000)
    location: Optional[str] = Field(None, max_length=255)
    start_time: datetime
    end_time: datetime

    @model_validator(mode="after")
    def _normalise(self):
        self.start_time = _naive_utc(self.start_time)
        self.end_time = _naive_utc(self.end_time)
        if self.end_time <= self.start_time:
            raise ValueError("End time must be after start time")
        return self


class MeetingUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=200)
    note: Optional[str] = Field(None, max_length=1000)
    location: Optional[str] = Field(None, max_length=255)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    @model_validator(mode="after")
    def _normalise(self):
        if self.start_time is not None:
            self.start_time = _naive_utc(self.start_time)
        if self.end_time is not None:
            self.end_time = _naive_utc(self.end_time)
        return self


class TimeProposal(BaseModel):
    start_time: datetime
    end_time: datetime
    note: Optional[str] = Field(None, max_length=1000)

    @model_validator(mode="after")
    def _normalise(self):
        self.start_time = _naive_utc(self.start_time)
        self.end_time = _naive_utc(self.end_time)
        if self.end_time <= self.start_time:
            raise ValueError("End time must be after start time")
        return self


class StatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(completed|no_show)$")


# ============================================================================
# Helpers
# ============================================================================

def _now() -> datetime:
    return datetime.utcnow()


def _iso(dt: Optional[datetime]) -> Optional[str]:
    # Trailing Z tells the browser these are UTC, so local times display correctly
    return dt.isoformat() + "Z" if dt else None


def _me(current_user: Any) -> int:
    user_id = getattr(current_user, "id", None)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid user session")
    return user_id


def _get_mine(db: DBSession, meeting_id: int, me: int) -> Meeting:
    row = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if row is None or me not in (row.requester_id, row.receiver_id):
        raise HTTPException(status_code=404, detail="Meeting not found")
    return row


def _other_id(row: Meeting, me: int) -> int:
    return row.receiver_id if row.requester_id == me else row.requester_id


def _visible(query, me: int):
    """Hide meetings a person has removed from their own list."""
    return query.filter(or_(
        and_(Meeting.requester_id == me, Meeting.requester_hidden.is_(False)),
        and_(Meeting.receiver_id == me, Meeting.receiver_hidden.is_(False)),
    ))


def _load_users(db: DBSession, ids) -> dict:
    ids = list(ids)
    if not ids:
        return {}
    return {u.id: u for u in db.query(User).filter(User.id.in_(ids)).all()}


def _person(user: Optional[User]) -> Optional[dict]:
    if user is None:
        return None
    name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username or "Attendee"
    return {
        "user_id": user.id,
        "name": name,
        "avatar_url": user.avatar_url,
        "job_title": user.job_title,
        "company": user.company,
    }


def _serialize(row: Meeting, me: int, users: dict) -> dict:
    proposed_by_me = row.proposed_by == me
    if row.status == PENDING:
        can_respond = row.receiver_id == me
    elif row.status == RESCHEDULE:
        can_respond = not proposed_by_me
    else:
        can_respond = False

    return {
        "id": row.id,
        "title": row.title,
        "note": row.note or "",
        "location": row.location or "",
        "start_time": _iso(row.start_time),
        "end_time": _iso(row.end_time),
        "status": row.status,
        "is_ended": row.end_time <= _now(),
        "is_requester": row.requester_id == me,
        "proposed_start": _iso(row.proposed_start),
        "proposed_end": _iso(row.proposed_end),
        "proposed_note": row.proposed_note or "",
        "proposed_by_me": proposed_by_me,
        "can_respond": can_respond,
        "created_at": _iso(row.created_at),
        "other": _person(users.get(_other_id(row, me))),
    }


def _clear_proposal(row: Meeting) -> None:
    row.proposed_start = None
    row.proposed_end = None
    row.proposed_note = None
    row.proposed_by = None


def _commit(db: DBSession, action: str, detail: str) -> None:
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("%s failed: %s", action, exc)
        raise HTTPException(status_code=500, detail=detail)


def _ensure_not_blocked(db: DBSession, me: int, other: int) -> None:
    if is_blocked_between(db, me, other):
        raise HTTPException(status_code=403, detail="You cannot schedule a meeting with this person")


def _require_future(start: datetime) -> None:
    if start < _now() - timedelta(minutes=5):
        raise HTTPException(status_code=400, detail="Choose a time in the future")


def _assert_free(db: DBSession, people: list, start: datetime, end: datetime, exclude_id: Optional[int] = None) -> None:
    """Confirmed meetings block the time for both people."""
    q = db.query(Meeting).filter(
        Meeting.status == CONFIRMED,
        Meeting.start_time < end,
        Meeting.end_time > start,
        or_(Meeting.requester_id.in_(people), Meeting.receiver_id.in_(people)),
    )
    if exclude_id is not None:
        q = q.filter(Meeting.id != exclude_id)
    if q.first() is not None:
        raise HTTPException(status_code=409, detail="That time is not available for one of you")


# ============================================================================
# Lists and detail
# ============================================================================

@router.get("/")
def list_meetings(
    tab: str = Query("confirmed", pattern="^(confirmed|invites)$"),
    filter: str = Query("all", pattern="^(all|upcoming|ended|sent|cancelled|invitation|reschedule)$"),
    limit: int = Query(100, ge=1, le=200),
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _me(current_user)
    now = _now()
    q = _visible(db.query(Meeting), me)

    if tab == "invites":
        if filter == "reschedule":
            q = q.filter(Meeting.status == RESCHEDULE, Meeting.proposed_by != me)
        elif filter == "invitation":
            q = q.filter(Meeting.status == PENDING, Meeting.receiver_id == me)
        else:
            q = q.filter(or_(
                and_(Meeting.status == PENDING, Meeting.receiver_id == me),
                and_(Meeting.status == RESCHEDULE, Meeting.proposed_by != me),
            ))
    else:
        if filter == "sent":
            q = q.filter(Meeting.status == PENDING, Meeting.requester_id == me)
        elif filter == "cancelled":
            q = q.filter(Meeting.status.in_(CLOSED))
        elif filter == "ended":
            q = q.filter(or_(
                Meeting.status.in_(OUTCOME),
                and_(Meeting.status == CONFIRMED, Meeting.end_time <= now),
            ))
        elif filter == "upcoming":
            q = q.filter(or_(
                and_(Meeting.status == CONFIRMED, Meeting.end_time > now),
                and_(Meeting.status == RESCHEDULE, Meeting.proposed_by == me),
            ))
        else:
            q = q.filter(or_(
                Meeting.status.in_((CONFIRMED,) + OUTCOME),
                and_(Meeting.status == RESCHEDULE, Meeting.proposed_by == me),
                and_(Meeting.status == PENDING, Meeting.requester_id == me),
            ))

    total = q.count()
    rows = q.order_by(Meeting.start_time.asc()).limit(limit).all()
    users = _load_users(db, {_other_id(r, me) for r in rows})

    return {
        "status": "success",
        "total": total,
        "data": [_serialize(r, me, users) for r in rows],
    }


@router.get("/{meeting_id}")
def get_meeting(
    meeting_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _me(current_user)
    row = _get_mine(db, meeting_id, me)
    users = _load_users(db, [_other_id(row, me)])
    return {"status": "success", "data": _serialize(row, me, users)}


# ============================================================================
# Create and edit
# ============================================================================

@router.post("/requests/{user_id}", status_code=status.HTTP_201_CREATED)
def request_meeting(
    user_id: int,
    payload: MeetingCreate,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _me(current_user)
    if user_id == me:
        raise HTTPException(status_code=400, detail="You cannot book a meeting with yourself")
    other = db.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()
    if other is None:
        raise HTTPException(status_code=404, detail="Person not found")
    _ensure_not_blocked(db, me, user_id)
    _require_future(payload.start_time)
    _assert_free(db, [me, user_id], payload.start_time, payload.end_time)

    row = Meeting(
        requester_id=me,
        receiver_id=user_id,
        title=payload.title.strip(),
        note=(payload.note or "").strip() or None,
        location=(payload.location or "").strip() or None,
        start_time=payload.start_time,
        end_time=payload.end_time,
        status=PENDING,
    )
    db.add(row)
    _commit(db, "Request meeting", "Could not send your meeting request")
    db.refresh(row)

    return {
        "status": "success",
        "message": "Meeting request sent",
        "data": _serialize(row, me, {other.id: other}),
    }


@router.put("/{meeting_id}")
def edit_meeting(
    meeting_id: int,
    payload: MeetingUpdate,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _me(current_user)
    row = _get_mine(db, meeting_id, me)
    if row.status != PENDING:
        raise HTTPException(status_code=400, detail="Only a pending request can be edited")
    if row.requester_id != me:
        raise HTTPException(status_code=403, detail="Only the person who sent the request can edit it")

    if payload.title is not None:
        row.title = payload.title.strip()
    if payload.note is not None:
        row.note = payload.note.strip() or None
    if payload.location is not None:
        row.location = payload.location.strip() or None
    if payload.start_time is not None or payload.end_time is not None:
        start = payload.start_time or row.start_time
        end = payload.end_time or row.end_time
        if end <= start:
            raise HTTPException(status_code=400, detail="End time must be after start time")
        _require_future(start)
        _assert_free(db, [row.requester_id, row.receiver_id], start, end, exclude_id=row.id)
        row.start_time, row.end_time = start, end

    _commit(db, "Edit meeting", "Could not save the meeting")
    return {"status": "success", "message": "Meeting updated", "data": {"id": row.id}}


# ============================================================================
# Remove from my list (delete)
# ============================================================================

@router.delete("/{meeting_id}")
def remove_meeting(
    meeting_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _me(current_user)
    row = _get_mine(db, meeting_id, me)
    is_requester = row.requester_id == me
    now = _now()

    if row.status == PENDING:
        # Requester withdraws the request; receiver declines it
        row.status = CANCELLED if is_requester else REJECTED
    elif row.status in CLOSED or row.status in OUTCOME:
        pass
    elif row.status == CONFIRMED and row.end_time <= now:
        pass
    else:
        raise HTTPException(status_code=400, detail="Cancel this meeting before removing it")

    if is_requester:
        row.requester_hidden = True
    else:
        row.receiver_hidden = True

    _commit(db, "Remove meeting", "Could not remove this meeting")
    return {"status": "success", "message": "Removed from your meetings"}


# ============================================================================
# Responses and changes
# ============================================================================

@router.post("/{meeting_id}/accept")
def accept_meeting(
    meeting_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _me(current_user)
    row = _get_mine(db, meeting_id, me)
    people = [row.requester_id, row.receiver_id]

    if row.status == PENDING and row.receiver_id == me:
        _assert_free(db, people, row.start_time, row.end_time, exclude_id=row.id)
        row.status = CONFIRMED
    elif row.status == RESCHEDULE and row.proposed_by != me:
        _assert_free(db, people, row.proposed_start, row.proposed_end, exclude_id=row.id)
        row.start_time, row.end_time = row.proposed_start, row.proposed_end
        _clear_proposal(row)
        row.status = CONFIRMED
    else:
        raise HTTPException(status_code=400, detail="Nothing here is waiting for your answer")

    _commit(db, "Accept meeting", "Could not accept the meeting")
    return {"status": "success", "message": "Meeting confirmed", "data": {"id": row.id, "status": CONFIRMED}}


@router.post("/{meeting_id}/reject")
def reject_meeting(
    meeting_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _me(current_user)
    row = _get_mine(db, meeting_id, me)

    if row.status == PENDING and row.receiver_id == me:
        row.status = REJECTED
    elif row.status == RESCHEDULE and row.proposed_by != me:
        # Keep the original time and return to confirmed
        _clear_proposal(row)
        row.status = CONFIRMED
    else:
        raise HTTPException(status_code=400, detail="Nothing here is waiting for your answer")

    _commit(db, "Reject meeting", "Could not decline the meeting")
    return {"status": "success", "message": "Meeting declined", "data": {"id": row.id, "status": row.status}}


@router.post("/{meeting_id}/reschedule")
def propose_reschedule(
    meeting_id: int,
    payload: TimeProposal,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _me(current_user)
    row = _get_mine(db, meeting_id, me)
    other = _other_id(row, me)

    if row.status == RESCHEDULE:
        raise HTTPException(status_code=400, detail="A reschedule is already waiting for an answer")
    if row.status != CONFIRMED:
        raise HTTPException(status_code=400, detail="Only confirmed meetings can be rescheduled")
    if row.end_time <= _now():
        raise HTTPException(status_code=400, detail="This meeting has already ended")

    _ensure_not_blocked(db, me, other)
    _require_future(payload.start_time)
    _assert_free(db, [me, other], payload.start_time, payload.end_time, exclude_id=row.id)

    row.proposed_start = payload.start_time
    row.proposed_end = payload.end_time
    row.proposed_note = (payload.note or "").strip() or None
    row.proposed_by = me
    row.status = RESCHEDULE
    _commit(db, "Propose reschedule", "Could not send the new time")
    return {"status": "success", "message": "New time sent for approval", "data": {"id": row.id, "status": RESCHEDULE}}


@router.post("/{meeting_id}/cancel")
def cancel_meeting(
    meeting_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _me(current_user)
    row = _get_mine(db, meeting_id, me)
    if row.status not in ACTIVE:
        raise HTTPException(status_code=400, detail="This meeting cannot be cancelled")

    row.status = CANCELLED
    _clear_proposal(row)
    _commit(db, "Cancel meeting", "Could not cancel the meeting")
    return {"status": "success", "message": "Meeting cancelled", "data": {"id": row.id, "status": CANCELLED}}


@router.post("/{meeting_id}/status")
def mark_status(
    meeting_id: int,
    payload: StatusUpdate,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _me(current_user)
    row = _get_mine(db, meeting_id, me)
    if row.status != CONFIRMED:
        raise HTTPException(status_code=400, detail="Only confirmed meetings can be marked")
    if row.end_time > _now():
        raise HTTPException(status_code=400, detail="You can mark the status after the meeting ends")

    row.status = payload.status
    _commit(db, "Mark meeting status", "Could not update the status")
    return {"status": "success", "message": "Status updated", "data": {"id": row.id, "status": row.status}}