# ============================================================================
# Rating Routes
# ============================================================================
# File: app/routes/ratings.py
# Purpose: Rating analytics and dashboard endpoints
# Status: Production-Ready ✅

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
import logging

from app.database import get_db
from app.models import Rating, RatingType, Session as SessionModel, Speaker, Resource, User
from app.schemas import (
    RatingResponse, RatingDistribution, RatingDashboardResponse,
    ErrorResponse
)
from app.routes.users import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Ratings"])


# ============================================================================
# SCHEMAS & SERIALIZATION HELPER
# ============================================================================

class RatingCreateSchema(BaseModel):
    session_id: int
    score: int
    review: Optional[str] = None


def _serialize_rating(rating: Rating):
    """
    Safely serialize a Rating ORM object using Pydantic v2 model_validate
    with a dictionary fallback if target_id or enum fields are null in DB.
    """
    try:
        return RatingResponse.model_validate(rating)
    except Exception:
        r_type = getattr(rating, "rating_type", None)
        r_type_val = r_type.value if hasattr(r_type, "value") else (str(r_type) if r_type else "session")
        return {
            "id": getattr(rating, "id", 0),
            "user_id": getattr(rating, "user_id", 0),
            "session_id": getattr(rating, "session_id", None),
            "speaker_id": getattr(rating, "speaker_id", None),
            "resource_id": getattr(rating, "resource_id", None),
            "target_id": getattr(rating, "target_id", None) or getattr(rating, "session_id", None) or 0,
            "rating_type": r_type_val,
            "score": getattr(rating, "score", 0) or 0,
            "feedback": getattr(rating, "feedback", None) or "",
            "created_at": rating.created_at.isoformat() if getattr(rating, "created_at", None) else datetime.utcnow().isoformat()
        }


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
    """
    try:
        ratings = db.query(Rating).order_by(Rating.created_at.desc()).limit(50).all()

        ratings_data = [
            _serialize_rating(rating) for rating in ratings
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
    """
    try:
        all_ratings = db.query(Rating).all()

        total_ratings = len(all_ratings)
        average_rating = (
            sum((r.score or 0) for r in all_ratings) / total_ratings
            if all_ratings else 0
        )

        distribution = {
            "five_stars": len([r for r in all_ratings if r.score == 5]),
            "four_stars": len([r for r in all_ratings if r.score == 4]),
            "three_stars": len([r for r in all_ratings if r.score == 3]),
            "two_stars": len([r for r in all_ratings if r.score == 2]),
            "one_star": len([r for r in all_ratings if r.score == 1]),
        }

        recent_ratings = db.query(Rating).order_by(
            Rating.created_at.desc()
        ).limit(10).all()

        recent_data = [
            _serialize_rating(r) for r in recent_ratings
        ]

        ratings_by_type = {}
        for rating_type in RatingType:
            matching = [r for r in all_ratings if r.rating_type == rating_type]
            count = len(matching)
            avg = sum((r.score or 0) for r in matching) / count if count > 0 else 0
            ratings_by_type[rating_type.value] = {
                "count": count,
                "average": round(avg, 2)
            }

        summary_obj = {
            "total_ratings": total_ratings,
            "average_rating": round(average_rating, 2),
            "distribution": distribution
        }

        return {
            "summary": summary_obj,
            "data": summary_obj,
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
    Get ratings filtered by entity type (handles singular & plural e.g. session/sessions)
    """
    try:
        # Normalize plural strings like 'sessions' -> 'SESSION', 'speakers' -> 'SPEAKER'
        normalized = entity_type.strip().lower()
        if normalized.endswith("s"):
            normalized = normalized[:-1]

        enum_key = normalized.upper()
        rating_type = getattr(RatingType, enum_key, None)

        # If the enum member doesn't exist in RatingType (e.g. RESOURCE), return empty stats safely
        if rating_type is None:
            return {
                "entity_type": entity_type,
                "total": 0,
                "average": 0,
                "distribution": {
                    "five_stars": 0,
                    "four_stars": 0,
                    "three_stars": 0,
                    "two_stars": 0,
                    "one_star": 0,
                },
                "recent": [],
                "data": []
            }

        ratings = db.query(Rating).filter(
            Rating.rating_type == rating_type
        ).all()

        total = len(ratings)
        average = sum((r.score or 0) for r in ratings) / total if total > 0 else 0

        distribution = {
            "five_stars": len([r for r in ratings if r.score == 5]),
            "four_stars": len([r for r in ratings if r.score == 4]),
            "three_stars": len([r for r in ratings if r.score == 3]),
            "two_stars": len([r for r in ratings if r.score == 2]),
            "one_star": len([r for r in ratings if r.score == 1]),
        }

        ratings_data = [
            _serialize_rating(r) for r in ratings[:20]
        ]

        return {
            "entity_type": entity_type,
            "total": total,
            "average": round(average, 2),
            "distribution": distribution,
            "recent": ratings_data,
            "data": ratings_data
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get ratings by type error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch ratings"
        )


# ============================================================================
# CREATE RATING/REVIEW
# ============================================================================

@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED, include_in_schema=False)
def create_rating(
    rating: RatingCreateSchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Attendee rates a session"""
    try:
        new_rating = Rating(
            session_id=rating.session_id,
            target_id=rating.session_id,
            user_id=current_user.id,
            rating_type=RatingType.SESSION,
            score=rating.score,
            feedback=rating.review,
            created_at=datetime.utcnow()
        )
        db.add(new_rating)
        db.commit()
        db.refresh(new_rating)

        return {
            "message": "Rating submitted successfully",
            "rating_id": new_rating.id
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Rating creation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit rating"
        )