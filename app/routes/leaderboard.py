# ============================================================================
# Leaderboard Routes
# ============================================================================
# File: app/routes/leaderboard.py
# Purpose: Leaderboard rankings and user statistics
# Status: Production-Ready ✅

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
import logging

from app.database import get_db
from app.models import Leaderboard, User, Badge
from app.schemas import (
    LeaderboardUserResponse, UserLeaderboardStatsResponse,
    LeaderboardListRequest, ErrorResponse
)
from app.routes.users import get_current_user


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/leaderboard", tags=["Leaderboard"])


# ============================================================================
# GET LEADERBOARD
# ============================================================================

@router.get(
    "",
    response_model=dict,
    responses={400: {"model": ErrorResponse}}
)
async def get_leaderboard(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    time_period: Optional[str] = "all",  # all, month, week
    tier: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Get global leaderboard with rankings
    
    Args:
        page: Page number
        limit: Results per page
        time_period: Filter by time period
        tier: Filter by tier
        db: Database session
    
    Returns:
        dict: Ranked users list
    """
    try:
        # Get leaderboard entries
        query = db.query(Leaderboard).join(User).filter(User.is_active == True)
        
        if tier:
            query = query.filter(Leaderboard.tier == tier)
        
        # Order by points
        query = query.order_by(Leaderboard.total_points.desc())
        
        # Get total count
        total = query.count()
        
        # Pagination
        leaderboard_entries = query.offset((page - 1) * limit).limit(limit).all()
        
        # Format response with rank
        leaderboard_data = []
        for idx, entry in enumerate(leaderboard_entries, start=(page - 1) * limit + 1):
            entry.rank = idx
            leaderboard_data.append(LeaderboardUserResponse.model_validate(entry))
        
        return {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit,
            "has_next": page * limit < total,
            "has_prev": page > 1,
            "data": leaderboard_data
        }
    
    except Exception as e:
        logger.error(f"Get leaderboard error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch leaderboard"
        )


# ============================================================================
# GET USER LEADERBOARD STATS
# ============================================================================

@router.get(
    "/me",
    response_model=dict,
    responses={
        401: {"model": ErrorResponse}, 
        404: {"model": ErrorResponse}
    }
)
async def get_user_leaderboard_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get current user's leaderboard statistics
    
    Args:
        current_user: Authenticated user
        db: Database session
    
    Returns:
        dict: User leaderboard stats
    """
    try:
        # Get user leaderboard entry
        leaderboard = db.query(Leaderboard).filter(
            Leaderboard.user_id == current_user.id
        ).first()
        
        if not leaderboard:
            # Create entry if doesn't exist
            leaderboard = Leaderboard(
                user_id=current_user.id,
                total_points=0,
                rank=None,
                tier="bronze"
            )
            db.add(leaderboard)
            db.commit()
        
        # Get user's rank
        rank = db.query(Leaderboard).filter(
            Leaderboard.total_points > leaderboard.total_points
        ).count() + 1
        
        # Get earned badges
        badges = db.query(Badge).join(
            Badge.users
        ).filter(Badge.users.contains(current_user)).all()
        
        badges_data = [
            {
                "id": badge.id,
                "name": badge.name,
                "icon_url": badge.icon_url,
                "rarity": badge.rarity
            }
            for badge in badges
        ]
        
        return {
            "message": "success",
            "data": {
                "user_id": current_user.id,
                "username": current_user.username,
                "total_points": leaderboard.total_points,
                "rank": rank,
                "tier": leaderboard.tier,
                "badges_earned": len(badges_data),
                "challenges_completed": leaderboard.challenges_completed,
                "sessions_attended": leaderboard.sessions_attended,
                "sessions_rated": leaderboard.sessions_rated,
                "posts_created": leaderboard.posts_created,
                "earned_badges": badges_data,
                "last_activity": leaderboard.last_activity
            }
        }
    
    except Exception as e:
        logger.error(f"Get user stats error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch statistics"
        )


# ============================================================================
# GET LEADERBOARD BY TIER
# ============================================================================

@router.get(
    "/tier/{tier_name}",
    response_model=dict,
    responses={400: {"model": ErrorResponse}}
)
async def get_leaderboard_by_tier(
    tier_name: str,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """
    Get leaderboard filtered by tier
    
    Args:
        tier_name: Tier name (bronze/silver/gold/platinum/diamond)
        page: Page number
        limit: Results per page
        db: Database session
    
    Returns:
        dict: Tier leaderboard
    """
    try:
        valid_tiers = ["bronze", "silver", "gold", "platinum", "diamond"]
        
        if tier_name.lower() not in valid_tiers:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid tier. Must be one of: {', '.join(valid_tiers)}"
            )
        
        query = db.query(Leaderboard).filter(
            Leaderboard.tier == tier_name.lower()
        ).order_by(Leaderboard.total_points.desc())
        
        total = query.count()
        leaderboard_entries = query.offset((page - 1) * limit).limit(limit).all()
        
        leaderboard_data = [
            LeaderboardUserResponse.model_validate(entry)
            for entry in leaderboard_entries
        ]
        
        return {
            "tier": tier_name.lower(),
            "total": total,
            "page": page,
            "limit": limit,
            "data": leaderboard_data
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get tier leaderboard error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch tier leaderboard"
        )


# ============================================================================
# GET NEARBY USERS IN LEADERBOARD
# ============================================================================

@router.get(
    "/nearby",
    response_model=dict,
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse}
    }
)
async def get_nearby_leaderboard(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get leaderboard with user in center
    
    Args:
        current_user: Authenticated user
        db: Database session
    
    Returns:
        dict: Nearby users
    """
    try:
        # Get user's leaderboard entry
        user_leaderboard = db.query(Leaderboard).filter(
            Leaderboard.user_id == current_user.id
        ).first()
        
        if not user_leaderboard:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User leaderboard entry not found"
            )
        
        # Get user's rank
        rank = db.query(Leaderboard).filter(
            Leaderboard.total_points > user_leaderboard.total_points
        ).count() + 1
        
        # Get nearby entries (2 above, current, 2 below)
        nearby = db.query(Leaderboard).order_by(
            Leaderboard.total_points.desc()
        ).offset(max(0, rank - 3)).limit(5).all()
        
        nearby_data = [
            LeaderboardUserResponse.model_validate(entry)
            for entry in nearby
        ]
        
        return {
            "your_rank": rank,
            "nearby_users": nearby_data
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get nearby leaderboard error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch nearby users"
        )