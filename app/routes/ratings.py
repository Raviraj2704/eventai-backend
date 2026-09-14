# ============================================================================
# Rating Routes
# ============================================================================
# File: app/routes/ratings.py
# Purpose: Rating analytics and dashboard endpoints
# Status: Production-Ready ✅

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import datetime
import logging

from app.database import get_db
from app.models import Rating, RatingType, Session as SessionModel, Speaker, Resource
from app.schemas import (
    RatingResponse, RatingDistribution, RatingDashboardResponse,
    ErrorResponse
)
from app.routes.users import get_current_user


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/ratings", tags=["Ratings"])


# ============================================================================
# GET ALL RATINGS
# ============================================================================

@router.get(
    "",
    response_model=dict
)
async def get_ratings(
    db: Session = Depends(get_db)
):
    """
    Get all ratings (paginated)
    
    Args:
        db: Database session
    
    Returns:
        dict: Ratings list
    """
    try:
        ratings = db.query(Rating).order_by(Rating.created_at.desc()).limit(50).all()
        
        ratings_data = [
            RatingResponse.from_attributes(rating) for rating in ratings
        ]
        
        return {
            "total": len(ratings_data),
            "data": ratings_data
        }
    
    except Exception as e:
        logger.error(f"Get ratings error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch ratings"
        )


# ============================================================================
# GET RATING DASHBOARD
# ============================================================================

@router.get(
    "/dashboard/overview",
    response_model=dict
)
async def get_rating_dashboard(
    db: Session = Depends(get_db)
):
    """
    Get rating dashboard with aggregated statistics
    
    Args:
        db: Database session
    
    Returns:
        dict: Dashboard data with charts
    """
    try:
        # Get all ratings
        all_ratings = db.query(Rating).all()
        
        # Calculate overall stats
        total_ratings = len(all_ratings)
        average_rating = sum(r.score for r in all_ratings) / total_ratings if all_ratings else 0
        
        # Rating distribution
        distribution = {
            "five_stars": len([r for r in all_ratings if r.score == 5]),
            "four_stars": len([r for r in all_ratings if r.score == 4]),
            "three_stars": len([r for r in all_ratings if r.score == 3]),
            "two_stars": len([r for r in all_ratings if r.score == 2]),
            "one_star": len([r for r in all_ratings if r.score == 1]),
        }
        
        # Recent ratings
        recent_ratings = db.query(Rating).order_by(
            Rating.created_at.desc()
        ).limit(10).all()
        
        recent_data = [
            RatingResponse.from_attributes(r) for r in recent_ratings
        ]
        
        # Ratings by type
        ratings_by_type = {}
        for rating_type in RatingType:
            count = len([r for r in all_ratings if r.rating_type == rating_type])
            avg = sum(r.score for r in all_ratings if r.rating_type == rating_type) / count if count > 0 else 0
            ratings_by_type[rating_type.value] = {
                "count": count,
                "average": round(avg, 2)
            }
        
        return {
            "summary": {
                "total_ratings": total_ratings,
                "average_rating": round(average_rating, 2),
                "distribution": distribution
            },
            "by_type": ratings_by_type,
            "recent_feedback": recent_data,
            "charts": {
                "distribution": distribution,
                "by_type": ratings_by_type
            }
        }
    
    except Exception as e:
        logger.error(f"Get rating dashboard error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch dashboard"
        )


# ============================================================================
# GET RATINGS BY ENTITY TYPE
# ============================================================================

@router.get(
    "/entity/{entity_type}",
    response_model=dict
)
async def get_ratings_by_type(
    entity_type: str,
    db: Session = Depends(get_db)
):
    """
    Get ratings filtered by entity type
    
    Args:
        entity_type: Type of entity (session/speaker/resource/event)
        db: Database session
    
    Returns:
        dict: Filtered ratings
    """
    try:
        # Map entity type
        rating_type_map = {
            "session": RatingType.SESSION,
            "speaker": RatingType.SPEAKER,
            "resource": RatingType.RESOURCE,
            "event": RatingType.EVENT,
            "experience": RatingType.EXPERIENCE,
            "partner": RatingType.PARTNER
        }
        
        if entity_type not in rating_type_map:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid entity type"
            )
        
        rating_type = rating_type_map[entity_type]
        ratings = db.query(Rating).filter(
            Rating.rating_type == rating_type
        ).all()
        
        # Calculate stats
        total = len(ratings)
        average = sum(r.score for r in ratings) / total if total > 0 else 0
        
        # Distribution
        distribution = {
            "five_stars": len([r for r in ratings if r.score == 5]),
            "four_stars": len([r for r in ratings if r.score == 4]),
            "three_stars": len([r for r in ratings if r.score == 3]),
            "two_stars": len([r for r in ratings if r.score == 2]),
            "one_star": len([r for r in ratings if r.score == 1]),
        }
        
        ratings_data = [
            RatingResponse.from_attributes(r) for r in ratings[:20]
        ]
        
        return {
            "entity_type": entity_type,
            "total": total,
            "average": round(average, 2),
            "distribution": distribution,
            "recent": ratings_data
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get ratings by type error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch ratings"
        )