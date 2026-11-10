# ============================================================================
# Badge Routes
# File: app/routes/badges.py
# Purpose: Badge list, earned badges, badge detail, badge leaderboard
# ============================================================================

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Badge, Rarity, User, UserBadge
from app.routes.users import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Badges"])


def _enum_text(value, default: str = "") -> str:
    """Return enum values (or plain strings) as lowercase text."""
    if value is None:
        return default
    return str(getattr(value, "value", value)).lower()


def _badge_dict(badge: Badge) -> dict:
    return {
        "id": badge.id,
        "name": badge.name,
        "description": badge.description,
        "icon_url": badge.icon_url,
        "rarity": _enum_text(badge.rarity, "common"),
        "points_reward": badge.points_reward or 0,
        "created_at": badge.created_at,
    }


# ============================================================================
# GET ALL BADGES (logged-in users; marks which ones they have earned)
# ============================================================================

@router.get("", response_model=dict)
async def get_badges(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    rarity: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        query = db.query(Badge).filter(Badge.is_active == True)

        if rarity:
            try:
                rarity_value = Rarity(rarity.lower())
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Unknown rarity",
                )
            query = query.filter(Badge.rarity == rarity_value)

        query = query.order_by(Badge.name.asc())
        total = query.count()
        badges = query.offset((page - 1) * limit).limit(limit).all()

        earned_ids = {
            row.badge_id
            for row in db.query(UserBadge.badge_id)
            .filter(UserBadge.user_id == current_user.id)
            .all()
        }

        data = [
            {**_badge_dict(b), "is_earned_by_user": b.id in earned_ids}
            for b in badges
        ]

        return {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit,
            "has_next": page * limit < total,
            "has_prev": page > 1,
            "data": data,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get badges error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch badges",
        )


# ============================================================================
# GET BADGES EARNED BY CURRENT USER
# ============================================================================

@router.get("/earned", response_model=dict)
async def get_earned_badges(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        rows = (
            db.query(UserBadge, Badge)
            .join(Badge, Badge.id == UserBadge.badge_id)
            .filter(UserBadge.user_id == current_user.id)
            .order_by(UserBadge.earned_at.desc())
            .all()
        )

        badges_data = [
            {
                "id": badge.id,
                "name": badge.name,
                "icon_url": badge.icon_url,
                "rarity": _enum_text(badge.rarity, "common"),
                "earned_at": ub.earned_at,
                "points_reward": badge.points_reward or 0,
            }
            for ub, badge in rows
        ]

        return {"total_earned": len(badges_data), "badges": badges_data}

    except Exception as e:
        logger.error(f"Get earned badges error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch earned badges",
        )


# ============================================================================
# GET BADGE BY ID
# ============================================================================

@router.get("/{badge_id:int}", response_model=dict)
async def get_badge_by_id(
    badge_id: int,
    db: Session = Depends(get_db),
):
    try:
        badge = db.query(Badge).filter(Badge.id == badge_id).first()
        if not badge:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Badge not found",
            )

        recipients_count = (
            db.query(UserBadge).filter(UserBadge.badge_id == badge_id).count()
        )

        return {**_badge_dict(badge), "recipients_count": recipients_count}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get badge error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch badge",
        )


# ============================================================================
# GET BADGE LEADERBOARD (WHO EARNED IT)
# ============================================================================

@router.get("/{badge_id}/leaderboard", response_model=dict)
async def get_badge_leaderboard(
    badge_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    try:
        badge = db.query(Badge).filter(Badge.id == badge_id).first()
        if not badge:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Badge not found",
            )

        query = (
            db.query(UserBadge, User)
            .join(User, User.id == UserBadge.user_id)
            .filter(UserBadge.badge_id == badge_id)
            .order_by(UserBadge.earned_at.desc())
        )

        total = query.count()
        rows = query.offset((page - 1) * limit).limit(limit).all()

        users_data = [
            {
                "user_id": user.id,
                "username": user.username,
                "avatar_url": user.avatar_url,
                "earned_at": ub.earned_at,
            }
            for ub, user in rows
        ]

        return {
            "badge_id": badge_id,
            "badge_name": badge.name,
            "total_users": total,
            "page": page,
            "limit": limit,
            "users": users_data,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get badge leaderboard error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch badge leaderboard",
        )