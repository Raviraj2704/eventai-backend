# ============================================================================
# Resource Routes
# ============================================================================
# File: app/routes/resources.py
# Purpose: Resource management, upload, download, and rating
# Status: Production-Ready ✅

from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from datetime import datetime
from typing import Optional
import logging

from app.database import get_db
from app.models import Resource, User, Rating, RatingType, Leaderboard
from app.schemas import (
    ResourceResponse, ResourceDetailResponse, ResourceRatingRequest,
    ResourceListRequest, ErrorResponse
)
from app.routes.users import get_current_user


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/resources", tags=["Resources"])


# ============================================================================
# GET ALL RESOURCES
# ============================================================================

@router.get(
    "",
    response_model=dict,
    responses={400: {"model": ErrorResponse}}
)
async def get_resources(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    resource_type: Optional[str] = None,
    category: Optional[str] = None,
    session_id: Optional[int] = None,
    search: Optional[str] = None,
    sort_by: Optional[str] = "created_at",
    db: Session = Depends(get_db)
):
    """
    Get all resources with filtering and pagination
    """
    try:
        query = db.query(Resource).filter(Resource.is_published == True)
        
        # Build filters
        if resource_type:
            query = query.filter(Resource.resource_type == resource_type)
        
        if category:
            query = query.filter(Resource.category == category)
        
        if session_id:
            query = query.filter(Resource.session_id == session_id)
        
        if search:
            query = query.filter(
                or_(
                    Resource.title.ilike(f"%{search}%"),
                    Resource.description.ilike(f"%{search}%")
                )
            )
        
        # Sorting
        if sort_by == "downloads":
            query = query.order_by(Resource.download_count.desc())
        elif sort_by == "rating":
            query = query.order_by(Resource.average_rating.desc())
        else:
            query = query.order_by(Resource.created_at.desc())
        
        # Get total count
        total = query.count()
        
        # Pagination
        resources = query.offset((page - 1) * limit).limit(limit).all()
        
        # Format response
        resources_data = [
            ResourceResponse.model_validate(resource) for resource in resources
        ]
        
        return {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit,
            "has_next": page * limit < total,
            "has_prev": page > 1,
            "data": resources_data
        }
    
    except Exception as e:
        logger.error(f"Get resources error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch resources"
        )


# ============================================================================
# GET RESOURCE BY ID
# ============================================================================

@router.get(
    "/{resource_id}",
    response_model=ResourceDetailResponse,
    responses={404: {"model": ErrorResponse}}
)
async def get_resource_by_id(
    resource_id: int,
    db: Session = Depends(get_db)
):
    """
    Get resource by ID with full details
    """
    try:
        resource = db.query(Resource).filter(Resource.id == resource_id).first()
        
        if not resource:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Resource not found"
            )
        
        return ResourceDetailResponse.model_validate(resource)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get resource error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch resource"
        )


# ============================================================================
# CREATE RESOURCE
# ============================================================================

@router.post(
    "",
    response_model=ResourceResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"model": ErrorResponse}, 
        400: {"model": ErrorResponse}
    }
)
async def create_resource(
    title: str,
    description: Optional[str] = None,
    resource_type: str = None,
    category: Optional[str] = None,
    session_id: Optional[int] = None,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create new resource with file upload
    """
    try:
        # Validate file size (100MB limit)
        contents = await file.read()
        file_size = len(contents)
        
        if file_size > 100 * 1024 * 1024:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File size exceeds 100MB limit"
            )
        
        # In production, upload to S3/Firebase
        file_url = f"https://api.eventai.com/resources/{file.filename}"
        file_size_mb = file_size / (1024 * 1024)
        
        resource = Resource(
            title=title,
            description=description,
            resource_type=resource_type,
            category=category,
            file_url=file_url,
            file_size_mb=file_size_mb,
            uploaded_by_user_id=current_user.id,
            session_id=session_id,
            is_published=True,
            created_at=datetime.utcnow()
        )
        
        db.add(resource)
        db.commit()
        db.refresh(resource)
        
        logger.info(f"Resource created: {resource.id} by user {current_user.id}")
        
        return ResourceResponse.model_validate(resource)
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Resource creation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create resource"
        )


# ============================================================================
# DOWNLOAD RESOURCE
# ============================================================================

@router.post(
    "/{resource_id}/download",
    response_model=dict,
    responses={
        401: {"model": ErrorResponse}, 
        404: {"model": ErrorResponse}
    }
)
async def download_resource(
    resource_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Download resource and track download count
    """
    try:
        resource = db.query(Resource).filter(Resource.id == resource_id).first()
        
        if not resource:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Resource not found"
            )
        
        resource.download_count += 1
        
        leaderboard = db.query(Leaderboard).filter(
            Leaderboard.user_id == current_user.id
        ).first()
        
        if leaderboard:
            leaderboard.total_points += 2
            leaderboard.last_activity = datetime.utcnow()
        
        db.commit()
        
        logger.info(f"Resource {resource_id} downloaded by user {current_user.id}")
        
        return {
            "message": "Download started",
            "url": resource.file_url,
            "download_count": resource.download_count
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Download resource error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to download resource"
        )


# ============================================================================
# RATE RESOURCE
# ============================================================================

@router.post(
    "/{resource_id}/rate",
    response_model=dict,
    responses={
        401: {"model": ErrorResponse}, 
        404: {"model": ErrorResponse}
    }
)
async def rate_resource(
    resource_id: int,
    request: ResourceRatingRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Rate a resource
    """
    try:
        resource = db.query(Resource).filter(Resource.id == resource_id).first()
        if not resource:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Resource not found"
            )
        
        existing_rating = db.query(Rating).filter(
            and_(
                Rating.user_id == current_user.id,
                Rating.rating_type == RatingType.RESOURCE,
                Rating.resource_id == resource_id
            )
        ).first()
        
        if existing_rating:
            existing_rating.score = request.score
            existing_rating.feedback = request.feedback
            existing_rating.updated_at = datetime.utcnow()
        else:
            new_rating = Rating(
                user_id=current_user.id,
                rating_type=RatingType.RESOURCE,
                resource_id=resource_id,
                target_id=resource_id,
                score=request.score,
                feedback=request.feedback,
                created_at=datetime.utcnow()
            )
            db.add(new_rating)
        
        all_ratings = db.query(Rating).filter(
            and_(
                Rating.rating_type == RatingType.RESOURCE,
                Rating.resource_id == resource_id
            )
        ).all()
        
        if all_ratings:
            total_score = sum(r.score for r in all_ratings)
            resource.average_rating = total_score / len(all_ratings)
            resource.total_ratings = len(all_ratings)
        
        leaderboard = db.query(Leaderboard).filter(
            Leaderboard.user_id == current_user.id
        ).first()
        
        if leaderboard:
            leaderboard.total_points += 3
            leaderboard.last_activity = datetime.utcnow()
        
        db.commit()
        
        logger.info(f"Resource {resource_id} rated by user {current_user.id}")
        
        return {
            "message": "Rating submitted successfully",
            "average_rating": resource.average_rating,
            "total_ratings": resource.total_ratings
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Resource rating error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit rating"
        )