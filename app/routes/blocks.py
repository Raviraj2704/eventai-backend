# ============================================================================
# Blocks (Production Ready)
# File: app/routes/blocks.py
# Mounted at /api/v1/blocks
#
# GET    /               people I have blocked
# POST   /{user_id}      block a person (removes any connection with them)
# DELETE /{user_id}      unblock a person
# ============================================================================

import logging
from datetime import datetime
from typing import Any, Set

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import Column, DateTime, ForeignKey, Integer, UniqueConstraint, or_, and_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.models import Base, User
from app.routes.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================================
# Database model
# ============================================================================

class UserBlock(Base):
    __tablename__ = "user_blocks"
    __table_args__ = (
        UniqueConstraint("blocker_id", "blocked_id", name="uq_user_block_pair"),
    )

    id = Column(Integer, primary_key=True, index=True)
    blocker_id = Column(Integer, ForeignKey(f"{User.__tablename__}.id", ondelete="CASCADE"), nullable=False, index=True)
    blocked_id = Column(Integer, ForeignKey(f"{User.__tablename__}.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


# ============================================================================
# Shared helpers (imported by connections, users, and chat)
# ============================================================================

def is_blocked_between(db: DBSession, a: int, b: int) -> bool:
    """True if either person has blocked the other."""
    return (
        db.query(UserBlock.id)
        .filter(
            or_(
                and_(UserBlock.blocker_id == a, UserBlock.blocked_id == b),
                and_(UserBlock.blocker_id == b, UserBlock.blocked_id == a),
            )
        )
        .first()
        is not None
    )


def blocked_user_ids(db: DBSession, me: int) -> Set[int]:
    """Every user id that is hidden from me, in either direction."""
    rows = db.query(UserBlock.blocker_id, UserBlock.blocked_id).filter(
        or_(UserBlock.blocker_id == me, UserBlock.blocked_id == me)
    ).all()
    hidden = set()
    for blocker_id, blocked_id in rows:
        hidden.add(blocked_id if blocker_id == me else blocker_id)
    return hidden


def _commit(db: DBSession, action: str, detail: str) -> None:
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("%s failed: %s", action, exc)
        raise HTTPException(status_code=500, detail=detail)


# ============================================================================
# Routes
# ============================================================================

@router.get("/")
def list_blocked(
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    rows = (
        db.query(UserBlock)
        .filter(UserBlock.blocker_id == current_user.id)
        .order_by(UserBlock.created_at.desc())
        .all()
    )
    ids = [r.blocked_id for r in rows]
    users = {u.id: u for u in db.query(User).filter(User.id.in_(ids)).all()} if ids else {}

    data = []
    for r in rows:
        u = users.get(r.blocked_id)
        if u is None:
            continue
        name = f"{u.first_name or ''} {u.last_name or ''}".strip() or u.username or "Attendee"
        data.append({
            "user_id": u.id,
            "name": name,
            "avatar_url": u.avatar_url,
            "job_title": u.job_title,
            "company": u.company,
        })

    return {"status": "success", "data": data}


@router.post("/{user_id}", status_code=status.HTTP_201_CREATED)
def block_user(
    user_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    from app.routes.connections import ConnectionRequest  # local import avoids a circular import

    me = current_user.id
    if user_id == me:
        raise HTTPException(status_code=400, detail="You cannot block yourself")
    if db.query(User.id).filter(User.id == user_id).first() is None:
        raise HTTPException(status_code=404, detail="Person not found")

    already = (
        db.query(UserBlock.id)
        .filter(UserBlock.blocker_id == me, UserBlock.blocked_id == user_id)
        .first()
    )
    if already is not None:
        return {"status": "success", "message": "Already blocked", "data": {"state": "blocked"}}

    # Remove any connection or pending request between the two people
    db.query(ConnectionRequest).filter(
        or_(
            and_(ConnectionRequest.sender_id == me, ConnectionRequest.receiver_id == user_id),
            and_(ConnectionRequest.sender_id == user_id, ConnectionRequest.receiver_id == me),
        )
    ).delete(synchronize_session=False)

    db.add(UserBlock(blocker_id=me, blocked_id=user_id))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return {"status": "success", "message": "Already blocked", "data": {"state": "blocked"}}
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Block user failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not block this person")

    return {"status": "success", "message": "Blocked", "data": {"state": "blocked"}}


@router.delete("/{user_id}")
def unblock_user(
    user_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    row = (
        db.query(UserBlock)
        .filter(UserBlock.blocker_id == current_user.id, UserBlock.blocked_id == user_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="This person is not blocked")

    try:
        db.delete(row)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Unblock user failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not unblock this person")

    return {"status": "success", "message": "Unblocked", "data": {"state": "none"}}