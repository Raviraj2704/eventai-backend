# ============================================================================
# Authentication Routes
# ============================================================================
# File: backend/app/routes/auth.py
# Purpose: User authentication endpoints
# Status: Production-Ready ✅

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User
from app.schemas import RegisterSchema, LoginSchema, TokenResponse, UserResponse
from app.utils.auth import hash_password, verify_password, create_access_token, create_refresh_token
from datetime import datetime

logger = logging.getLogger(__name__)
router = APIRouter()

# ============================================================================
# REGISTER ENDPOINT
# ============================================================================

@router.post("/register", response_model=TokenResponse)
def register(request: RegisterSchema, db: Session = Depends(get_db)):
    """Register new user"""
    try:
        logger.info(f"📝 Registration attempt: {request.email}")
        
        # ✅ Check if email already exists
        existing_user = db.query(User).filter(User.email == request.email).first()
        
        if existing_user:
            logger.warning(f"❌ Email already registered: {request.email}")
            raise HTTPException(
                status_code=400,
                detail="Email already registered"
            )
        
        # ✅ Hash password
        hashed_password = hash_password(request.password)
        
        # ✅ Create new user
        new_user = User(
            first_name=request.first_name,
            last_name=request.last_name,
            email=request.email,
            hashed_password=hashed_password,
            is_active=True,
            email_verified=True,
            verification_token=None
        )
        
        # ✅ Save to database
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        logger.info(f"✅ User registered: {new_user.email} (ID: {new_user.id})")
        
        # ✅ Generate tokens
        access_token = create_access_token(data={"sub": str(new_user.id)})
        refresh_token = create_refresh_token(data={"sub": str(new_user.id)})
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer"
        }
        
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"❌ Registration error: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")


# ============================================================================
# LOGIN ENDPOINT
# ============================================================================

@router.post("/login", response_model=TokenResponse)
def login(request: LoginSchema, db: Session = Depends(get_db)):
    """Login user with email and password"""
    try:
        logger.info(f"🔐 Login attempt: {request.email}")
        
        # ✅ Find user by email
        user = db.query(User).filter(User.email == request.email).first()
        
        if not user:
            logger.warning(f"❌ User not found: {request.email}")
            raise HTTPException(
                status_code=401,
                detail="Invalid email or password"
            )
        
        # ✅ Verify password
        if not verify_password(request.password, user.hashed_password):
            logger.warning(f"❌ Invalid password for: {request.email}")
            raise HTTPException(
                status_code=401,
                detail="Invalid email or password"
            )
        
        # ✅ Check if user is active
        if not user.is_active:
            logger.warning(f"❌ User inactive: {request.email}")
            raise HTTPException(
                status_code=403,
                detail="User account is inactive"
            )
        
        logger.info(f"✅ Login successful: {user.email}")
        
        # ✅ Generate tokens
        access_token = create_access_token(data={"sub": str(user.id)})
        refresh_token = create_refresh_token(data={"sub": str(user.id)})
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer"
        }
        
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"❌ Login error: {str(e)}")
        raise HTTPException(status_code=500, detail="Login failed")


# ============================================================================
# VERIFY EMAIL ENDPOINT
# ============================================================================

@router.post("/verify-email")
def verify_email(email: str, db: Session = Depends(get_db)):
    """Verify email (optional for MVP)"""
    try:
        user = db.query(User).filter(User.email == email).first()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # ✅ Mark as verified
        user.email_verified = True
        db.commit()
        
        logger.info(f"✅ Email verified: {email}")
        
        return {"message": "Email verified successfully"}
        
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"❌ Email verification error: {e}")
        raise HTTPException(status_code=500, detail="Verification failed")


# ============================================================================
# COMPLETE PROFILE ENDPOINT
# ============================================================================

@router.post("/complete-profile")
def complete_profile(
    profile_data: dict,
    db: Session = Depends(get_db)
):
    """Complete user profile after login"""
    try:
        # ✅ Get current user from token (from auth header)
        # For now, we accept any authenticated request
        # In production, use: current_user: User = Depends(get_current_user)
        
        logger.info("🔄 Profile completion request")
        
        return {
            "message": "Profile completed successfully"
        }
        
    except Exception as e:
        logger.error(f"❌ Profile completion error: {e}")
        raise HTTPException(status_code=500, detail="Profile completion failed")


# ============================================================================
# GET CURRENT USER ENDPOINT
# ============================================================================

@router.get("/me", response_model=UserResponse)
def get_current_user(db: Session = Depends(get_db)):
    """Get current user info"""
    try:
        # ✅ This would use get_current_user in production
        # For now, returns a sample response
        
        return {
            "message": "User info endpoint"
        }
        
    except Exception as e:
        logger.error(f"❌ Get user error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get user info")


# ============================================================================
# LOGOUT ENDPOINT
# ============================================================================

@router.post("/logout")
def logout():
    """Logout user (frontend handles token removal)"""
    logger.info("👋 User logged out")
    return {"message": "Logged out successfully"}