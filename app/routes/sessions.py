# ============================================================================
# Session Routes
# ============================================================================
# File: app/routes/sessions.py
# Purpose: Session management and attendance endpoints
# Status: Production-Ready ✅

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
import logging

from app.database import get_db
from app.models import (
    Session as SessionModel, SessionAttendance, User, Speaker,
    Rating, RatingType, Leaderboard
)
from app.schemas import (
    SessionResponse, SessionDetailResponse, SessionAttendanceRequest,
    SessionCheckInRequest, SessionRatingRequest, SessionListRequest,
    ErrorResponse
)
from app.routes.users import get_current_user


logger = logging.getLogger(__name__)
router = APIRouter(tags=["Sessions"])

# ============================================================================
# SCHEMAS
# ============================================================================

class SessionCreateSchema(BaseModel):
    title: str
    description: str
    session_type: str
    start_time: datetime
    end_time: datetime
    location: str
    capacity: int
    category: Optional[str] = None

class SessionUpdateSchema(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None


# ============================================================================
# CREATE A NEW SESSION
# ============================================================================

@router.post("", response_model=dict)
@router.post("/", response_model=dict, include_in_schema=False)
def create_session(
    session: SessionCreateSchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
   """Only speakers or admins can create sessions"""
    # Safe checks that work whether current_user is a dict or an ORM object
   user_role = getattr(current_user, "role", None) or (current_user.get("role") if isinstance(current_user, dict) else None)
   is_admin = getattr(current_user, "is_admin", False) or (current_user.get("is_admin", False) if isinstance(current_user, dict) else False)
   user_id = getattr(current_user, "id", None) or (current_user.get("id") if isinstance(current_user, dict) else None)

   if user_role not in ["speaker", "admin"] and not is_admin:
        raise HTTPException(status_code=403, detail="Not authorized to create sessions")

   try:
        new_session = SessionModel(
            title=session.title,
            description=session.description,
            session_type=session.session_type,
            start_time=session.start_time,
            end_time=session.end_time,
            location=session.location,
            capacity=session.capacity,
            category=session.category,
            is_published=True,
            actual_attendees=0
        )
        db.add(new_session)
        db.commit()
        db.refresh(new_session)
        return {"message": "Session successfully created!", "session_id": new_session.id}
   except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# UPDATE A SESSION
# ============================================================================

@router.put("/{session_id}", response_model=dict)
def update_session(
    session_id: int,
    session: SessionUpdateSchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Only speaker who created can update"""
    try:
        db_session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        
        if not db_session:
            raise HTTPException(status_code=404, detail="Session not found")
            
        if db_session.speaker_id != current_user.id:
            raise HTTPException(status_code=403, detail="Can only update your own sessions")
        
        if session.title is not None:
            db_session.title = session.title
        if session.description is not None:
            db_session.description = session.description
            
        db.commit()
        db.refresh(db_session)
        return {"message": "Session updated successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# GET ALL SESSIONS
# ============================================================================

@router.get(
    "",
    response_model=dict,
    responses={400: {"model": ErrorResponse}}
)
async def get_sessions(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    category: Optional[str] = None,
    difficulty: Optional[str] = None,
    search: Optional[str] = None,
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all sessions with filtering and pagination
    """
    try:
        query = db.query(SessionModel).filter(SessionModel.is_published == True)
        
        # Build filters
        if category:
            query = query.filter(SessionModel.category == category)
        
        if difficulty:
            query = query.filter(SessionModel.difficulty_level == difficulty)
        
        if search:
            query = query.filter(
                or_(
                    SessionModel.title.ilike(f"%{search}%"),
                    SessionModel.description.ilike(f"%{search}%")
                )
            )
        
        # Sort by start time (upcoming first)
        query = query.order_by(SessionModel.start_time.asc())
        
        # Get total count
        total = query.count()
        
        # Pagination
        sessions = query.offset((page - 1) * limit).limit(limit).all()
        
        # Format response
        sessions_data = []
        for session in sessions:
            session_data = SessionResponse.model_validate(session)
            
            # Check if user attended
            if current_user:
                attendance = db.query(SessionAttendance).filter(
                    and_(
                        SessionAttendance.session_id == session.id,
                        SessionAttendance.user_id == current_user.id
                    )
                ).first()
                
                session_data.is_attended_by_user = attendance is not None
                if attendance:
                    session_data.user_rating = attendance.rating
            
            sessions_data.append(session_data)
        
        return {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit,
            "has_next": page * limit < total,
            "has_prev": page > 1,
            "data": sessions_data
        }
    
    except Exception as e:
        logger.error(f"Get sessions error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch sessions"
        )


# ============================================================================
# GET SESSION BY ID
# ============================================================================

@router.get(
    "/{session_id}",
    response_model=SessionDetailResponse,
    responses={404: {"model": ErrorResponse}}
)
async def get_session_by_id(
    session_id: int,
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get session by ID with full details
    """
    try:
        session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        # Build response
        detail = SessionDetailResponse.model_validate(session)
        
        # Add speakers
        detail.speakers = [
            {"id": s.id, "name": f"{s.user.first_name} {s.user.last_name}".strip()}
            for s in session.speakers
        ]
        
        # Check if user attended
        if current_user:
            attendance = db.query(SessionAttendance).filter(
                and_(
                    SessionAttendance.session_id == session_id,
                    SessionAttendance.user_id == current_user.id
                )
            ).first()
            
            detail.is_attended_by_user = attendance is not None
            if attendance:
                detail.user_rating = attendance.rating
        
        return detail
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get session error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch session"
        )


# ============================================================================
# ATTEND SESSION
# ============================================================================

@router.post(
    "/{session_id}/attend",
    response_model=dict,
    responses={
        401: {"model": ErrorResponse}, 
        404: {"model": ErrorResponse}, 
        409: {"model": ErrorResponse}
    }
)
async def attend_session(
    session_id: int,
    request: SessionAttendanceRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Register user for a session
    """
    try:
        session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        if session.capacity and session.actual_attendees >= session.capacity:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Session is at full capacity"
            )
        
        existing = db.query(SessionAttendance).filter(
            and_(
                SessionAttendance.session_id == session_id,
                SessionAttendance.user_id == current_user.id
            )
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Already registered for this session"
            )
        
        attendance = SessionAttendance(
            session_id=session_id,
            user_id=current_user.id,
            attended=False,
            created_at=datetime.utcnow()
        )
        
        session.actual_attendees += 1
        
        db.add(attendance)
        db.commit()
        
        logger.info(f"User {current_user.id} registered for session {session_id}")
        
        return {
            "message": "Session registration successful",
            "session_id": session_id,
            "user_id": current_user.id
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Session attendance error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register for session"
        )


# ============================================================================
# CHECK IN TO SESSION
# ============================================================================

@router.post(
    "/{session_id}/check-in",
    response_model=dict,
    responses={
        401: {"model": ErrorResponse}, 
        404: {"model": ErrorResponse}, 
        409: {"model": ErrorResponse}
    }
)
async def check_in_session(
    session_id: int,
    request: SessionCheckInRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Check in to a session
    """
    try:
        attendance = db.query(SessionAttendance).filter(
            and_(
                SessionAttendance.session_id == session_id,
                SessionAttendance.user_id == current_user.id
            )
        ).first()
        
        if not attendance:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Not registered for this session"
            )
        
        attendance.attended = True
        attendance.check_in_time = datetime.utcnow()
        
        leaderboard = db.query(Leaderboard).filter(
            Leaderboard.user_id == current_user.id
        ).first()
        
        if leaderboard:
            leaderboard.total_points += 10
            leaderboard.sessions_attended += 1
            leaderboard.last_activity = datetime.utcnow()
        
        db.commit()
        
        logger.info(f"User {current_user.id} checked in to session {session_id}")
        
        return {
            "message": "Check-in successful",
            "check_in_time": attendance.check_in_time,
            "points_earned": 10
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Check-in error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check in"
        )


# ============================================================================
# RATE SESSION
# ============================================================================

@router.post(
    "/{session_id}/rate",
    response_model=dict,
    responses={
        401: {"model": ErrorResponse}, 
        404: {"model": ErrorResponse}, 
        409: {"model": ErrorResponse}
    }
)
async def rate_session(
    session_id: int,
    request: SessionRatingRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Rate a session
    """
    try:
        session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        attendance = db.query(SessionAttendance).filter(
            and_(
                SessionAttendance.session_id == session_id,
                SessionAttendance.user_id == current_user.id
            )
        ).first()
        
        if not attendance:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Must attend session to rate it"
            )
        
        attendance.rating = request.score
        
        existing_rating = db.query(Rating).filter(
            and_(
                Rating.user_id == current_user.id,
                Rating.rating_type == RatingType.SESSION,
                Rating.session_id == session_id
            )
        ).first()
        
        if existing_rating:
            existing_rating.score = request.score
            existing_rating.feedback = request.feedback
            existing_rating.updated_at = datetime.utcnow()
        else:
            new_rating = Rating(
                user_id=current_user.id,
                rating_type=RatingType.SESSION,
                session_id=session_id,
                target_id=session_id,
                score=request.score,
                feedback=request.feedback,
                created_at=datetime.utcnow()
            )
            db.add(new_rating)
        
        all_ratings = db.query(Rating).filter(
            and_(
                Rating.rating_type == RatingType.SESSION,
                Rating.session_id == session_id
            )
        ).all()
        
        if all_ratings:
            total_score = sum(r.score for r in all_ratings)
            session.average_rating = total_score / len(all_ratings)
            session.total_ratings = len(all_ratings)
        
        leaderboard = db.query(Leaderboard).filter(
            Leaderboard.user_id == current_user.id
        ).first()
        
        if leaderboard:
            leaderboard.total_points += 5
            leaderboard.sessions_rated += 1
            leaderboard.last_activity = datetime.utcnow()
        
        db.commit()
        
        logger.info(f"User {current_user.id} rated session {session_id}")
        
        return {
            "message": "Rating submitted successfully",
            "average_rating": session.average_rating,
            "total_ratings": session.total_ratings,
            "points_earned": 5
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Session rating error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit rating"
        )