# ============================================================================
# Announcement Routes
# File: app/routes/announcements.py
# GET    /api/v1/announcements            published announcements (everyone)
# GET    /api/v1/announcements/{id}       one announcement (everyone)
# POST   /api/v1/announcements            create (admin only)
# PUT    /api/v1/announcements/{id}       edit (admin only)
# DELETE /api/v1/announcements/{id}       delete (admin only)
# ============================================================================

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Announcement, User
from app.routes.users import get_current_user
from app.utils.email import send_announcement_email

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Announcements"])


# ============================================================================
# Schemas
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
    is_published: bool = True


class AnnouncementUpdateSchema(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    announcement_type: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[str] = None
    image_url: Optional[str] = None
    action_url: Optional[str] = None
    expires_at: Optional[datetime] = None
    is_published: Optional[bool] = None


# ============================================================================
# Helpers
# ============================================================================

TYPE_MAP = {
    "event": "event", "schedule": "schedule", "important": "important",
    "update": "update", "reminder": "reminder", "urgent": "important",
    "general": "event",
}
CATEGORY_MAP = {
    "general": "general", "technical": "technical", "logistical": "logistical",
    "logistics": "logistical", "urgent": "urgent", "important": "urgent",
}
PRIORITY_MAP = {
    "low": "low", "medium": "medium", "normal": "medium", "high": "high",
    "urgent": "urgent", "critical": "urgent",
}


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Only admins can manage announcements")
    return current_user


def _enum_value(v):
    return getattr(v, "value", v)


def _to_dict(a: Announcement) -> dict:
    return {
        "id": a.id,
        "title": a.title,
        "content": a.content,
        "message": a.content,
        "announcement_type": _enum_value(a.announcement_type),
        "category": _enum_value(a.category),
        "priority": _enum_value(a.priority),
        "image_url": a.image_url,
        "action_url": a.action_url,
        "is_published": bool(a.is_published),
        "view_count": a.view_count or 0,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "expires_at": a.expires_at.isoformat() if a.expires_at else None,
    }


def _send_emails(recipients: list) -> None:
    """Runs after the response is sent, so posting never waits on email."""
    for email, title, body in recipients:
        try:
            send_announcement_email(email, title, body)
        except Exception as e:
            logger.warning(f"Failed to send announcement email to {email}: {e}")


# ============================================================================
# List and detail (everyone)
# ============================================================================

@router.get("")
def list_announcements(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(Announcement).filter(
        Announcement.is_published == True,
        or_(Announcement.expires_at == None, Announcement.expires_at > datetime.utcnow()),
    )
    total = query.count()
    rows = (
        query.order_by(Announcement.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    return {
        "status": "success",
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": (total + limit - 1) // limit,
        "has_next": page * limit < total,
        "has_prev": page > 1,
        "data": [_to_dict(a) for a in rows],
    }


@router.get("/{announcement_id}")
def get_announcement(announcement_id: int, db: Session = Depends(get_db)):
    a = db.query(Announcement).filter(Announcement.id == announcement_id).first()
    if not a or not a.is_published:
        raise HTTPException(status_code=404, detail="Announcement not found")
    a.view_count = (a.view_count or 0) + 1
    db.commit()
    return {"status": "success", "data": _to_dict(a)}


# ============================================================================
# Create, edit, delete (admin only)
# ============================================================================

@router.post("", status_code=status.HTTP_201_CREATED)
def create_announcement(
    payload: AnnouncementCreateSchema,
    background_tasks: BackgroundTasks,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    title = payload.title.strip()
    content = payload.content.strip()
    if not title or not content:
        raise HTTPException(status_code=400, detail="Title and message are required")

    a = Announcement(
        title=title,
        content=content,
        announcement_type=TYPE_MAP.get((payload.announcement_type or "").lower(), "event"),
        category=CATEGORY_MAP.get((payload.category or "").lower(), "general"),
        priority=PRIORITY_MAP.get((payload.priority or "").lower(), "medium"),
        image_url=payload.image_url,
        action_url=(payload.action_url or "").strip() or None,
        expires_at=payload.expires_at,
        is_published=payload.is_published,
        created_by_user_id=admin.id,
        created_at=datetime.utcnow(),
    )
    db.add(a)
    db.commit()
    db.refresh(a)

    if a.is_published:
        users = db.query(User).filter(User.is_active == True).all()
        recipients = [(u.email, a.title, a.content) for u in users if u.email]
        background_tasks.add_task(_send_emails, recipients)

    logger.info(f"Announcement {a.id} created by admin {admin.id}")
    return {"status": "success", "data": _to_dict(a)}


@router.put("/{announcement_id}")
def update_announcement(
    announcement_id: int,
    payload: AnnouncementUpdateSchema,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    a = db.query(Announcement).filter(Announcement.id == announcement_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Announcement not found")

    if payload.title is not None:
        a.title = payload.title.strip()
    if payload.content is not None:
        a.content = payload.content.strip()
    if payload.announcement_type is not None:
        a.announcement_type = TYPE_MAP.get(payload.announcement_type.lower(), "event")
    if payload.category is not None:
        a.category = CATEGORY_MAP.get(payload.category.lower(), "general")
    if payload.priority is not None:
        a.priority = PRIORITY_MAP.get(payload.priority.lower(), "medium")
    if payload.image_url is not None:
        a.image_url = payload.image_url
    if payload.action_url is not None:
        a.action_url = payload.action_url.strip() or None
    if payload.expires_at is not None:
        a.expires_at = payload.expires_at
    if payload.is_published is not None:
        a.is_published = payload.is_published

    db.commit()
    db.refresh(a)
    logger.info(f"Announcement {a.id} updated by admin {admin.id}")
    return {"status": "success", "data": _to_dict(a)}


@router.delete("/{announcement_id}")
def delete_announcement(
    announcement_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    a = db.query(Announcement).filter(Announcement.id == announcement_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Announcement not found")
    db.delete(a)
    db.commit()
    logger.info(f"Announcement {announcement_id} deleted by admin {admin.id}")
    return {"status": "success", "message": "Announcement deleted", "id": announcement_id}