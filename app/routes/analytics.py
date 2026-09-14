# ============================================================================
# Analytics Routes
# ============================================================================
# File: app/routes/analytics.py
# Purpose: Event analytics and dashboards
# Status: Production-Ready ✅

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime
import logging

from app.database import get_db
from app.models import (
    User, Session as SessionModel, SessionAttendance, Rating,
    SocialPost, Leaderboard
)
from app.schemas import ErrorResponse
from app.routes.users import get_current_user


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])


# ============================================================================
# GET ANALYTICS DASHBOARD
# ============================================================================

@router.get(
    "/dashboard",
    response_model=dict,
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}}
)
async def get_analytics_dashboard(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get analytics dashboard (admin only)
    
    Args:
        current_user: Authenticated user (must be admin)
        db: Database session
    
    Returns:
        dict: Analytics data
    """
    try:
        # Check if admin
        if not current_user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can view analytics"
            )
        
        # Count stats
        total_users = db.query(User).filter(User.is_active == True).count()
        total_sessions = db.query(SessionModel).filter(
            SessionModel.is_published == True
        ).count()
        total_attendees = db.query(SessionAttendance).filter(
            SessionAttendance.attended == True
        ).count()
        
        # Average rating
        ratings = db.query(Rating).all()
        avg_rating = sum(r.score for r in ratings) / len(ratings) if ratings else 0
        
        # Total engagement
        total_posts = db.query(SocialPost).count()
        total_points = db.query(Leaderboard).count()
        
        # Top sessions by attendance
        top_sessions = db.query(SessionModel).filter(
            SessionModel.is_published == True
        ).order_by(SessionModel.actual_attendees.desc()).limit(5).all()
        
        top_sessions_data = [
            {
                "id": s.id,
                "title": s.title,
                "attendees": s.actual_attendees,
                "rating": s.average_rating
            }
            for s in top_sessions
        ]
        
        # Top users by engagement
        top_users = db.query(Leaderboard).order_by(
            Leaderboard.total_points.desc()
        ).limit(5).all()
        
        top_users_data = [
            {
                "user_id": lu.user.id,
                "username": lu.user.username,
                "points": lu.total_points,
                "tier": lu.tier
            }
            for lu in top_users
        ]
        
        return {
            "summary": {
                "total_users": total_users,
                "total_sessions": total_sessions,
                "total_attendees": total_attendees,
                "average_rating": round(avg_rating, 2),
                "total_posts": total_posts,
                "total_engagement_score": db.query(Leaderboard).count()
            },
            "top_sessions": top_sessions_data,
            "top_users": top_users_data,
            "timestamp": datetime.utcnow()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get analytics error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch analytics"
        )


# ============================================================================
# GET USER ANALYTICS
# ============================================================================

@router.get(
    "/user/me",
    response_model=dict,
    responses={401: {"model": ErrorResponse}}
)
async def get_user_analytics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get current user's personal analytics
    
    Args:
        current_user: Authenticated user
        db: Database session
    
    Returns:
        dict: User analytics
    """
    try:
        # Get session attendance
        sessions_attended = db.query(SessionAttendance).filter(
            SessionAttendance.user_id == current_user.id,
            SessionAttendance.attended == True
        ).count()
        
        # Get ratings given
        ratings_given = db.query(Rating).filter(
            Rating.user_id == current_user.id
        ).count()
        
        # Get posts created
        posts_created = db.query(SocialPost).filter(
            SocialPost.user_id == current_user.id
        ).count()
        
        # Get leaderboard stats
        leaderboard = db.query(Leaderboard).filter(
            Leaderboard.user_id == current_user.id
        ).first()
        
        return {
            "message": "success",
            "data": {
                "sessions_attended": sessions_attended,
                "ratings_given": ratings_given,
                "posts_created": posts_created,
                "total_points": leaderboard.total_points if leaderboard else 0,
                "current_rank": db.query(Leaderboard).filter(
                    Leaderboard.total_points > (leaderboard.total_points if leaderboard else 0)
                ).count() + 1,
                "current_tier": leaderboard.tier if leaderboard else "bronze",
                "badges_earned": leaderboard.badges_earned if leaderboard else 0,
                "challenges_completed": leaderboard.challenges_completed if leaderboard else 0
            }
        }
    
    except Exception as e:
        logger.error(f"Get user analytics error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch user analytics"
        )