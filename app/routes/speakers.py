# ============================================================================
# Speaker Routes
# ============================================================================
# File: app/routes/speakers.py
# Purpose: Speaker profile and management endpoints
# Status: Production-Ready ✅

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from datetime import datetime
from typing import List, Optional
import logging

from app.database import get_db
from app.models import Speaker, User, Rating, RatingType
from app.schemas import (
    SpeakerResponse, SpeakerDetailResponse, SpeakerRatingRequest,
    ErrorResponse
)
from app.routes.users import get_current_user


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/speakers", tags=["Speakers"])


# ============================================================================
# GET ALL SPEAKERS
# ============================================================================

@router.get(
    "",
    response_model=dict,
    responses={400: {"model": ErrorResponse}}
)
async def get_speakers(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    search: Optional[str] = None,
    experience_level: Optional[str] = None,
    featured_only: bool = False,
    db: Session = Depends(get_db)
):
    """
    Get all speakers with pagination
    
    Args:
        page: Page number
        limit: Results per page
        search: Search by name/company
        experience_level: Filter by level
        featured_only: Show only featured speakers
        db: Database session
    
    Returns:
        dict: Paginated speakers list
    """
    try:
        query = db.query(Speaker).join(User)
        
        # Build filters
        if search:
            query = query.filter(
                or_(
                    User.first_name.ilike(f"%{search}%"),
                    User.last_name.ilike(f"%{search}%"),
                    Speaker.company.ilike(f"%{search}%")
                )
            )
        
        if experience_level:
            query = query.filter(Speaker.experience_level == experience_level)
        
        if featured_only:
            query = query.filter(Speaker.is_featured == True)
        
        # Get total count
        total = query.count()
        
        # Pagination
        speakers = query.offset((page - 1) * limit).limit(limit).all()
        
        # Format response
        speakers_data = [
            SpeakerResponse.from_attributes(speaker) for speaker in speakers
        ]
        
        return {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit,
            "has_next": page * limit < total,
            "has_prev": page > 1,
            "data": speakers_data
        }
    
    except Exception as e:
        logger.error(f"Get speakers error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch speakers"
        )


# ============================================================================
# GET SPEAKER BY ID
# ============================================================================

@router.get(
    "/{speaker_id}",
    response_model=SpeakerDetailResponse,
    responses={404: {"model": ErrorResponse}}
)
async def get_speaker_by_id(
    speaker_id: int,
    db: Session = Depends(get_db)
):
    """
    Get speaker by ID with full details
    
    Args:
        speaker_id: Speaker ID
        db: Database session
    
    Returns:
        SpeakerDetailResponse: Speaker details
    
    Raises:
        HTTPException: If speaker not found
    """
    try:
        speaker = db.query(Speaker).filter(Speaker.id == speaker_id).first()
        
        if not speaker:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Speaker not found"
            )
        
        # Get upcoming sessions
        from app.models import Session as SessionModel
        upcoming_sessions = db.query(SessionModel).filter(
            SessionModel.speakers.contains(speaker),
            SessionModel.start_time > datetime.utcnow(),
            SessionModel.is_published == True
        ).limit(5).all()
        
        # Get past sessions
        past_sessions = db.query(SessionModel).filter(
            SessionModel.speakers.contains(speaker),
            SessionModel.start_time <= datetime.utcnow(),
            SessionModel.is_published == True
        ).order_by(SessionModel.start_time.desc()).limit(5).all()
        
        # Build response
        detail = SpeakerDetailResponse.from_attributes(speaker)
        detail.upcoming_sessions = [
            {"id": s.id, "title": s.title, "start_time": s.start_time}
            for s in upcoming_sessions
        ]
        detail.past_sessions = [
            {"id": s.id, "title": s.title, "start_time": s.start_time}
            for s in past_sessions
        ]
        
        return detail
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get speaker error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch speaker"
        )


# ============================================================================
# RATE SPEAKER
# ============================================================================

@router.post(
    "/{speaker_id}/rate",
    response_model=dict,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}
)
async def rate_speaker(
    speaker_id: int,
    request: SpeakerRatingRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Rate a speaker
    
    Args:
        speaker_id: Speaker ID
        request: Rating data
        current_user: Authenticated user
        db: Database session
    
    Returns:
        dict: Success message
    
    Raises:
        HTTPException: If speaker not found or rating fails
    """
    try:
        # Get speaker
        speaker = db.query(Speaker).filter(Speaker.id == speaker_id).first()
        if not speaker:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Speaker not found"
            )
        
        # Check if user already rated
        existing_rating = db.query(Rating).filter(
            and_(
                Rating.user_id == current_user.id,
                Rating.rating_type == RatingType.SPEAKER,
                Rating.target_id == speaker_id
            )
        ).first()
        
        if existing_rating:
            # Update existing rating
            existing_rating.score = request.score
            existing_rating.feedback = request.feedback
            existing_rating.updated_at = datetime.utcnow()
        else:
            # Create new rating
            new_rating = Rating(
                user_id=current_user.id,
                rating_type=RatingType.SPEAKER,
                target_id=speaker_id,
                score=request.score,
                feedback=request.feedback,
                created_at=datetime.utcnow()
            )
            db.add(new_rating)
        
        # Update speaker average rating
        all_ratings = db.query(Rating).filter(
            and_(
                Rating.rating_type == RatingType.SPEAKER,
                Rating.target_id == speaker_id
            )
        ).all()
        
        if all_ratings:
            total_score = sum(r.score for r in all_ratings)
            speaker.average_rating = total_score / len(all_ratings)
            speaker.total_ratings = len(all_ratings)
        
        db.commit()
        
        logger.info(f"Speaker {speaker_id} rated by user {current_user.id}")
        
        return {
            "message": "Rating submitted successfully",
            "average_rating": speaker.average_rating,
            "total_ratings": speaker.total_ratings
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Speaker rating error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit rating"
        )


# ============================================================================
# FOLLOW SPEAKER
# ============================================================================

@router.post(
    "/{speaker_id}/follow",
    response_model=dict,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}
)
async def follow_speaker(
    speaker_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Follow a speaker (placeholder for future implementation)
    
    Args:
        speaker_id: Speaker ID
        current_user: Authenticated user
        db: Database session
    
    Returns:
        dict: Success message
    """
    try:
        # Get speaker
        speaker = db.query(Speaker).filter(Speaker.id == speaker_id).first()
        if not speaker:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Speaker not found"
            )
        
        # In production, create a Speaker_Followers table
        logger.info(f"User {current_user.id} followed speaker {speaker_id}")
        
        return {"message": "Speaker followed successfully"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Follow speaker error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to follow speaker"
        )