# ============================================================================
# Activity Feed and Top Leaderboard (Production Ready)
# File: app/routes/activity_feed.py
#
# GET /api/v1/activity/feed?page=1&limit=10
#   Approved social posts with the author's name and photo, newest first.
#
# GET /api/v1/activity/leaderboard/top?limit=3
#   Top users by points, with name and profile photo, ranked 1..N.
# ============================================================================

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.models import Leaderboard, SocialPost, User
from app.routes.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


def _author_name(user) -> str:
    if user is None:
        return "Attendee"
    full = f"{user.first_name or ''} {user.last_name or ''}".strip()
    return full or user.username or "Attendee"


@router.get("/feed")
def get_activity_feed(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    try:
        query = (
            db.query(SocialPost)
            .filter(SocialPost.is_approved.is_(True))
            .order_by(SocialPost.created_at.desc(), SocialPost.id.desc())
        )
        total = query.count()
        posts = query.offset((page - 1) * limit).limit(limit).all()

        author_ids = {post.user_id for post in posts}
        authors = {}
        if author_ids:
            authors = {
                u.id: u
                for u in db.query(User).filter(User.id.in_(author_ids)).all()
            }

        data = []
        for post in posts:
            author = authors.get(post.user_id)
            data.append({
                "id": post.id,
                "user_id": post.user_id,
                "author_name": _author_name(author),
                "author_avatar_url": author.avatar_url if author else None,
                "content": post.content,
                "image_url": post.image_url,
                "like_count": post.like_count or 0,
                "comment_count": post.comment_count or 0,
                "created_at": post.created_at.isoformat() if post.created_at else None,
            })

        return {
            "status": "success",
            "total": total,
            "page": page,
            "limit": limit,
            "has_next": page * limit < total,
            "data": data,
        }
    except Exception as exc:
        logger.error("Get activity feed error: %s", exc)
        raise HTTPException(status_code=500, detail="Could not load the activity feed")


@router.get("/leaderboard/top")
def get_top_leaderboard(
    limit: int = Query(3, ge=1, le=10),
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    try:
        rows = (
            db.query(Leaderboard)
            .order_by(Leaderboard.total_points.desc(), Leaderboard.user_id.asc())
            .limit(limit)
            .all()
        )

        user_ids = [row.user_id for row in rows]
        users = {}
        if user_ids:
            users = {
                u.id: u
                for u in db.query(User).filter(User.id.in_(user_ids)).all()
            }

        data = []
        for index, row in enumerate(rows, start=1):
            user = users.get(row.user_id)
            data.append({
                "rank": index,
                "user_id": row.user_id,
                "name": _author_name(user),
                "avatar_url": user.avatar_url if user else None,
                "total_points": row.total_points or 0,
            })

        return {"status": "success", "data": data}
    except Exception as exc:
        logger.error("Get top leaderboard error: %s", exc)
        raise HTTPException(status_code=500, detail="Could not load the leaderboard")