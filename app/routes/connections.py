# ============================================================================
# Connections (Production Ready)
# File: app/routes/connections.py
# Mounted at /api/v1/connections
#
# POST   /scan/{user_id}            save a badge-scanned person (accepted at once)
# GET    /contacts                  accepted connections (My Contacts)
# GET    /requests?direction=in|out pending requests
# POST   /requests/{user_id}        send a request, with an optional message
# POST   /requests/{id}/accept      receiver accepts
# POST   /requests/{id}/reject      receiver rejects
# DELETE /requests/{id}             sender revokes a pending request
# GET    /status/{user_id}          none | pending_out | pending_in | connected
# DELETE /contacts/{user_id}        remove a contact
# ============================================================================

import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, or_, and_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.models import Base, User
from app.routes.auth import get_current_user
from app.routes.blocks import is_blocked_between

logger = logging.getLogger(__name__)
router = APIRouter()

PENDING = "pending"
ACCEPTED = "accepted"
REJECTED = "rejected"


# ============================================================================
# Database model
# ============================================================================

class ConnectionRequest(Base):
    __tablename__ = "connection_requests"
    __table_args__ = (
        UniqueConstraint("sender_id", "receiver_id", name="uq_connection_pair"),
    )

    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer, ForeignKey(f"{User.__tablename__}.id", ondelete="CASCADE"), nullable=False, index=True)
    receiver_id = Column(Integer, ForeignKey(f"{User.__tablename__}.id", ondelete="CASCADE"), nullable=False, index=True)
    message = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default=PENDING, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    responded_at = Column(DateTime, nullable=True)


# ============================================================================
# Schemas
# ============================================================================

class RequestCreate(BaseModel):
    message: Optional[str] = Field(None, max_length=500)


# ============================================================================
# Helpers
# ============================================================================

def _me(current_user: Any) -> int:
    user_id = getattr(current_user, "id", None)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid user session")
    return user_id


def _person(user: User) -> dict:
    full = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username or "Attendee"
    return {
        "user_id": user.id,
        "name": full,
        "avatar_url": user.avatar_url,
        "job_title": user.job_title,
        "company": user.company,
    }


def _contact_person(user: User) -> dict:
    """Saved contacts include email and phone, so they can be shown and exported."""
    data = _person(user)
    data["email"] = user.email
    data["phone"] = user.phone
    return data


def _get_user_or_404(db: DBSession, user_id: int) -> User:
    user = db.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()
    if user is None:
        raise HTTPException(status_code=404, detail="Person not found")
    return user


def _is_blocked_between(db: DBSession, a: int, b: int) -> bool:
    return is_blocked_between(db, a, b)


def _commit(db: DBSession, action: str, detail: str) -> None:
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("%s failed: %s", action, exc)
        raise HTTPException(status_code=500, detail=detail)


def _pair_filter(a: int, b: int):
    return or_(
        and_(ConnectionRequest.sender_id == a, ConnectionRequest.receiver_id == b),
        and_(ConnectionRequest.sender_id == b, ConnectionRequest.receiver_id == a),
    )


# ============================================================================
# Save on badge scan (mutual, so the contact is accepted at once)
# ============================================================================

@router.post("/scan/{user_id}", status_code=status.HTTP_200_OK)
def save_scanned_contact(
    user_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _me(current_user)
    if user_id == me:
        raise HTTPException(status_code=400, detail="You cannot save yourself")
    _get_user_or_404(db, user_id)

    if _is_blocked_between(db, me, user_id):
        raise HTTPException(status_code=403, detail="You cannot connect with this person")

    row = db.query(ConnectionRequest).filter(_pair_filter(me, user_id)).first()

    if row is not None:
        if row.status != ACCEPTED:
            row.status = ACCEPTED
            row.responded_at = datetime.utcnow()
            _commit(db, "Scan accept", "Could not save this contact")
        return {
            "status": "success",
            "message": "Contact saved",
            "data": {"request_id": row.id, "state": "connected"},
        }

    row = ConnectionRequest(
        sender_id=me,
        receiver_id=user_id,
        status=ACCEPTED,
        responded_at=datetime.utcnow(),
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        # Another request for this pair was created at the same moment: treat as saved.
        db.rollback()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Scan save failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not save this contact")
    else:
        db.refresh(row)

    return {
        "status": "success",
        "message": "Contact saved",
        "data": {"request_id": row.id if row.id else None, "state": "connected"},
    }


# ============================================================================
# Lists
# ============================================================================

@router.get("/contacts")
def my_contacts(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _me(current_user)
    query = db.query(ConnectionRequest).filter(
        ConnectionRequest.status == ACCEPTED,
        or_(ConnectionRequest.sender_id == me, ConnectionRequest.receiver_id == me),
    )
    total = query.count()
    rows = query.order_by(ConnectionRequest.responded_at.desc()).offset((page - 1) * limit).limit(limit).all()

    other_ids = [r.receiver_id if r.sender_id == me else r.sender_id for r in rows]
    users = {u.id: u for u in db.query(User).filter(User.id.in_(other_ids)).all()} if other_ids else {}

    data = []
    for r in rows:
        other_id = r.receiver_id if r.sender_id == me else r.sender_id
        user = users.get(other_id)
        if user is None:
            continue
        data.append(_contact_person(user))

    return {"status": "success", "total": total, "page": page, "limit": limit, "data": data}


@router.get("/requests")
def my_requests(
    direction: str = Query("in", pattern="^(in|out)$"),
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _me(current_user)
    if direction == "in":
        rows = db.query(ConnectionRequest).filter(
            ConnectionRequest.receiver_id == me,
            ConnectionRequest.status == PENDING,
        ).order_by(ConnectionRequest.created_at.desc()).all()
        other_ids = [r.sender_id for r in rows]
    else:
        rows = db.query(ConnectionRequest).filter(
            ConnectionRequest.sender_id == me,
            ConnectionRequest.status == PENDING,
        ).order_by(ConnectionRequest.created_at.desc()).all()
        other_ids = [r.receiver_id for r in rows]

    users = {u.id: u for u in db.query(User).filter(User.id.in_(other_ids)).all()} if other_ids else {}

    data = []
    for r in rows:
        other_id = r.sender_id if direction == "in" else r.receiver_id
        user = users.get(other_id)
        if user is None:
            continue
        item = _person(user)
        item.update({
            "request_id": r.id,
            "message": r.message or "",
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })
        data.append(item)

    return {"status": "success", "data": data}


# ============================================================================
# Status for an attendee profile (drives the Chat / Request button)
# ============================================================================

@router.get("/status/{user_id}")
def connection_status(
    user_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _me(current_user)
    if user_id == me:
        return {"status": "success", "data": {"state": "self", "request_id": None}}

    row = db.query(ConnectionRequest).filter(_pair_filter(me, user_id)).first()
    if row is None or row.status == REJECTED:
        state = "none"
    elif row.status == ACCEPTED:
        state = "connected"
    elif row.sender_id == me:
        state = "pending_out"
    else:
        state = "pending_in"

    return {
        "status": "success",
        "data": {"state": state, "request_id": row.id if row else None},
    }


# ============================================================================
# Send, accept, reject, revoke
# ============================================================================

@router.post("/requests/{user_id}", status_code=status.HTTP_201_CREATED)
def send_request(
    user_id: int,
    payload: RequestCreate,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _me(current_user)
    if user_id == me:
        raise HTTPException(status_code=400, detail="You cannot connect with yourself")
    _get_user_or_404(db, user_id)

    if _is_blocked_between(db, me, user_id):
        raise HTTPException(status_code=403, detail="You cannot connect with this person")

    existing = db.query(ConnectionRequest).filter(_pair_filter(me, user_id)).first()

    if existing is not None:
        if existing.status == ACCEPTED:
            raise HTTPException(status_code=400, detail="You are already connected")
        if existing.status == PENDING and existing.sender_id == me:
            raise HTTPException(status_code=400, detail="Your request is already pending")
        if existing.status == PENDING and existing.sender_id != me:
            # They already asked you: accepting their request is the natural result
            existing.status = ACCEPTED
            existing.responded_at = datetime.utcnow()
            _commit(db, "Auto-accept connection", "Could not connect")
            return {"status": "success", "message": "You are now connected", "data": {"request_id": existing.id, "state": "connected"}}
        # Previously rejected: allow a fresh request by reusing the row
        existing.sender_id = me
        existing.receiver_id = user_id
        existing.status = PENDING
        existing.message = (payload.message or "").strip() or None
        existing.created_at = datetime.utcnow()
        existing.responded_at = None
        _commit(db, "Resend connection", "Could not send your request")
        return {"status": "success", "message": "Request sent", "data": {"request_id": existing.id, "state": "pending_out"}}

    row = ConnectionRequest(
        sender_id=me,
        receiver_id=user_id,
        message=(payload.message or "").strip() or None,
        status=PENDING,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="A request already exists")
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Send connection request failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not send your request")
    db.refresh(row)

    return {"status": "success", "message": "Request sent", "data": {"request_id": row.id, "state": "pending_out"}}


@router.post("/requests/{request_id}/accept")
def accept_request(
    request_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _me(current_user)
    row = db.query(ConnectionRequest).filter(ConnectionRequest.id == request_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Request not found")
    if row.receiver_id != me:
        raise HTTPException(status_code=403, detail="Only the person who received this request can accept it")
    if row.status != PENDING:
        raise HTTPException(status_code=400, detail="This request is no longer pending")

    row.status = ACCEPTED
    row.responded_at = datetime.utcnow()
    _commit(db, "Accept connection", "Could not accept the request")
    return {"status": "success", "message": "Connection accepted", "data": {"state": "connected"}}


@router.post("/requests/{request_id}/reject")
def reject_request(
    request_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _me(current_user)
    row = db.query(ConnectionRequest).filter(ConnectionRequest.id == request_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Request not found")
    if row.receiver_id != me:
        raise HTTPException(status_code=403, detail="Only the person who received this request can reject it")
    if row.status != PENDING:
        raise HTTPException(status_code=400, detail="This request is no longer pending")

    row.status = REJECTED
    row.responded_at = datetime.utcnow()
    _commit(db, "Reject connection", "Could not reject the request")
    return {"status": "success", "message": "Request declined", "data": {"state": "none"}}


@router.delete("/requests/{request_id}")
def revoke_request(
    request_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _me(current_user)
    row = db.query(ConnectionRequest).filter(ConnectionRequest.id == request_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Request not found")
    if row.sender_id != me:
        raise HTTPException(status_code=403, detail="Only the sender can revoke this request")
    if row.status != PENDING:
        raise HTTPException(status_code=400, detail="Only pending requests can be revoked")

    try:
        db.delete(row)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Revoke connection failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not revoke the request")

    return {"status": "success", "message": "Request revoked", "data": {"state": "none"}}


@router.delete("/contacts/{user_id}")
def remove_contact(
    user_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _me(current_user)
    row = db.query(ConnectionRequest).filter(
        _pair_filter(me, user_id),
        ConnectionRequest.status == ACCEPTED,
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="This person is not in your contacts")

    try:
        db.delete(row)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Remove contact failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not remove this contact")

    return {"status": "success", "message": "Removed from your contacts", "data": {"state": "none"}}