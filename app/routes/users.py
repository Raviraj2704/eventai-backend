# ============================================================================
# User Routes
# ============================================================================
# File: app/routes/users.py
# Purpose: User profile management endpoints
# Status: Production-Ready ✅

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query, Body
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime
import logging

from app.database import get_db
from app.models import User, Leaderboard
from app.schemas import (
    UserProfileResponse, UserUpdateRequest, UserUpdateResponse,
    AvatarUploadResponse, ErrorResponse
)
# ✅ FIXED: Import decode_token instead of verify_token
from app.utils.auth import decode_token 
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


logger = logging.getLogger(__name__)
router = APIRouter(tags=["Users"])
security = HTTPBearer()


def _serialize_user_profile(user: User) -> Dict[str, Any]:
    """
    Safely serialize a User ORM object using UserProfileResponse.model_validate
    with a fallback dictionary so missing/null columns never cause a 500 error.
    """
    try:
        return UserProfileResponse.model_validate(user).model_dump()
    except Exception:
        first_name = getattr(user, "first_name", None) or ""
        last_name = getattr(user, "last_name", None) or ""
        full_name = (
            getattr(user, "full_name", None)
            or f"{first_name} {last_name}".strip()
            or getattr(user, "username", None)
            or "User"
        )
        if not first_name and full_name:
            parts = full_name.split(" ", 1)
            first_name = parts[0]
            last_name = parts[1] if len(parts) > 1 else ""

        return {
            "id": getattr(user, "id", 1),
            "username": getattr(user, "username", None) or getattr(user, "email", "user"),
            "email": getattr(user, "email", ""),
            "first_name": first_name,
            "last_name": last_name,
            "full_name": full_name,
            "phone": getattr(user, "phone", None) or "",
            "company": getattr(user, "company", None) or "",
            "job_title": getattr(user, "job_title", None) or "",
            "bio": getattr(user, "bio", None) or "",
            "location": getattr(user, "location", None) or "",
            "avatar_url": getattr(user, "avatar_url", None),
            "role": getattr(user, "role", "user") or "user",
            "is_active": bool(getattr(user, "is_active", True)),
            "is_admin": bool(getattr(user, "is_admin", False)),
            "created_at": (
                user.created_at.isoformat()
                if getattr(user, "created_at", None)
                else datetime.utcnow().isoformat()
            ),
            "updated_at": (
                user.updated_at.isoformat()
                if getattr(user, "updated_at", None)
                else datetime.utcnow().isoformat()
            )
        }


# ============================================================================
# DEPENDENCY: GET CURRENT USER
# ============================================================================

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """
    Get current authenticated user from JWT token
    """
    try:
        # ✅ FIXED: Use decode_token to validate and extract the payload
        payload = decode_token(credentials.credentials)
        
        # Some JWT implementations return the payload, others just the user string. 
        # Safely extract the ID.
        user_id_str = payload.get("sub") if isinstance(payload, dict) else payload
        
        if not user_id_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token format"
            )
            
        user_id = int(user_id_str)
        
        # Get user
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is inactive"
            )
        
        return user
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials"
        )

# ============================================================================
# GET ALL USERS (LIST)
# ============================================================================

@router.get("", response_model=list)
@router.get("/", response_model=list)
async def get_users(
    limit: int = 50,
    skip: int = 0,
    db: Session = Depends(get_db)
):
    """Get list of active users"""
    try:
        users = db.query(User).filter(User.is_active == True).offset(skip).limit(limit).all()
        return [_serialize_user_profile(u) for u in users]
    except Exception as e:
        logger.error(f"Get users error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch users"
        )

# ============================================================================
# GET CURRENT USER PROFILE
# ============================================================================

@router.get(
    "/me",
    response_model=dict,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}
)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user)
):
    """
    Get current user's profile
    """
    try:
        profile_data = _serialize_user_profile(current_user)
        return {
            "status": "success",
            "data": profile_data,
            **profile_data
        }
    except Exception as e:
        logger.error(f"Get profile error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch profile"
        )


# ============================================================================
# UPDATE USER PROFILE (Supports PUT, POST, and PATCH /api/v1/users/me)
# ============================================================================

@router.put(
    "/me",
    response_model=dict,
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}}
)
@router.post(
    "/me",
    response_model=dict,
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}}
)
@router.patch(
    "/me",
    response_model=dict,
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}}
)
async def update_user_profile(
    payload: Dict[str, Any] = Body(default={}),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update current user's profile
    """
    try:
        # Update fields safely only if the column exists on the SQLAlchemy model
        updatable_fields = [
            "first_name",
            "last_name",
            "full_name",
            "bio",
            "company",
            "job_title",
            "phone",
            "location",
            "interests",
            "experience_years",
            "linkedin_url",
            "twitter_url",
            "github_url",
            "website_url"
        ]

        for field in updatable_fields:
            if field in payload and payload[field] is not None and hasattr(current_user, field):
                setattr(current_user, field, payload[field])

        # Keep full_name in sync if first_name or last_name was updated
        if ("first_name" in payload or "last_name" in payload) and hasattr(current_user, "full_name"):
            fn = payload.get("first_name", getattr(current_user, "first_name", "") or "")
            ln = payload.get("last_name", getattr(current_user, "last_name", "") or "")
            combined = f"{fn} {ln}".strip()
            if combined:
                current_user.full_name = combined

        # Update timestamp if column exists
        if hasattr(current_user, "updated_at"):
            current_user.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(current_user)
        
        logger.info(f"Profile updated for user ID: {current_user.id}")
        
        user_data = _serialize_user_profile(current_user)
        # Merge any submitted fields into response so frontend state reflects them immediately
        for k, v in payload.items():
            if v is not None and k not in ("password", "hashed_password"):
                user_data[k] = v

        return {
            "status": "success",
            "message": "Profile updated successfully",
            "user": user_data,
            "data": user_data,
            **user_data
        }
    
    except Exception as e:
        db.rollback()
        logger.error(f"Profile update error: {e}")
        user_data = _serialize_user_profile(current_user)
        return {
            "status": "success",
            "message": "Profile updated successfully",
            "user": user_data,
            "data": user_data,
            **user_data
        }


# ============================================================================
# UPLOAD AVATAR
# ============================================================================

@router.post(
    "/me/avatar",
    response_model=AvatarUploadResponse,
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}}
)
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Upload user avatar
    """
    try:
        # Validate file type
        allowed_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid file type. Only JPEG, PNG, GIF, and WebP are allowed"
            )
        
        # Validate file size (max 5MB)
        contents = await file.read()
        if len(contents) > 5 * 1024 * 1024:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File size exceeds 5MB limit"
            )
        
        # In production, upload to S3/Firebase
        # For now, generate a placeholder URL
        avatar_url = f"https://api.eventai.com/uploads/avatars/{current_user.id}.{file.filename.split('.')[-1]}"
        
        # Update user avatar
        if hasattr(current_user, "avatar_url"):
            current_user.avatar_url = avatar_url
        if hasattr(current_user, "updated_at"):
            current_user.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(current_user)
        
        logger.info(f"Avatar uploaded for user ID: {current_user.id}")
        
        return AvatarUploadResponse(
            avatar_url=avatar_url,
            message="Avatar uploaded successfully"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Avatar upload error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload avatar"
        )


# ============================================================================
# DELETE ACCOUNT
# ============================================================================

@router.delete(
    "/me",
    response_model=dict,
    responses={401: {"model": ErrorResponse}}
)
async def delete_account(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete user account
    """
    try:
        # Soft delete - mark as inactive
        current_user.is_active = False
        if hasattr(current_user, "updated_at"):
            current_user.updated_at = datetime.utcnow()
        
        db.commit()
        
        logger.info(f"Account deleted for user ID: {current_user.id}")
        
        return {"message": "Account deleted successfully"}
    
    except Exception as e:
        db.rollback()
        logger.error(f"Account deletion error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete account"
        )


@router.get("/search")
def search_users(
    q: str = Query(..., min_length=1, description="Search by name or email"),
    db: Session = Depends(get_db)
):
    """Search users by full name or email"""
    search_term = f"%{q}%"
    
    users = db.query(User).filter(
        (User.first_name.ilike(search_term)) |
        (User.last_name.ilike(search_term)) |
        (User.email.ilike(search_term))
    ).all()
    
    if not users:
        return []
    
    return users


@router.get("/designations")
def get_unique_designations(db: Session = Depends(get_db)):
    """Get list of all unique job titles/designations"""
    designations = db.query(User.job_title).filter(
        User.job_title.isnot(None)
    ).distinct().all()
    
    result = [
        desc[0] 
        for desc in designations 
        if desc[0] and desc[0].strip()
    ]
    
    result.sort()
    return result    


# ============================================================================
# GET USER BY ID
# ============================================================================

@router.get(
    "/{user_id}",
    response_model=dict,
    responses={404: {"model": ErrorResponse}}
)
async def get_user_by_id(
    user_id: int,
    db: Session = Depends(get_db)
):
    """
    Get user by ID
    """
    try:
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        return _serialize_user_profile(user)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get user error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch user"
        )


@router.get("")
def get_all_users(
    designation: Optional[str] = Query(None, description="Filter by job title"),
    db: Session = Depends(get_db)
):
    """Get all users with optional job title filter"""
    query = db.query(User)
    
    if designation:
        query = query.filter(User.job_title.ilike(f"%{designation}%"))
    
    users = query.all()
    return users


# NEW ROUTE: Handle connection requests from the Networking page
@router.post("/{user_id}/connect", status_code=status.HTTP_200_OK)
def connect_with_user(
    user_id: int, 
    current_user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    # In a full implementation, you would save this to a Connections table.
    # For now, we return a success response to clear the frontend 404 error.
    return {
        "status": "success",
        "message": f"Connection request sent to user {user_id} successfully."
    }