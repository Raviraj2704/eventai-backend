# ============================================================================
# Authentication Routes
# ============================================================================
# File: backend/app/routes/auth.py
# Status: Production-Ready ✅

import logging
import base64
import json
import secrets
import smtplib
import os
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.database import get_db
from app.models import User
from app.schemas import RegisterSchema, LoginSchema, TokenResponse
from app.utils.auth import hash_password, verify_password, create_access_token, create_refresh_token, decode_token

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Auth"])
security = HTTPBearer(auto_error=False)

# --- Standard Auth Routes ---

@router.post("/register", response_model=TokenResponse)
def register(request: RegisterSchema, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == request.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    raw_pw = request.password.get_secret_value() if hasattr(request.password, 'get_secret_value') else str(request.password)
    new_user = User(
        username=request.email.split("@")[0],
        first_name=request.first_name,
        last_name=request.last_name,
        email=request.email,
        password_hash=hash_password(raw_pw.strip()[:72]),
        is_active=True,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return {
        "access_token": create_access_token(data={"sub": str(new_user.id)}),
        "refresh_token": create_refresh_token(data={"sub": str(new_user.id)}),
        "token_type": "bearer"
    }

@router.post("/login", response_model=TokenResponse)
def login(request: LoginSchema, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == request.email).first()
    raw_pw = request.password.get_secret_value() if hasattr(request.password, 'get_secret_value') else str(request.password)
    
    if not user or not verify_password(raw_pw.strip()[:72], user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User account is inactive")

    user_role = getattr(user, "role", "admin" if user.is_admin else "user")
    return {
        "access_token": create_access_token(data={"sub": str(user.id)}),
        "token_type": "bearer",
        "user_id": user.id,
        "user_role": user_role,
        "is_admin": user.is_admin,
        "user": {"id": user.id, "email": user.email, "role": user_role, "is_admin": user.is_admin}
    }

class RefreshRequest(BaseModel):
    refresh_token: str

@router.post("/refresh", response_model=TokenResponse)
def refresh_token(request: RefreshRequest, db: Session = Depends(get_db)):
    try:
        parts = request.refresh_token.split(".")
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)).decode('utf-8'))
        user = db.query(User).filter(User.id == int(payload.get("sub"))).first()
        if not user or not user.is_active: raise Exception()
        return {
            "access_token": create_access_token(data={"sub": str(user.id)}),
            "refresh_token": create_refresh_token(data={"sub": str(user.id)}),
            "token_type": "bearer"
        }
    except:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    if not credentials: raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_token(credentials.credentials)
    if not payload: raise HTTPException(status_code=401, detail="Invalid token")
    user = db.query(User).filter(User.id == int(payload.get("sub"))).first()
    if not user or not getattr(user, "is_active", True): raise HTTPException(status_code=401)
    return user

@router.get("/me")
def read_current_user(current_user: User = Depends(get_current_user)):
    return {"id": current_user.id, "email": current_user.email, "role": getattr(current_user, "role", None), "is_admin": bool(getattr(current_user, "is_admin", False))}

@router.post("/logout")
def logout(): return {"message": "Logged out successfully"}

# --- Forgot Password Flow (Render Fix applied) ---

class PasswordResetRequest(BaseModel): email: str
class PasswordResetConfirm(BaseModel): token: str; new_password: str

@router.post("/request-password-reset")
async def request_password_reset(req: PasswordResetRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email.lower().strip()).first()
    if not user: return {"status": "success"} 
    
    token = secrets.token_urlsafe(32)
    
    # Store token in Neon
    db.execute(
        text("UPDATE users SET reset_token = :token, reset_token_expires = :expires WHERE id = :uid"),
        {"token": token, "expires": datetime.utcnow() + timedelta(minutes=15), "uid": user.id}
    )
    db.commit()

    reset_link = f"https://frontend-livid-two-96gqet7oy4.vercel.app/login?token={token}"
    sender_email = os.getenv("SMTP_EMAIL", "ravirajapanthulu@gmail.com")
    sender_pass = os.getenv("SMTP_PASSWORD", "")

    if sender_pass:
        try:
            msg = MIMEMultipart()
            msg['From'] = f"EventAI <{sender_email}>"
            msg['To'] = user.email
            msg['Subject'] = "EventAI - Password Reset Request"
            msg.attach(MIMEText(f"Click here to reset your password (expires in 15 mins):\n\n{reset_link}", 'plain'))
            
            # FIXED FOR RENDER: Using Port 465 (SMTP_SSL) instead of 587 to bypass network blocks
            server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
            server.login(sender_email, sender_pass)
            server.send_message(msg)
            server.quit()
        except Exception as e:
            logger.error(f"Email failed: {e}. Reset link is: {reset_link}")
    else:
        logger.info(f"NO SMTP PASSWORD. LINK IS: {reset_link}")
        
    return {"status": "success", "message": "Link sent."}

@router.post("/reset-password")
async def reset_password(req: PasswordResetConfirm, db: Session = Depends(get_db)):
    user_record = db.execute(
        text("SELECT id FROM users WHERE reset_token = :token AND reset_token_expires > :now"),
        {"token": req.token, "now": datetime.utcnow()}
    ).fetchone()
    
    if not user_record:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link.")
        
    db.execute(
        text("UPDATE users SET password_hash = :hp, reset_token = NULL, reset_token_expires = NULL WHERE id = :uid"),
        {"hp": hash_password(req.new_password), "uid": user_record[0]}
    )
    db.commit()
    return {"status": "success", "message": "Password updated."}