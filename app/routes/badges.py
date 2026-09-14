# ============================================================================
# Badge Routes
# ============================================================================
# File: app/routes/badges.py
# Purpose: Badge achievements and management
# Status: Production-Ready ✅

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
import logging

from app.database import get_db
from app.models import Badge, User, UserBadge
from app.schemas import (
    BadgeResponse, BadgeDetailResponse, EarnedBadgeResponse,
    ErrorResponse
)
from app.routes.users import get_current_user


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/badges", tags=["Badges"])


# ============================================================================
# GET ALL BADGES
# ============================================================================

@router.get(
    "",
    response_model=dict,
    responses={400: {"model": ErrorResponse}}
)
async def get_badges(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    rarity: Optional[str] = None,
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all badges
    
    Args:
        page: Page number
        limit: Results per page
        rarity: Filter by rarity
        current_user: Optional authenticated user
        db: Database session
    
    Returns:
        dict: Paginated badges list
    """
    try:
        query = db.query(Badge).filter(Badge.is_active == True)
        
        if rarity:
            query = query.filter(Badge.rarity == rarity)
        
        query = query.order_by(Badge.rarity.desc(), Badge.name.asc())
        
        total = query.count()
        badges = query.offset((page - 1) * limit).limit(limit).all()
        
        badges_data = []
        for badge in badges:
            badge_resp = BadgeResponse.from_attributes(badge)
            
            # Check if earned by user
            if current_user:
                earned = db.query(UserBadge).filter(
                    and_(
                        UserBadge.user_id == current_user.id,
                        UserBadge.badge_id == badge.id
                    )
                ).first()
                badge_resp.is_earned_by_user = earned is not None
            
            badges_data.append(badge_resp)
        
        return {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit,
            "has_next": page * limit < total,
            "has_prev": page > 1,
            "data": badges_data
        }
    
    except Exception as e:
        logger.error(f"Get badges error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch badges"
        )


# ============================================================================
# GET BADGE BY ID
# ============================================================================

@router.get(
    "/{badge_id}",
    response_model=BadgeDetailResponse,
    responses={404: {"model": ErrorResponse}}
)
async def get_badge_by_id(
    badge_id: int,
    db: Session = Depends(get_db)
):
    """
    Get badge by ID with details
    
    Args:
        badge_id: Badge ID
        db: Database session
    
    Returns:
        BadgeDetailResponse: Badge details
    """
    try:
        badge = db.query(Badge).filter(Badge.id == badge_id).first()
        
        if not badge:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Badge not found"
            )
        
        # Count who earned this badge
        earned_count = db.query(UserBadge).filter(
            UserBadge.badge_id == badge_id
        ).count()
        
        detail = BadgeDetailResponse.from_attributes(badge)
        detail.earned_by_count = earned_count
        
        return detail
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get badge error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch badge"
        )


# ============================================================================
# GET USER'S EARNED BADGES
# ============================================================================

@router.get(
    "/earned",
    response_model=dict,
    responses={401: {"model": ErrorResponse}}
)
async def get_earned_badges(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get badges earned by current user
    
    Args:
        current_user: Authenticated user
        db: Database session
    
    Returns:
        dict: Earned badges list
    """
    try:
        # Get user badges
        user_badges = db.query(UserBadge).filter(
            UserBadge.user_id == current_user.id
        ).order_by(UserBadge.earned_at.desc()).all()
        
        badges_data = [
            {
                "id": ub.badge.id,
                "name": ub.badge.name,
                "icon_url": ub.badge.icon_url,
                "rarity": ub.badge.rarity,
                "earned_at": ub.earned_at,
                "points_reward": ub.badge.points_reward
            }
            for ub in user_badges
        ]
        
        return {
            "total_earned": len(badges_data),
            "badges": badges_data
        }
    
    except Exception as e:
        logger.error(f"Get earned badges error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch earned badges"
        )


# ============================================================================
# GET BADGE LEADERBOARD (WHO EARNED MOST)
# ============================================================================

@router.get(
    "/{badge_id}/leaderboard",
    response_model=dict,
    responses={404: {"model": ErrorResponse}}
)
async def get_badge_leaderboard(
    badge_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """
    Get users who earned a specific badge
    
    Args:
        badge_id: Badge ID
        page: Page number
        limit: Results per page
        db: Database session
    
    Returns:
        dict: Users with badge
    """
    try:
        # Get badge
        badge = db.query(Badge).filter(Badge.id == badge_id).first()
        if not badge:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Badge not found"
            )
        
        # Get users with badge
        query = db.query(UserBadge).filter(
            UserBadge.badge_id == badge_id
        ).order_by(UserBadge.earned_at.desc())
        
        total = query.count()
        user_badges = query.offset((page - 1) * limit).limit(limit).all()
        
        users_data = [
            {
                "user_id": ub.user.id,
                "username": ub.user.username,
                "avatar_url": ub.user.avatar_url,
                "earned_at": ub.earned_at
            }
            for ub in user_badges
        ]
        
        return {
            "badge_id": badge_id,
            "badge_name": badge.name,
            "total_users": total,
            "page": page,
            "limit": limit,
            "users": users_data
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get badge leaderboard error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch badge leaderboard"
        )


# Import for and_ operator
from sqlalchemy import and_