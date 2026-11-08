# ============================================================================
# 1-2-1 Meetings (Production Ready)
# File: app/routes/meetings.py
# Mounted at /api/v1/meetings
#
# GET    /?tab=confirmed|invites|sent    my meetings
# POST   /requests/{user_id}             request a 1-2-1
# PUT    /{id}                           edit details (requester while pending; either person otherwise)
# POST   /{id}/accept                    receiver accepts (or accepts a reschedule)
# POST   /{id}/reject                    receiver rejects (or rejects a reschedule)
# POST   /{id}/reschedule                propose a new time (confirmed meetings)
# POST   /{id}/cancel                    either person cancels
# POST   /{id}/status                    completed | no_show, after confirmation
# DELETE /{id}                           remove a rejected or cancelled meeting
# ============================================================================

import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, or_, and_
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

ACTIVE_STATES = (PENDING, CONFIRMED, RESCHEDULE)
OUTCOME_STATES = (COMPLETED, NO_SHOW)


# ============================================================================
# Database model
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
    proposed_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


# ============================================================================
# Schemas
# ============================================================================

class MeetingCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    note: Optional[str] = Field(None, max_length=1000)
    location: Optional[str] = Field(None, max_length=255)
    start_time: datetime
    end_time: datetime

    @model_validator(mode="after")
    def check_times(self):
        if self.end_time <= self.start_time:
            raise ValueError("End time must be after start time")
        return self


class MeetingUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=200)
    note: Optional[str] = Field(None, max_length=1000)
    location: Optional[str] = Field(None, max_length=255)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


class TimeProposal(BaseModel):
    start_time: datetime
    end_time: datetime

    @model_validator(mode="after")
    def check_times(self):
        if self.end_time <= self.start_time:
            raise ValueError("End time must be after start time")
        return self


class StatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(completed|no_show)$")


# ============================================================================
# Helpers
# ============================================================================

def _me(current_user: Any) -> int:
    user_id = getattr(current_user, "id", None)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid user session")
    return user_id


def _get_meeting(db: DBSession, meeting_id: int) -> Meeting:
    row = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return row


def _is_participant(row: Meeting, me: int) -> bool:
    return me in (row.requester_id, row.receiver_id)


def _other_id(row: Meeting, me: int) -> int:
    return row.receiver_id if row.requester_id == me else row.requester_id


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
    other = users.get(_other_id(row, me))
    return {
        "id": row.id,
        "title": row.title,
        "note": row.note or "",
        "location": row.location or "",
        "start_time": row.start_time.isoformat() if row.start_time else None,
        "end_time": row.end_time.isoformat() if row.end_time else None,
        "status": row.status,
        "is_requester": row.requester_id == me,
        "proposed_start": row.proposed_start.isoformat() if row.proposed_start else None,
        "proposed_end": row.proposed_end.isoformat() if row.proposed_end else None,
        "proposed_by_me": row.proposed_by == me if row.proposed_by else False,
        "other": _person(other),
    }


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


# ============================================================================
# Lists
# ============================================================================

@router.get("/")
def list_meetings(
    tab: str = Query("confirmed", pattern="^(confirmed|invites|sent)$"),
    limit: int = Query(50, ge=1, le=100),
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _me(current_user)
    base = db.query(Meeting).filter(or_(Meeting.requester_id == me, Meeting.receiver_id == me))

    if tab == "confirmed":
        query = base.filter(or_(
            Meeting.status.in_([CONFIRMED, COMPLETED, NO_SHOW]),
            and_(Meeting.status == RESCHEDULE, Meeting.proposed_by == me),
        ))
    elif tab == "invites":
        query = base.filter(or_(
            and_(Meeting.status == PENDING, Meeting.receiver_id == me),
            and_(Meeting.status == RESCHEDULE, Meeting.proposed_by != me),
        ))
    else:  # sent
        query = base.filter(or_(
            and_(Meeting.status == PENDING, Meeting.requester_id == me),
            Meeting.status.in_([REJECTED, CANCELLED]),
        ))

    rows = query.order_by(Meeting.start_time.asc()).limit(limit).all()
    other_ids = {_other_id(r, me) for r in rows}
    users = {u.id: u for u in db.query(User).filter(User.id.in_(other_ids)).all()} if other_ids else {}

    return {"status": "success", "data": [_serialize(r, me, users) for r in rows]}


# ============================================================================
# Create, edit, delete
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
    if db.query(User.id).filter(User.id == user_id, User.is_active.is_(True)).first() is None:
        raise HTTPException(status_code=404, detail="Person not found")
    _ensure_not_blocked(db, me, user_id)

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

    return {"status": "success", "message": "Meeting request sent", "data": {"id": row.id, "status": PENDING}}


@router.put("/{meeting_id}")
def edit_meeting(
    meeting_id: int,
    payload: MeetingUpdate,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _me(current_user)
    row = _get_meeting(db, meeting_id)
    if not _is_participant(row, me):
        raise HTTPException(status_code=403, detail="You are not part of this meeting")
    if row.status in (REJECTED, CANCELLED):
        raise HTTPException(status_code=400, detail="This meeting is closed and cannot be edited")
    if row.status in OUTCOME_STATES:
        raise HTTPException(status_code=400, detail="This meeting has already ended")

    # Only the requester edits a pending request. Confirmed meetings change via reschedule.
    if row.status == PENDING and row.requester_id != me:
        raise HTTPException(status_code=403, detail="Only the person who sent the request can edit it")
    if row.status != PENDING and any(v is not None for v in (payload.start_time, payload.end_time)):
        raise HTTPException(status_code=400, detail="Use reschedule to change the time of a confirmed meeting")

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
        row.start_time, row.end_time = start, end

    _commit(db, "Edit meeting", "Could not save the meeting")
    return {"status": "success", "message": "Meeting updated", "data": {"id": row.id}}


@router.delete("/{meeting_id}")
def delete_meeting(
    meeting_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _me(current_user)
    row = _get_meeting(db, meeting_id)
    if not _is_participant(row, me):
        raise HTTPException(status_code=403, detail="You are not part of this meeting")
    if row.status not in (REJECTED, CANCELLED):
        raise HTTPException(status_code=400, detail="Cancel or reject the meeting before deleting it")

    try:
        db.delete(row)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Delete meeting failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not delete the meeting")

    return {"status": "success", "message": "Meeting deleted"}


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
    row = _get_meeting(db, meeting_id)

    if row.status == PENDING and row.receiver_id == me:
        row.status = CONFIRMED
    elif row.status == RESCHEDULE and row.proposed_by != me and _is_participant(row, me):
        row.start_time, row.end_time = row.proposed_start, row.proposed_end
        row.proposed_start = row.proposed_end = row.proposed_by = None
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
    row = _get_meeting(db, meeting_id)

    if row.status == PENDING and row.receiver_id == me:
        row.status = REJECTED
    elif row.status == RESCHEDULE and row.proposed_by != me and _is_participant(row, me):
        # Keep the original time and go back to confirmed
        row.proposed_start = row.proposed_end = row.proposed_by = None
        row.status = CONFIRMED
    else:
        raise HTTPException(status_code=400, detail="Nothing here is waiting for your answer")

    _commit(db, "Reject meeting", "Could not reject the meeting")
    return {"status": "success", "message": "Meeting declined", "data": {"id": row.id, "status": row.status}}


@router.post("/{meeting_id}/reschedule")
def propose_reschedule(
    meeting_id: int,
    payload: TimeProposal,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _me(current_user)
    row = _get_meeting(db, meeting_id)
    if not _is_participant(row, me):
        raise HTTPException(status_code=403, detail="You are not part of this meeting")
    if row.status not in (CONFIRMED, RESCHEDULE):
        raise HTTPException(status_code=400, detail="Only confirmed meetings can be rescheduled")

    _ensure_not_blocked(db, me, _other_id(row, me))

    row.proposed_start = payload.start_time
    row.proposed_end = payload.end_time
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
    row = _get_meeting(db, meeting_id)
    if not _is_participant(row, me):
        raise HTTPException(status_code=403, detail="You are not part of this meeting")
    if row.status not in ACTIVE_STATES:
        raise HTTPException(status_code=400, detail="This meeting cannot be cancelled")

    row.status = CANCELLED
    row.proposed_start = row.proposed_end = row.proposed_by = None
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
    row = _get_meeting(db, meeting_id)
    if not _is_participant(row, me):
        raise HTTPException(status_code=403, detail="You are not part of this meeting")
    if row.status != CONFIRMED:
        raise HTTPException(status_code=400, detail="Only confirmed meetings can be marked")

    row.status = payload.status
    _commit(db, "Mark meeting status", "Could not update the status")
    return {"status": "success", "message": "Status updated", "data": {"id": row.id, "status": row.status}}