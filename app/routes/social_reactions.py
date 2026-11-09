# ============================================================================
# Social reactions and wall feed
# File: app/routes/social_reactions.py
# Mounted at /api/v1/social (alongside the existing social routes)
#
# GET    /wall                       posts with reaction counts, my reaction, author
# POST   /posts/{post_id}/react      set my reaction: like | love | haha
# DELETE /posts/{post_id}/react      remove my reaction
# ============================================================================

import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.models import Base, SocialPost, User
from app.routes.auth import get_current_user
from app.routes.blocks import blocked_user_ids

logger = logging.getLogger(__name__)
router = APIRouter()

KINDS = ("like", "love", "haha")


# ============================================================================
# Database model: one reaction per user per post
# ============================================================================

class SocialPostReaction(Base):
    __tablename__ = "social_post_reactions"
    __table_args__ = (
        UniqueConstraint("post_id", "user_id", name="uq_social_post_reaction"),
    )

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey(f"{SocialPost.__tablename__}.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey(f"{User.__tablename__}.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String(10), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ReactionIn(BaseModel):
    kind: str = Field(..., pattern="^(like|love|haha)$")


# ============================================================================
# Helpers
# ============================================================================

def _me(current_user: Any) -> int:
    user_id = getattr(current_user, "id", None)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid user session")
    return user_id


def _person(user: Optional[User]) -> Optional[dict]:
    if user is None:
        return None
    name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username or "Attendee"
    return {
        "user_id": user.id,
        "name": name,
        "avatar_url": user.avatar_url,
        "job_title": user.job_title,
    }


def _commit(db: DBSession, action: str, detail: str) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Please try again")
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("%s failed: %s", action, exc)
        raise HTTPException(status_code=500, detail=detail)


# ============================================================================
# Wall feed
# ============================================================================

@router.get("/wall")
def social_wall(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _me(current_user)
    hidden = blocked_user_ids(db, me)

    query = db.query(SocialPost).filter(SocialPost.is_approved == True)
    if hidden:
        query = query.filter(SocialPost.user_id.notin_(hidden))

    total = query.count()
    posts = (
        query.order_by(SocialPost.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    post_ids = [p.id for p in posts]

    counts = {pid: {k: 0 for k in KINDS} for pid in post_ids}
    mine = {}
    if post_ids:
        rows = (
            db.query(SocialPostReaction.post_id, SocialPostReaction.kind, func.count(SocialPostReaction.id))
            .filter(SocialPostReaction.post_id.in_(post_ids))
            .group_by(SocialPostReaction.post_id, SocialPostReaction.kind)
            .all()
        )
        for pid, kind, n in rows:
            counts[pid][kind] = n

        for r in (
            db.query(SocialPostReaction)
            .filter(SocialPostReaction.post_id.in_(post_ids), SocialPostReaction.user_id == me)
            .all()
        ):
            mine[r.post_id] = r.kind

    author_ids = {p.user_id for p in posts}
    users = {u.id: u for u in db.query(User).filter(User.id.in_(author_ids)).all()} if author_ids else {}

    data = []
    for p in posts:
        c = counts[p.id]
        data.append({
            "id": p.id,
            "content": p.content or "",
            "image_url": p.image_url,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "comment_count": p.comment_count or 0,
            "is_mine": p.user_id == me,
            "author": _person(users.get(p.user_id)),
            "reactions": {**c, "total": sum(c.values())},
            "my_reaction": mine.get(p.id),
        })

    return {
        "status": "success",
        "total": total,
        "page": page,
        "limit": limit,
        "has_next": page * limit < total,
        "data": data,
    }


# ============================================================================
# Set and remove my reaction
# ============================================================================

@router.post("/posts/{post_id}/react")
def set_reaction(
    post_id: int,
    payload: ReactionIn,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _me(current_user)
    post = db.query(SocialPost).filter(SocialPost.id == post_id, SocialPost.is_approved == True).first()
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")

    row = (
        db.query(SocialPostReaction)
        .filter(SocialPostReaction.post_id == post_id, SocialPostReaction.user_id == me)
        .first()
    )
    if row is None:
        db.add(SocialPostReaction(post_id=post_id, user_id=me, kind=payload.kind))
    else:
        row.kind = payload.kind
        row.created_at = datetime.utcnow()

    _commit(db, "Set reaction", "Could not save your reaction")
    return {"status": "success", "data": {"post_id": post_id, "my_reaction": payload.kind}}


@router.delete("/posts/{post_id}/react")
def clear_reaction(
    post_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = _me(current_user)
    row = (
        db.query(SocialPostReaction)
        .filter(SocialPostReaction.post_id == post_id, SocialPostReaction.user_id == me)
        .first()
    )
    if row is not None:
        db.delete(row)
        _commit(db, "Clear reaction", "Could not remove your reaction")
    return {"status": "success", "data": {"post_id": post_id, "my_reaction": None}}