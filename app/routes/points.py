# ============================================================================
# Points and Leaderboard
# File: app/routes/points.py
# Mounted at /api/v1/points
#
# GET    /criteria                      all ways to earn points (Criteria tab)
# GET    /me                            my total and what I have earned (My Points tab)
# GET    /leaderboard?limit=50          ranked list, top N, plus my own entry
# POST   /award                         admin awards a criterion to a person
# DELETE /award/{user_id}/{criteria_id} admin removes an award
# ============================================================================

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.models import Base, User
from app.routes.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================================
# Database models (tables created in Step 1)
# ============================================================================

class PointCriteria(Base):
    __tablename__ = "point_criteria"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    points = Column(Integer, nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)


class UserPoint(Base):
    __tablename__ = "user_points"
    __table_args__ = (
        UniqueConstraint("user_id", "criteria_id", name="uq_user_criteria"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey(f"{User.__tablename__}.id", ondelete="CASCADE"), nullable=False, index=True)
    criteria_id = Column(Integer, ForeignKey(PointCriteria.__tablename__ + ".id", ondelete="CASCADE"), nullable=False)
    awarded_by = Column(Integer, nullable=True)
    awarded_at = Column(DateTime, nullable=False, default=datetime.utcnow)


# ============================================================================
# Schemas
# ============================================================================

class AwardIn(BaseModel):
    user_id: int
    criteria_id: int


# ============================================================================
# Helpers
# ============================================================================

def _iso(dt):
    return dt.isoformat() + "Z" if dt else None


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Only admins can award points")
    return current_user


def _board(db: DBSession) -> list:
    """Everyone active, ordered by points. Ties share a rank (1, 2, 2, 4)."""
    total = func.coalesce(func.sum(PointCriteria.points), 0)
    rows = (
        db.query(
            User.id,
            User.first_name,
            User.last_name,
            User.username,
            User.avatar_url,
            total.label("points"),
        )
        .outerjoin(UserPoint, UserPoint.user_id == User.id)
        .outerjoin(PointCriteria, PointCriteria.id == UserPoint.criteria_id)
        .filter(User.is_active.is_(True))
        .group_by(User.id)
        .order_by(total.desc(), User.id.asc())
        .all()
    )

    board = []
    last_points = None
    rank = 0
    for position, r in enumerate(rows, start=1):
        pts = int(r.points or 0)
        if pts != last_points:
            rank = position
            last_points = pts
        name = f"{r.first_name or ''} {r.last_name or ''}".strip() or r.username or "Attendee"
        board.append({
            "rank": rank,
            "user_id": r.id,
            "name": name,
            "avatar_url": r.avatar_url,
            "points": pts,
        })
    return board


# ============================================================================
# Read endpoints (any logged-in user)
# ============================================================================

@router.get("/criteria")
def list_criteria(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = db.query(PointCriteria).order_by(PointCriteria.sort_order.asc(), PointCriteria.id.asc()).all()
    return {
        "status": "success",
        "data": [{"id": r.id, "title": r.title, "points": r.points} for r in rows],
    }


@router.get("/me")
def my_points(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(UserPoint, PointCriteria)
        .join(PointCriteria, PointCriteria.id == UserPoint.criteria_id)
        .filter(UserPoint.user_id == current_user.id)
        .order_by(UserPoint.awarded_at.asc())
        .all()
    )
    earned = [
        {
            "criteria_id": c.id,
            "title": c.title,
            "points": c.points,
            "awarded_at": _iso(up.awarded_at),
        }
        for up, c in rows
    ]
    return {
        "status": "success",
        "data": {
            "total": sum(e["points"] for e in earned),
            "earned": earned,
        },
    }


@router.get("/leaderboard")
def leaderboard(
    limit: int = Query(50, ge=1, le=200),
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    board = _board(db)
    me = next((b for b in board if b["user_id"] == current_user.id), None)
    return {
        "status": "success",
        "data": {
            "top": board[:limit],
            "me": me,
            "total_users": len(board),
        },
    }


# ============================================================================
# Admin: award and revoke
# ============================================================================

@router.post("/award", status_code=status.HTTP_201_CREATED)
def award_points(
    payload: AwardIn,
    db: DBSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if db.query(User.id).filter(User.id == payload.user_id).first() is None:
        raise HTTPException(status_code=404, detail="Person not found")
    criteria = db.query(PointCriteria).filter(PointCriteria.id == payload.criteria_id).first()
    if criteria is None:
        raise HTTPException(status_code=404, detail="Criteria not found")

    existing = db.query(UserPoint).filter(
        UserPoint.user_id == payload.user_id,
        UserPoint.criteria_id == payload.criteria_id,
    ).first()
    if existing is not None:
        return {"status": "success", "message": "Already awarded", "data": {"awarded": False}}

    db.add(UserPoint(
        user_id=payload.user_id,
        criteria_id=payload.criteria_id,
        awarded_by=admin.id,
        awarded_at=datetime.utcnow(),
    ))
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("Award points failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not award points")

    return {
        "status": "success",
        "message": f"{criteria.points} points awarded",
        "data": {"awarded": True, "points": criteria.points},
    }


@router.delete("/award/{user_id}/{criteria_id}")
def revoke_points(
    user_id: int,
    criteria_id: int,
    db: DBSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    row = db.query(UserPoint).filter(
        UserPoint.user_id == user_id,
        UserPoint.criteria_id == criteria_id,
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="This award does not exist")
    db.delete(row)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("Revoke points failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not remove the award")
    return {"status": "success", "message": "Award removed"}