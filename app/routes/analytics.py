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
router = APIRouter(tags=["Analytics"])


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
    Get analytics dashboard
    """
    try:
        total_users = db.query(User).filter(User.is_active == True).count()
        total_sessions = db.query(SessionModel).count()
        total_attendees = db.query(SessionAttendance).filter(
            SessionAttendance.attended == True
        ).count()

        ratings = db.query(Rating).all()
        avg_rating = sum(r.score for r in ratings) / len(ratings) if ratings else 0

        total_posts = db.query(SocialPost).count()
        total_points = db.query(Leaderboard).count()

        # Safely fetch top sessions without relying on missing actual_attendees column
        top_sessions = db.query(SessionModel).order_by(SessionModel.id.desc()).limit(5).all()

        top_sessions_data = []
        for s in top_sessions:
            attendee_count = getattr(s, "actual_attendees", None)
            if attendee_count is None:
                attendee_count = getattr(s, "current_attendees", None)
            if attendee_count is None:
                attendee_count = db.query(SessionAttendance).filter(
                    SessionAttendance.session_id == s.id
                ).count()

            session_rating = getattr(s, "average_rating", None)
            if session_rating is None:
                s_ratings = [r.score for r in ratings if getattr(r, "session_id", None) == s.id]
                session_rating = round(sum(s_ratings) / len(s_ratings), 2) if s_ratings else 0.0

            top_sessions_data.append({
                "id": s.id,
                "title": s.title,
                "attendees": attendee_count,
                "rating": session_rating
            })

        # Top users by engagement
        top_users = db.query(Leaderboard).order_by(
            Leaderboard.total_points.desc()
        ).limit(5).all()

        top_users_data = []
        for lu in top_users:
            u = getattr(lu, "user", None)
            if not u and getattr(lu, "user_id", None):
                u = db.query(User).filter(User.id == lu.user_id).first()
            top_users_data.append({
                "user_id": u.id if u else getattr(lu, "user_id", 0),
                "username": getattr(u, "username", None) or getattr(u, "email", "User"),
                "points": getattr(lu, "total_points", 0),
                "tier": getattr(lu, "tier", "bronze")
            })

        return {
            "summary": {
                "total_users": total_users,
                "total_sessions": total_sessions,
                "total_attendees": total_attendees,
                "average_rating": round(avg_rating, 2),
                "total_posts": total_posts,
                "total_engagement_score": total_points
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
    """
    try:
        sessions_attended = db.query(SessionAttendance).filter(
            SessionAttendance.user_id == current_user.id,
            SessionAttendance.attended == True
        ).count()

        ratings_given = db.query(Rating).filter(
            Rating.user_id == current_user.id
        ).count()

        posts_created = db.query(SocialPost).filter(
            SocialPost.user_id == current_user.id
        ).count()

        leaderboard = db.query(Leaderboard).filter(
            Leaderboard.user_id == current_user.id
        ).first()

        user_points = getattr(leaderboard, "total_points", 0) if leaderboard else 0

        return {
            "message": "success",
            "data": {
                "sessions_attended": sessions_attended,
                "ratings_given": ratings_given,
                "posts_created": posts_created,
                "total_points": user_points,
                "current_rank": db.query(Leaderboard).filter(
                    Leaderboard.total_points > user_points
                ).count() + 1,
                "current_tier": getattr(leaderboard, "tier", "bronze") if leaderboard else "bronze",
                "badges_earned": getattr(leaderboard, "badges_earned", 0) if leaderboard else 0,
                "challenges_completed": getattr(leaderboard, "challenges_completed", 0) if leaderboard else 0
            }
        }

    except Exception as e:
        logger.error(f"Get user analytics error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch user analytics"
        )