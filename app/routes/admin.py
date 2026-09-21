# ============================================================================
# Admin Routes - Phase 3 (RBAC with Real Data)
# ============================================================================
# Production-ready admin endpoints with Role-Based Access Control

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from datetime import datetime
import logging

from app.database import get_db
from app.models import User, Session as SessionModel, SessionAttendance
from app.routes.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

# ============================================================================
# RBAC Middleware Functions
# ============================================================================

def require_admin(current_user: User = Depends(get_current_user)):
    """Verify user is admin"""
    is_admin = getattr(current_user, "is_admin", False)
    if not is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

def require_role(required_roles: list):
    """Factory function to create role-based dependency"""
    async def verify_role(current_user: User = Depends(get_current_user)):
        is_admin = getattr(current_user, "is_admin", False)
        user_role = getattr(current_user, "role", "admin" if is_admin else "user")
        if user_role not in required_roles and not is_admin:
            raise HTTPException(status_code=403, detail=f"Role '{user_role}' not authorized")
        return current_user
    return verify_role

# ============================================================================
# USER MANAGEMENT - View & Control Users
# ============================================================================

@router.get("/users")
async def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    role: str = Query(None),
    is_active: bool = Query(None)
):
    """
    PRODUCTION: List all users with filtering.
    
    Admin only endpoint. Returns all user data for management.
    """
    try:
        query = db.query(User)

        # Apply filters
        if role:
            query = query.filter(User.role == role)
        if is_active is not None:
            query = query.filter(User.is_active == is_active)

        total = query.count()
        users = query.offset(offset).limit(limit).all()

        return {
            "status": "success",
            "data": [
                {
                    "id": u.id,
                    "full_name": u.full_name,
                    "email": u.email,
                    "role": u.role or "user",
                    "is_admin": u.is_admin,
                    "is_active": u.is_active,
                    "job_title": u.job_title,
                    "company": u.company,
                    "location": u.location,
                    "experience_years": u.experience_years,
                    "total_points": u.total_points or 0,
                    "created_at": u.created_at.isoformat() if u.created_at else None,
                    "last_login": u.last_login.isoformat() if u.last_login else None,
                    "sessions_attended": db.query(func.count(SessionAttendance.id)).filter(
                        SessionAttendance.user_id == u.id,
                        SessionAttendance.attended == True
                    ).scalar()
                }
                for u in users
            ],
            "total": total,
            "limit": limit,
            "offset": offset
        }

    except Exception as e:
        logger.error(f"User list error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to list users")


@router.put("/users/{user_id}/role")
async def update_user_role(
    user_id: int,
    request_body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    PRODUCTION: Update user role.
    
    Valid roles: user, speaker, moderator, admin
    Only admins can change roles.
    """
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        new_role = request_body.get("role", "").lower()
        valid_roles = ["user", "speaker", "moderator", "admin"]

        if new_role not in valid_roles:
            raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {valid_roles}")

        # Update role
        user.role = new_role
        if new_role == "admin":
            user.is_admin = True
        else:
            user.is_admin = False

        db.commit()

        logger.info(f"User {user_id} role changed to {new_role} by admin {current_user.id}")

        return {
            "status": "success",
            "message": f"User role updated to {new_role}",
            "user_id": user_id,
            "new_role": new_role
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Role update error: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update role")


@router.put("/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    PRODUCTION: Revoke user access.
    
    Sets is_active=false, user cannot log in.
    """
    try:
        if user_id == current_user.id:
            raise HTTPException(status_code=400, detail="Cannot deactivate yourself")

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user.is_active = False
        db.commit()

        logger.warning(f"User {user_id} deactivated by admin {current_user.id}")

        return {
            "status": "success",
            "message": "User access revoked",
            "user_id": user_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Deactivate error: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to deactivate user")


@router.put("/users/{user_id}/reactivate")
async def reactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    PRODUCTION: Re-enable user access.
    """
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user.is_active = True
        db.commit()

        logger.info(f"User {user_id} reactivated by admin {current_user.id}")

        return {
            "status": "success",
            "message": "User access restored",
            "user_id": user_id
        }

    except Exception as e:
        logger.error(f"Reactivate error: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to reactivate user")


# ============================================================================
# SESSION MANAGEMENT - Approve & Control Sessions
# ============================================================================

@router.get("/sessions")
async def list_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    is_approved: bool = Query(None)
):
    """
    PRODUCTION: List all sessions with approval status.
    """
    try:
        query = db.query(SessionModel)

        if is_approved is not None:
            query = query.filter(SessionModel.is_approved == is_approved)

        total = query.count()
        sessions = query.offset(offset).limit(limit).all()

        return {
            "status": "success",
            "data": [
                {
                    "id": s.id,
                    "title": s.title,
                    "description": s.description,
                    "speaker_name": s.speaker_name,
                    "speaker_id": s.speaker_id,
                    "category": s.category,
                    "level": s.level,
                    "location": s.location,
                    "start_time": s.start_time.isoformat() if s.start_time else None,
                    "end_time": s.end_time.isoformat() if s.end_time else None,
                    "capacity": s.capacity,
                    "is_approved": s.is_approved,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                    "attendee_count": db.query(func.count(SessionAttendance.id)).filter(
                        SessionAttendance.session_id == s.id,
                        SessionAttendance.attended == True
                    ).scalar()
                }
                for s in sessions
            ],
            "total": total,
            "limit": limit,
            "offset": offset
        }

    except Exception as e:
        logger.error(f"Session list error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to list sessions")


@router.put("/sessions/{session_id}/approve")
async def approve_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    PRODUCTION: Approve session for public visibility.
    """
    try:
        session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        session.is_approved = True
        db.commit()

        logger.info(f"Session {session_id} approved by admin {current_user.get('id')}")

        return {
            "status": "success",
            "message": "Session approved",
            "session_id": session_id
        }

    except Exception as e:
        logger.error(f"Approve error: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to approve session")


@router.put("/sessions/{session_id}/reject")
async def reject_session(
    session_id: int,
    request_body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    PRODUCTION: Reject session with reason.
    """
    try:
        session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        session.is_approved = False
        # Store rejection reason if you add a field
        reason = request_body.get("reason", "No reason provided")

        db.commit()

        logger.warning(f"Session {session_id} rejected by admin {current_user.get('id')}. Reason: {reason}")

        return {
            "status": "success",
            "message": f"Session rejected: {reason}",
            "session_id": session_id
        }

    except Exception as e:
        logger.error(f"Reject error: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to reject session")


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    PRODUCTION: Permanently delete session.
    
    WARNING: Irreversible action. Cascades to related records.
    """
    try:
        session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Delete related records
        db.query(SessionAttendance).filter(SessionAttendance.session_id == session_id).delete()

        # Delete session
        db.delete(session)
        db.commit()

        logger.warning(f"Session {session_id} deleted by admin {current_user.get('id')}")

        return {
            "status": "success",
            "message": "Session permanently deleted",
            "session_id": session_id
        }

    except Exception as e:
        logger.error(f"Delete error: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to delete session")


# ============================================================================
# ANALYTICS & REPORTING
# ============================================================================

@router.get("/analytics/dashboard")
async def get_analytics_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    PRODUCTION: Admin analytics dashboard with real data.
    """
    try:
        total_users = db.query(func.count(User.id)).scalar()
        active_users = db.query(func.count(User.id)).filter(User.is_active == True).scalar()
        admin_count = db.query(func.count(User.id)).filter(User.is_admin == True).scalar()
        
        total_sessions = db.query(func.count(SessionModel.id)).scalar()
        approved_sessions = db.query(func.count(SessionModel.id)).filter(
            SessionModel.is_approved == True
        ).scalar()
        pending_sessions = total_sessions - approved_sessions

        total_attendances = db.query(func.count(SessionAttendance.id)).filter(
            SessionAttendance.attended == True
        ).scalar()

        avg_attendance = 0
        if approved_sessions > 0:
            avg_attendance = total_attendances / approved_sessions

        return {
            "status": "success",
            "data": {
                "users": {
                    "total": total_users,
                    "active": active_users,
                    "inactive": total_users - active_users,
                    "admins": admin_count
                },
                "sessions": {
                    "total": total_sessions,
                    "approved": approved_sessions,
                    "pending": pending_sessions
                },
                "attendance": {
                    "total": total_attendances,
                    "average_per_session": round(avg_attendance, 2)
                },
                "timestamp": datetime.utcnow().isoformat()
            }
        }

    except Exception as e:
        logger.error(f"Analytics error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch analytics")


# ============================================================================
# ROLES & PERMISSIONS
# ============================================================================

@router.get("/roles")
async def get_roles(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    PRODUCTION: List all available roles and their permissions.
    """
    return {
        "status": "success",
        "data": [
            {
                "name": "user",
                "description": "Regular platform user",
                "permissions": [
                    "view_sessions",
                    "attend_sessions",
                    "rate_sessions",
                    "view_profile"
                ]
            },
            {
                "name": "speaker",
                "description": "Can create and manage sessions",
                "permissions": [
                    "view_sessions",
                    "attend_sessions",
                    "rate_sessions",
                    "create_session",
                    "edit_own_session",
                    "view_analytics"
                ]
            },
            {
                "name": "moderator",
                "description": "Can manage content and users",
                "permissions": [
                    "view_all_sessions",
                    "approve_sessions",
                    "reject_sessions",
                    "edit_any_session",
                    "manage_users",
                    "view_analytics"
                ]
            },
            {
                "name": "admin",
                "description": "Full platform access",
                "permissions": [
                    "manage_all",
                    "access_admin_panel",
                    "manage_roles",
                    "view_all_data"
                ]
            }
        ]
    }


# ============================================================================
# NOTE: Include in main.py
# ============================================================================
# from app.routes import admin_routes
# app.include_router(
#     admin_routes.router,
#     prefix="/api/v1/admin",
#     tags=["Admin Management"]
# )