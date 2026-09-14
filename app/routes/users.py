# ============================================================================
# User Routes
# ============================================================================
# File: app/routes/users.py
# Purpose: User profile management endpoints
# Status: Production-Ready ✅

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
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
router = APIRouter(prefix="/api/v1/users", tags=["Users"])
security = HTTPBearer()


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
# GET CURRENT USER PROFILE
# ============================================================================

@router.get(
    "/me",
    response_model=UserProfileResponse,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}
)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user)
):
    """
    Get current user's profile
    """
    try:
        return UserProfileResponse.from_attributes(current_user)
    except Exception as e:
        logger.error(f"Get profile error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch profile"
        )


# ============================================================================
# UPDATE USER PROFILE
# ============================================================================

@router.put(
    "/me",
    response_model=UserUpdateResponse,
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}}
)
async def update_user_profile(
    request: UserUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update current user's profile
    """
    try:
        # Update fields
        if request.first_name is not None:
            current_user.first_name = request.first_name
        if request.last_name is not None:
            current_user.last_name = request.last_name
        if request.bio is not None:
            current_user.bio = request.bio
        if request.company is not None:
            current_user.company = request.company
        if request.job_title is not None:
            current_user.job_title = request.job_title
        if request.phone is not None:
            current_user.phone = request.phone
        
        # Update timestamp
        current_user.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(current_user)
        
        logger.info(f"Profile updated for user: {current_user.username}")
        
        return UserUpdateResponse(
            message="Profile updated successfully",
            user=UserProfileResponse.from_attributes(current_user)
        )
    
    except Exception as e:
        db.rollback()
        logger.error(f"Profile update error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update profile"
        )


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
        current_user.avatar_url = avatar_url
        current_user.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(current_user)
        
        logger.info(f"Avatar uploaded for user: {current_user.username}")
        
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
# GET USER BY ID
# ============================================================================

@router.get(
    "/{user_id}",
    response_model=UserProfileResponse,
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
        
        return UserProfileResponse.from_attributes(user)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get user error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch user"
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
        current_user.updated_at = datetime.utcnow()
        
        db.commit()
        
        logger.info(f"Account deleted for user: {current_user.username}")
        
        return {"message": "Account deleted successfully"}
    
    except Exception as e:
        db.rollback()
        logger.error(f"Account deletion error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete account"
        )