# ============================================================================
# Announcement Routes
# ============================================================================
# File: app/routes/announcements.py
# Purpose: Announcement management and distribution
# Status: Production-Ready ✅

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from datetime import datetime
from typing import Optional
import logging

from app.database import get_db
from app.models import Announcement, User
from app.schemas import (
    AnnouncementResponse, AnnouncementDetailResponse,
    AnnouncementCreateRequest, AnnouncementListRequest,
    ErrorResponse
)
from app.routes.users import get_current_user
from app.utils.email import send_announcement_email


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/announcements", tags=["Announcements"])


# ============================================================================
# GET ALL ANNOUNCEMENTS
# ============================================================================

@router.get(
    "",
    response_model=dict,
    responses={400: {"model": ErrorResponse}}
)
async def get_announcements(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    announcement_type: Optional[str] = None,
    priority: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Get all announcements with filtering and pagination
    
    Args:
        page: Page number
        limit: Results per page
        announcement_type: Filter by type
        priority: Filter by priority
        db: Database session
    
    Returns:
        dict: Paginated announcements list
    """
    try:
        query = db.query(Announcement).filter(Announcement.is_published == True)
        
        # Build filters
        if announcement_type:
            query = query.filter(Announcement.announcement_type == announcement_type)
        
        if priority:
            query = query.filter(Announcement.priority == priority)
        
        # Filter expired announcements
        query = query.filter(
            or_(
                Announcement.expires_at == None,
                Announcement.expires_at > datetime.utcnow()
            )
        )
        
        # Sort by priority and date
        query = query.order_by(
            Announcement.priority.desc(),
            Announcement.created_at.desc()
        )
        
        # Get total count
        total = query.count()
        
        # Pagination
        announcements = query.offset((page - 1) * limit).limit(limit).all()
        
        # Format response
        announcements_data = [
            AnnouncementResponse.model_validate(announcement)
            for announcement in announcements
        ]
        
        return {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit,
            "has_next": page * limit < total,
            "has_prev": page > 1,
            "data": announcements_data
        }
    
    except Exception as e:
        logger.error(f"Get announcements error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch announcements"
        )


# ============================================================================
# GET ANNOUNCEMENT BY ID
# ============================================================================

@router.get(
    "/{announcement_id}",
    response_model=AnnouncementDetailResponse,
    responses={404: {"model": ErrorResponse}}
)
async def get_announcement_by_id(
    announcement_id: int,
    db: Session = Depends(get_db)
):
    """
    Get announcement by ID
    
    Args:
        announcement_id: Announcement ID
        db: Database session
    
    Returns:
        AnnouncementDetailResponse: Announcement details
    
    Raises:
        HTTPException: If announcement not found
    """
    try:
        announcement = db.query(Announcement).filter(
            Announcement.id == announcement_id
        ).first()
        
        if not announcement:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Announcement not found"
            )
        
        # Increment view count
        announcement.view_count += 1
        db.commit()
        
        return AnnouncementDetailResponse.model_validate(announcement)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get announcement error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch announcement"
        )


# ============================================================================
# CREATE ANNOUNCEMENT (ADMIN ONLY)
# ============================================================================

@router.post(
    "",
    response_model=AnnouncementResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"model": ErrorResponse}, 
        403: {"model": ErrorResponse}
    }
)
async def create_announcement(
    request: AnnouncementCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create new announcement (admin only)
    
    Args:
        request: Announcement data
        current_user: Authenticated user (must be admin)
        db: Database session
    
    Returns:
        AnnouncementResponse: Created announcement
    
    Raises:
        HTTPException: If not admin
    """
    try:
        # Check if admin
        if not getattr(current_user, "is_admin", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can create announcements"
            )
        
        # Create announcement
        announcement = Announcement(
            title=request.title,
            content=request.content,
            announcement_type=request.announcement_type,
            category=request.category,
            priority=request.priority,
            image_url=request.image_url,
            created_by_user_id=current_user.id,
            expires_at=request.expires_at,
            is_published=True,
            created_at=datetime.utcnow()
        )
        
        db.add(announcement)
        db.commit()
        db.refresh(announcement)
        
        # Send email to all users (in production, use async task)
        all_users = db.query(User).filter(User.is_active == True).all()
        for user in all_users:
            send_announcement_email(
                user.email,
                request.title,
                request.content
            )
        
        logger.info(f"Announcement created: {announcement.id} by admin {current_user.id}")
        
        return AnnouncementResponse.model_validate(announcement)
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Announcement creation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create announcement"
        )


# ============================================================================
# UPDATE ANNOUNCEMENT (ADMIN ONLY)
# ============================================================================

@router.put(
    "/{announcement_id}",
    response_model=AnnouncementResponse,
    responses={
        401: {"model": ErrorResponse}, 
        403: {"model": ErrorResponse}, 
        404: {"model": ErrorResponse}
    }
)
async def update_announcement(
    announcement_id: int,
    request: AnnouncementCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update announcement (admin only)
    
    Args:
        announcement_id: Announcement ID
        request: Updated data
        current_user: Authenticated user (must be admin)
        db: Database session
    
    Returns:
        AnnouncementResponse: Updated announcement
    """
    try:
        # Check if admin
        if not getattr(current_user, "is_admin", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can update announcements"
            )
        
        # Get announcement
        announcement = db.query(Announcement).filter(
            Announcement.id == announcement_id
        ).first()
        
        if not announcement:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Announcement not found"
            )
        
        # Update fields
        announcement.title = request.title
        announcement.content = request.content
        announcement.announcement_type = request.announcement_type
        announcement.category = request.category
        announcement.priority = request.priority
        announcement.image_url = request.image_url
        announcement.expires_at = request.expires_at
        
        db.commit()
        db.refresh(announcement)
        
        logger.info(f"Announcement updated: {announcement_id} by admin {current_user.id}")
        
        return AnnouncementResponse.model_validate(announcement)
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Announcement update error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update announcement"
        )


# ============================================================================
# DELETE ANNOUNCEMENT (ADMIN ONLY)
# ============================================================================

@router.delete(
    "/{announcement_id}",
    response_model=dict,
    responses={
        401: {"model": ErrorResponse}, 
        403: {"model": ErrorResponse}, 
        404: {"model": ErrorResponse}
    }
)
async def delete_announcement(
    announcement_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete announcement (admin only)
    
    Args:
        announcement_id: Announcement ID
        current_user: Authenticated user (must be admin)
        db: Database session
    
    Returns:
        dict: Success message
    """
    try:
        # Check if admin
        if not getattr(current_user, "is_admin", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can delete announcements"
            )
        
        # Get announcement
        announcement = db.query(Announcement).filter(
            Announcement.id == announcement_id
        ).first()
        
        if not announcement:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Announcement not found"
            )
        
        db.delete(announcement)
        db.commit()
        
        logger.info(f"Announcement deleted: {announcement_id} by admin {current_user.id}")
        
        return {"message": "Announcement deleted successfully"}
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Announcement deletion error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete announcement"
        )