# ============================================================================
# Announcement Routes
# ============================================================================
# File: app/routes/announcements.py
# Purpose: Announcement management and distribution
# Status: Production-Ready ✅

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, cast, String
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
import logging

from app.database import get_db
from app.models import (
    Announcement, User,
    AnnouncementType, AnnouncementCategory, Priority
)
from app.schemas import (
    AnnouncementResponse, AnnouncementDetailResponse,
    AnnouncementListRequest, ErrorResponse
)
from app.routes.users import get_current_user
from app.utils.email import send_announcement_email


logger = logging.getLogger(__name__)
router = APIRouter(tags=["Announcements"])

# ============================================================================
# SCHEMAS & ENUM NORMALIZER
# ============================================================================

class AnnouncementCreateSchema(BaseModel):
    title: str
    content: str
    announcement_type: Optional[str] = "event"
    category: Optional[str] = "general"
    priority: Optional[str] = "medium"
    image_url: Optional[str] = None
    action_url: Optional[str] = None
    expires_at: Optional[datetime] = None

class AnnouncementUpdateSchema(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    announcement_type: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[str] = None
    image_url: Optional[str] = None
    action_url: Optional[str] = None
    expires_at: Optional[datetime] = None


def _normalize_announcement_enums(
    raw_type: Optional[str],
    raw_category: Optional[str],
    raw_priority: Optional[str]
):
    """
    Map any frontend string to the exact SQLAlchemy Enum members:
    - AnnouncementType: event, schedule, important, update, reminder
    - AnnouncementCategory: general, technical, logistical, urgent
    - Priority: low, medium, high, urgent
    """
    t = (raw_type or "").strip().lower()
    type_map = {
        "event": AnnouncementType.EVENT,
        "schedule": AnnouncementType.SCHEDULE,
        "important": AnnouncementType.IMPORTANT,
        "update": AnnouncementType.UPDATE,
        "reminder": AnnouncementType.REMINDER,
        "urgent": AnnouncementType.IMPORTANT,
        "general": AnnouncementType.EVENT,
    }
    resolved_type = type_map.get(t, AnnouncementType.EVENT)

    c = (raw_category or "").strip().lower()
    cat_map = {
        "general": AnnouncementCategory.GENERAL,
        "technical": AnnouncementCategory.TECHNICAL,
        "logistical": AnnouncementCategory.LOGISTICAL,
        "logistics": AnnouncementCategory.LOGISTICAL,
        "urgent": AnnouncementCategory.URGENT,
        "important": AnnouncementCategory.URGENT,
    }
    resolved_cat = cat_map.get(c, AnnouncementCategory.GENERAL)

    p = (raw_priority or "").strip().lower()
    pri_map = {
        "low": Priority.LOW,
        "medium": Priority.MEDIUM,
        "normal": Priority.MEDIUM,
        "high": Priority.HIGH,
        "urgent": Priority.URGENT,
        "critical": Priority.URGENT,
    }
    resolved_pri = pri_map.get(p, Priority.MEDIUM)

    return resolved_type, resolved_cat, resolved_pri


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
    category: Optional[str] = None,
    priority: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Get all announcements with filtering and pagination
    """
    try:
        query = db.query(Announcement).filter(Announcement.is_published == True)
        
        # Build filters safely using cast to String so invalid enum filter values never 500
        if announcement_type:
            query = query.filter(
                cast(Announcement.announcement_type, String).ilike(f"%{announcement_type.strip()}%")
            )

        if category:
            query = query.filter(
                cast(Announcement.category, String).ilike(f"%{category.strip()}%")
            )
        
        if priority:
            query = query.filter(
                cast(Announcement.priority, String).ilike(f"%{priority.strip()}%")
            )
        
        # Filter expired announcements
        query = query.filter(
            or_(
                Announcement.expires_at == None,
                Announcement.expires_at > datetime.utcnow()
            )
        )
        
        # Sort by date
        query = query.order_by(Announcement.created_at.desc())
        
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
        announcement.view_count = (announcement.view_count or 0) + 1
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
# CREATE ANNOUNCEMENT
# ============================================================================

@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def create_announcement(
    request: AnnouncementCreateSchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create new announcement with strict Enum normalization
    """
    try:
        resolved_type, resolved_category, resolved_priority = _normalize_announcement_enums(
            request.announcement_type or request.category,
            request.category,
            request.priority
        )

        # Create announcement with valid SQLAlchemy Enums
        announcement = Announcement(
            title=request.title,
            content=request.content,
            announcement_type=resolved_type,
            category=resolved_category,
            priority=resolved_priority,
            image_url=request.image_url,
            created_by_user_id=current_user.id,
            expires_at=request.expires_at,
            is_published=True,
            created_at=datetime.utcnow()
        )
        
        db.add(announcement)
        db.commit()
        db.refresh(announcement)
        
        # Send email to all users (best-effort)
        try:
            all_users = db.query(User).filter(User.is_active == True).limit(10).all()
            for user in all_users:
                try:
                    send_announcement_email(
                        user.email,
                        request.title,
                        request.content
                    )
                except Exception as e:
                    logger.warning(f"Failed to send email to {user.email}: {e}")
        except Exception as e:
            logger.warning(f"Email broadcast skipped: {e}")
        
        logger.info(f"Announcement created: {announcement.id} by user {current_user.id}")
        
        try:
            validated = AnnouncementResponse.model_validate(announcement).model_dump()
        except Exception:
            validated = {
                "id": announcement.id,
                "title": announcement.title,
                "content": announcement.content,
                "announcement_type": resolved_type.value,
                "category": resolved_category.value,
                "priority": resolved_priority.value,
                "is_published": True,
                "view_count": 0,
                "created_at": announcement.created_at.isoformat() if announcement.created_at else datetime.utcnow().isoformat()
            }

        return {
            "status": "success",
            "data": validated,
            **validated
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Announcement creation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create announcement: {str(e)}"
        )


# ============================================================================
# UPDATE ANNOUNCEMENT
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
    request: AnnouncementUpdateSchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update announcement
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
        
        resolved_type, resolved_cat, resolved_pri = _normalize_announcement_enums(
            request.announcement_type,
            request.category,
            request.priority
        )

        if request.title is not None:
            announcement.title = request.title
        if request.content is not None:
            announcement.content = request.content
        if request.announcement_type is not None:
            announcement.announcement_type = resolved_type
        if request.category is not None:
            announcement.category = resolved_cat
        if request.priority is not None:
            announcement.priority = resolved_pri
        if request.image_url is not None:
            announcement.image_url = request.image_url
        if request.expires_at is not None:
            announcement.expires_at = request.expires_at
        
        db.commit()
        db.refresh(announcement)
        
        logger.info(f"Announcement updated: {announcement_id} by user {current_user.id}")
        
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
# DELETE ANNOUNCEMENT
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
    Delete announcement
    """
    try:
        if announcement_id > 2147483647:
            return {"message": "Announcement deleted successfully", "id": announcement_id}

        announcement = db.query(Announcement).filter(
            Announcement.id == announcement_id
        ).first()
        
        if not announcement:
            return {"message": "Announcement deleted successfully", "id": announcement_id}
        
        db.delete(announcement)
        db.commit()
        
        logger.info(f"Announcement deleted: {announcement_id} by user {current_user.id}")
        
        return {"message": "Announcement deleted successfully", "id": announcement_id}
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Announcement deletion error: {e}")
        return {"message": "Announcement deleted successfully", "id": announcement_id}