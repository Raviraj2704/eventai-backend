# ============================================================================
# Learning Paths Routes
# ============================================================================
# File: app/routes/learning_paths.py
# Purpose: Learning path management and progress tracking
# Status: Production-Ready ✅

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from datetime import datetime
from typing import Optional
import logging

from app.database import get_db
from app.models import (
    LearningPath, LearningModule, UserLearningProgress, User,
    Rating, RatingType, Leaderboard
)
from app.schemas import (
    LearningPathResponse, LearningPathDetailResponse,
    LearningModuleResponse, LearningPathEnrollRequest,
    LearningPathProgressRequest, LearningPathListRequest,
    ErrorResponse
)
from app.routes.users import get_current_user


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/learning-paths", tags=["Learning Paths"])


# ============================================================================
# GET ALL LEARNING PATHS
# ============================================================================

@router.get(
    "",
    response_model=dict,
    responses={400: {"model": ErrorResponse}}
)
async def get_learning_paths(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    difficulty: Optional[str] = None,
    search: Optional[str] = None,
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all learning paths
    
    Args:
        page: Page number
        limit: Results per page
        difficulty: Filter by difficulty
        search: Search by title/description
        current_user: Optional authenticated user
        db: Database session
    
    Returns:
        dict: Paginated learning paths
    """
    try:
        query = db.query(LearningPath).filter(LearningPath.is_published == True)
        
        if difficulty:
            query = query.filter(LearningPath.difficulty_level == difficulty)
        
        if search:
            query = query.filter(
                or_(
                    LearningPath.title.ilike(f"%{search}%"),
                    LearningPath.description.ilike(f"%{search}%")
                )
            )
        
        query = query.order_by(LearningPath.created_at.desc())
        
        total = query.count()
        paths = query.offset((page - 1) * limit).limit(limit).all()
        
        paths_data = []
        for path in paths:
            path_resp = LearningPathResponse.model_validate(path)
            
            # Check user enrollment
            if current_user:
                progress = db.query(UserLearningProgress).filter(
                    and_(
                        UserLearningProgress.user_id == current_user.id,
                        UserLearningProgress.learning_path_id == path.id
                    )
                ).first()
                
                if progress:
                    path_resp.user_progress = {
                        "enrolled": True,
                        "progress_percentage": progress.progress_percentage,
                        "modules_completed": progress.modules_completed,
                        "is_completed": progress.is_completed
                    }
            
            paths_data.append(path_resp)
        
        return {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit,
            "has_next": page * limit < total,
            "has_prev": page > 1,
            "data": paths_data
        }
    
    except Exception as e:
        logger.error(f"Get learning paths error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch learning paths"
        )


# ============================================================================
# GET LEARNING PATH BY ID
# ============================================================================

@router.get(
    "/{path_id}",
    response_model=LearningPathDetailResponse,
    responses={404: {"model": ErrorResponse}}
)
async def get_learning_path_by_id(
    path_id: int,
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get learning path by ID with modules
    
    Args:
        path_id: Learning path ID
        current_user: Optional authenticated user
        db: Database session
    
    Returns:
        LearningPathDetailResponse: Path details
    """
    try:
        path = db.query(LearningPath).filter(LearningPath.id == path_id).first()
        
        if not path:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Learning path not found"
            )
        
        detail = LearningPathDetailResponse.model_validate(path)
        
        # Add modules
        modules = db.query(LearningModule).filter(
            LearningModule.learning_path_id == path_id
        ).order_by(LearningModule.module_order).all()
        
        detail.modules = [
            LearningModuleResponse.model_validate(module) for module in modules
        ]
        
        # Check user enrollment
        if current_user:
            progress = db.query(UserLearningProgress).filter(
                and_(
                    UserLearningProgress.user_id == current_user.id,
                    UserLearningProgress.learning_path_id == path_id
                )
            ).first()
            
            if progress:
                detail.user_progress = {
                    "enrolled": True,
                    "progress_percentage": progress.progress_percentage,
                    "modules_completed": progress.modules_completed,
                    "started_at": progress.started_at,
                    "is_completed": progress.is_completed,
                    "certificate_issued": progress.certificate_issued
                }
        
        return detail
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get learning path error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch learning path"
        )


# ============================================================================
# ENROLL IN LEARNING PATH
# ============================================================================

@router.post(
    "/{path_id}/enroll",
    response_model=dict,
    responses={
        401: {"model": ErrorResponse}, 
        404: {"model": ErrorResponse}, 
        409: {"model": ErrorResponse}
    }
)
async def enroll_learning_path(
    path_id: int,
    request: LearningPathEnrollRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Enroll user in learning path
    
    Args:
        path_id: Learning path ID
        request: Enrollment request
        current_user: Authenticated user
        db: Database session
    
    Returns:
        dict: Success message
    """
    try:
        # Get path
        path = db.query(LearningPath).filter(LearningPath.id == path_id).first()
        if not path:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Learning path not found"
            )
        
        # Check if already enrolled
        existing = db.query(UserLearningProgress).filter(
            and_(
                UserLearningProgress.user_id == current_user.id,
                UserLearningProgress.learning_path_id == path_id
            )
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Already enrolled in this path"
            )
        
        # Create enrollment
        progress = UserLearningProgress(
            user_id=current_user.id,
            learning_path_id=path_id,
            progress_percentage=0,
            modules_completed=0,
            started_at=datetime.utcnow()
        )
        
        # Update path enrollments count
        path.enrollments += 1
        
        db.add(progress)
        db.commit()
        
        logger.info(f"User {current_user.id} enrolled in path {path_id}")
        
        return {
            "message": "Successfully enrolled in learning path",
            "path_id": path_id
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Enroll error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to enroll in learning path"
        )


# ============================================================================
# UPDATE LEARNING PATH PROGRESS
# ============================================================================

@router.put(
    "/{path_id}/progress",
    response_model=dict,
    responses={
        401: {"model": ErrorResponse}, 
        404: {"model": ErrorResponse}, 
        409: {"model": ErrorResponse}
    }
)
async def update_learning_progress(
    path_id: int,
    request: LearningPathProgressRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update user progress in learning path
    
    Args:
        path_id: Learning path ID
        request: Progress data
        current_user: Authenticated user
        db: Database session
    
    Returns:
        dict: Updated progress
    """
    try:
        # Get progress
        progress = db.query(UserLearningProgress).filter(
            and_(
                UserLearningProgress.user_id == current_user.id,
                UserLearningProgress.learning_path_id == path_id
            )
        ).first()
        
        if not progress:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Not enrolled in this path"
            )
        
        # Update progress
        progress.progress_percentage = request.progress_percentage
        progress.modules_completed = request.modules_completed
        progress.updated_at = datetime.utcnow()
        
        # Check if completed
        path = db.query(LearningPath).filter(LearningPath.id == path_id).first()
        if request.progress_percentage == 100 and not progress.is_completed:
            progress.is_completed = True
            progress.completed_at = datetime.utcnow()
            
            # Award certificate
            progress.certificate_issued = True
            
            # Award points
            leaderboard = db.query(Leaderboard).filter(
                Leaderboard.user_id == current_user.id
            ).first()
            
            if leaderboard:
                leaderboard.total_points += 50  # 50 points for completing path
                leaderboard.last_activity = datetime.utcnow()
        
        db.commit()
        
        logger.info(f"Progress updated for user {current_user.id} in path {path_id}")
        
        return {
            "message": "Progress updated successfully",
            "progress_percentage": progress.progress_percentage,
            "modules_completed": progress.modules_completed,
            "is_completed": progress.is_completed,
            "certificate_issued": progress.certificate_issued
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Update progress error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update progress"
        )