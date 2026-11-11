# ============================================================================
# Notification Routes
# File: app/routes/notifications.py
# GET    /api/v1/notifications              this user's notifications + unread_count
# POST   /api/v1/notifications/read-all     mark all as read
# POST   /api/v1/notifications/{id}/read    mark one as read
# create_notification() is called by other routes when real events happen.
# ============================================================================

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Notification, User
from app.routes.users import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Notifications"])


# ============================================================================
# Helper for other routes (meeting requests, profile approvals, etc.)
# ============================================================================

def create_notification(
    db: Session,
    user_id: int,
    title: str,
    message: str,
    notification_type: str = "personal",
    action_url: str | None = None,
    related_id: int | None = None,
    icon_emoji: str | None = None,
) -> Notification:
    """Adds a notification for one user. The caller commits the session."""
    row = Notification(
        user_id=user_id,
        title=title,
        message=message,
        notification_type=notification_type,
        action_url=action_url,
        related_id=related_id,
        icon_emoji=icon_emoji,
        is_read=False,
        created_at=datetime.utcnow(),
    )
    db.add(row)
    return row


def _to_dict(n: Notification) -> dict:
    return {
        "id": n.id,
        "title": n.title,
        "message": n.message,
        "notification_type": n.notification_type,
        "icon_emoji": n.icon_emoji,
        "action_url": n.action_url,
        "related_id": n.related_id,
        "is_read": bool(n.is_read),
        "created_at": n.created_at.isoformat() if n.created_at else None,
        "read_at": n.read_at.isoformat() if n.read_at else None,
    }


# ============================================================================
# List (current user only)
# ============================================================================

@router.get("")
def list_notifications(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    base = db.query(Notification).filter(Notification.user_id == current_user.id)
    total = base.count()
    unread_count = base.filter(Notification.is_read == False).count()
    rows = (
        base.order_by(Notification.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    return {
        "status": "success",
        "total": total,
        "unread_count": unread_count,
        "page": page,
        "limit": limit,
        "data": [_to_dict(n) for n in rows],
    }


# ============================================================================
# Mark read
# ============================================================================

@router.post("/read-all")
def mark_all_read(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == False,
    ).update({"is_read": True, "read_at": datetime.utcnow()}, synchronize_session=False)
    db.commit()
    return {"status": "success", "unread_count": 0}


@router.post("/{notification_id}/read")
def mark_read(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    n = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == current_user.id,
    ).first()
    if not n:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    if not n.is_read:
        n.is_read = True
        n.read_at = datetime.utcnow()
        db.commit()
    return {"status": "success", "data": _to_dict(n)}