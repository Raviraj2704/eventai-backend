# ============================================================================
# Admin Routes
# ============================================================================
# File: app/routes/admin.py
# Purpose: Admin user management and content moderation
# Status: Production-Ready ✅

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from datetime import datetime
from typing import Optional
import logging

from app.database import get_db
from app.models import User, AdminLog, SocialPost, SocialComment
from app.schemas import (
    AdminUserResponse, AdminUserDetailResponse, AdminUserUpdateRequest,
    AdminContentResponse, AdminContentActionRequest, AdminLogResponse,
    AdminListRequest, ErrorResponse
)
from app.routes.users import get_current_user


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])


# ============================================================================
# DEPENDENCY: CHECK ADMIN
# ============================================================================

def check_admin(current_user: User = Depends(get_current_user)) -> User:
    """
    Verify user is admin
    
    Args:
        current_user: Authenticated user
    
    Returns:
        User: Admin user
    
    Raises:
        HTTPException: If not admin
    """
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


# ============================================================================
# GET ALL USERS (ADMIN)
# ============================================================================

@router.get(
    "/users",
    response_model=dict,
    responses={403: {"model": ErrorResponse}}
)
async def get_all_users(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    status_filter: Optional[str] = None,
    admin: User = Depends(check_admin),
    db: Session = Depends(get_db)
):
    """
    Get all users (admin only)
    
    Args:
        page: Page number
        limit: Results per page
        search: Search by username/email
        status_filter: Filter by status (active/inactive)
        admin: Authenticated admin user
        db: Database session
    
    Returns:
        dict: Paginated users list
    """
    try:
        query = db.query(User)
        
        if status_filter == "active":
            query = query.filter(User.is_active == True)
        elif status_filter == "inactive":
            query = query.filter(User.is_active == False)
        
        if search:
            query = query.filter(
                or_(
                    User.username.ilike(f"%{search}%"),
                    User.email.ilike(f"%{search}%")
                )
            )
        
        query = query.order_by(User.created_at.desc())
        
        total = query.count()
        users = query.offset((page - 1) * limit).limit(limit).all()
        
        # Log admin action
        log_entry = AdminLog(
            admin_id=admin.id,
            action="VIEW_USERS_LIST",
            entity_type="User",
            timestamp=datetime.utcnow()
        )
        db.add(log_entry)
        db.commit()
        
        users_data = [
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "name": f"{u.first_name} {u.last_name}".strip() if u.first_name or u.last_name else "N/A",
                "status": "active" if u.is_active else "inactive",
                "joined_date": u.created_at,
                "last_login": getattr(u, "last_login", None)
            }
            for u in users
        ]
        
        return {
            "total": total,
            "page": page,
            "limit": limit,
            "data": users_data
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get users error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch users"
        )


# ============================================================================
# GET USER DETAIL (ADMIN)
# ============================================================================

@router.get(
    "/users/{user_id}",
    response_model=dict,
    responses={
        403: {"model": ErrorResponse}, 
        404: {"model": ErrorResponse}
    }
)
async def get_user_detail(
    user_id: int,
    admin: User = Depends(check_admin),
    db: Session = Depends(get_db)
):
    """
    Get user details (admin only)
    
    Args:
        user_id: User ID
        admin: Authenticated admin user
        db: Database session
    
    Returns:
        dict: User details
    """
    try:
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Log admin action
        log_entry = AdminLog(
            admin_id=admin.id,
            action="VIEW_USER_DETAIL",
            entity_type="User",
            entity_id=user_id,
            timestamp=datetime.utcnow()
        )
        db.add(log_entry)
        db.commit()
        
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "status": "active" if user.is_active else "inactive",
            "is_admin": user.is_admin,
            "is_verified": getattr(user, "is_verified", True),
            "company": getattr(user, "company", None),
            "job_title": getattr(user, "job_title", None),
            "created_at": user.created_at,
            "last_login": getattr(user, "last_login", None)
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get user detail error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch user details"
        )


# ============================================================================
# UPDATE USER (ADMIN)
# ============================================================================

@router.put(
    "/users/{user_id}",
    response_model=dict,
    responses={
        403: {"model": ErrorResponse}, 
        404: {"model": ErrorResponse}
    }
)
async def update_user(
    user_id: int,
    request: AdminUserUpdateRequest,
    admin: User = Depends(check_admin),
    db: Session = Depends(get_db)
):
    """
    Update user (admin only)
    
    Args:
        user_id: User ID
        request: Update data
        admin: Authenticated admin user
        db: Database session
    
    Returns:
        dict: Updated user
    """
    try:
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Track changes
        old_values = {
            "is_active": user.is_active,
            "is_admin": user.is_admin
        }
        
        # Update
        if request.is_active is not None:
            user.is_active = request.is_active
        if request.is_admin is not None:
            user.is_admin = request.is_admin
        
        new_values = {
            "is_active": user.is_active,
            "is_admin": user.is_admin
        }
        
        # Log admin action
        log_entry = AdminLog(
            admin_id=admin.id,
            action="UPDATE_USER",
            entity_type="User",
            entity_id=user_id,
            old_values=old_values,
            new_values=new_values,
            timestamp=datetime.utcnow()
        )
        db.add(log_entry)
        db.commit()
        
        logger.info(f"Admin {admin.id} updated user {user_id}")
        
        return {
            "message": "User updated successfully",
            "user_id": user_id
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Update user error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user"
        )


# ============================================================================
# DELETE USER (ADMIN)
# ============================================================================

@router.delete(
    "/users/{user_id}",
    response_model=dict,
    responses={
        403: {"model": ErrorResponse}, 
        404: {"model": ErrorResponse}
    }
)
async def delete_user(
    user_id: int,
    admin: User = Depends(check_admin),
    db: Session = Depends(get_db)
):
    """
    Delete user (admin only - soft delete)
    
    Args:
        user_id: User ID
        admin: Authenticated admin user
        db: Database session
    
    Returns:
        dict: Success message
    """
    try:
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Soft delete
        user.is_active = False
        user.updated_at = datetime.utcnow()
        
        # Log admin action
        log_entry = AdminLog(
            admin_id=admin.id,
            action="DELETE_USER",
            entity_type="User",
            entity_id=user_id,
            timestamp=datetime.utcnow()
        )
        db.add(log_entry)
        db.commit()
        
        logger.info(f"Admin {admin.id} deleted user {user_id}")
        
        return {"message": "User deleted successfully"}
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Delete user error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete user"
        )


# ============================================================================
# GET CONTENT FOR MODERATION
# ============================================================================

@router.get(
    "/moderation/content",
    response_model=dict,
    responses={403: {"model": ErrorResponse}}
)
async def get_content_for_moderation(
    content_type: Optional[str] = None,
    status_filter: Optional[str] = None,
    admin: User = Depends(check_admin),
    db: Session = Depends(get_db)
):
    """
    Get content requiring moderation (admin only)
    
    Args:
        content_type: post/comment
        status_filter: pending/approved/rejected
        admin: Authenticated admin user
        db: Database session
    
    Returns:
        dict: Content list
    """
    try:
        content_list = []
        
        if content_type in [None, "post"]:
            posts = db.query(SocialPost).filter(
                SocialPost.is_approved == False
            ).all()
            
            for post in posts:
                content_list.append({
                    "id": post.id,
                    "type": "post",
                    "author": post.author.username if post.author else "Unknown",
                    "content": post.content[:100],
                    "created_at": post.created_at,
                    "status": "pending"
                })
        
        if content_type in [None, "comment"]:
            comments = db.query(SocialComment).filter(
                SocialComment.is_approved == False
            ).all()
            
            for comment in comments:
                content_list.append({
                    "id": comment.id,
                    "type": "comment",
                    "author": comment.author.username if comment.author else "Unknown",
                    "content": comment.content[:100],
                    "created_at": comment.created_at,
                    "status": "pending"
                })
        
        return {
            "total": len(content_list),
            "data": content_list
        }
    
    except Exception as e:
        logger.error(f"Get moderation content error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch content"
        )


# ============================================================================
# APPROVE CONTENT
# ============================================================================

@router.post(
    "/moderation/content/{content_id}/approve",
    response_model=dict,
    responses={
        403: {"model": ErrorResponse}, 
        404: {"model": ErrorResponse}
    }
)
async def approve_content(
    content_id: int,
    content_type: str,
    admin: User = Depends(check_admin),
    db: Session = Depends(get_db)
):
    """
    Approve content (admin only)
    
    Args:
        content_id: Content ID
        content_type: post/comment
        admin: Authenticated admin user
        db: Database session
    
    Returns:
        dict: Success message
    """
    try:
        if content_type == "post":
            content = db.query(SocialPost).filter(SocialPost.id == content_id).first()
        elif content_type == "comment":
            content = db.query(SocialComment).filter(SocialComment.id == content_id).first()
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid content type"
            )
        
        if not content:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Content not found"
            )
        
        content.is_approved = True
        
        # Log action
        log_entry = AdminLog(
            admin_id=admin.id,
            action="APPROVE_CONTENT",
            entity_type=content_type.upper(),
            entity_id=content_id,
            timestamp=datetime.utcnow()
        )
        db.add(log_entry)
        db.commit()
        
        logger.info(f"Admin {admin.id} approved {content_type} {content_id}")
        
        return {"message": "Content approved successfully"}
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Approve content error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to approve content"
        )


# ============================================================================
# REJECT CONTENT
# ============================================================================

@router.post(
    "/moderation/content/{content_id}/reject",
    response_model=dict,
    responses={
        403: {"model": ErrorResponse}, 
        404: {"model": ErrorResponse}
    }
)
async def reject_content(
    content_id: int,
    content_type: str,
    request: AdminContentActionRequest,
    admin: User = Depends(check_admin),
    db: Session = Depends(get_db)
):
    """
    Reject content (admin only)
    
    Args:
        content_id: Content ID
        content_type: post/comment
        request: Rejection reason
        admin: Authenticated admin user
        db: Database session
    
    Returns:
        dict: Success message
    """
    try:
        if content_type == "post":
            content = db.query(SocialPost).filter(SocialPost.id == content_id).first()
        elif content_type == "comment":
            content = db.query(SocialComment).filter(SocialComment.id == content_id).first()
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid content type"
            )
        
        if not content:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Content not found"
            )
        
        # Delete content (soft delete or hard delete)
        db.delete(content)
        
        # Log action
        log_entry = AdminLog(
            admin_id=admin.id,
            action="REJECT_CONTENT",
            entity_type=content_type.upper(),
            entity_id=content_id,
            new_values={"reason": request.reason},
            timestamp=datetime.utcnow()
        )
        db.add(log_entry)
        db.commit()
        
        logger.info(f"Admin {admin.id} rejected {content_type} {content_id}")
        
        return {"message": "Content rejected successfully"}
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Reject content error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reject content"
        )


# ============================================================================
# GET ADMIN LOGS
# ============================================================================

@router.get(
    "/logs",
    response_model=dict,
    responses={403: {"model": ErrorResponse}}
)
async def get_admin_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    admin: User = Depends(check_admin),
    db: Session = Depends(get_db)
):
    """
    Get admin action logs (admin only)
    
    Args:
        page: Page number
        limit: Results per page
        admin: Authenticated admin user
        db: Database session
    
    Returns:
        dict: Paginated logs
    """
    try:
        query = db.query(AdminLog).order_by(AdminLog.timestamp.desc())
        
        total = query.count()
        logs = query.offset((page - 1) * limit).limit(limit).all()
        
        logs_data = [
            {
                "id": log.id,
                "admin_name": log.admin.username if log.admin else "Unknown",
                "action": log.action,
                "entity_type": log.entity_type,
                "entity_id": log.entity_id,
                "timestamp": log.timestamp
            }
            for log in logs
        ]
        
        return {
            "total": total,
            "page": page,
            "limit": limit,
            "data": logs_data
        }
    
    except Exception as e:
        logger.error(f"Get admin logs error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch logs"
        )