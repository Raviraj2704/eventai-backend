# ============================================================================
# Chat Router - Handles connections, accept/reject, and messaging
# File: app/routes/chat.py
# ============================================================================

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from app.database import get_db
from app.models import ChatConnection, ChatMessage, User

# Adjust this import if your auth dependency is located elsewhere (e.g., app.dependencies)
try:
    from app.routes.auth import get_current_user
except ImportError:
    # Fallback to avoid crashes if auth structure is different
    def get_current_user():
        raise HTTPException(status_code=401, detail="Auth dependency not found")

router = APIRouter()

# --- Schemas ---
class MessageCreate(BaseModel):
    content: str

class RespondRequest(BaseModel):
    status: str  # 'accepted' or 'rejected'

# --- Routes ---

@router.get("/list")
def get_chat_list(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Returns lists of Active Chats, Requests Received, and Requests Sent for the UI tabs.
    """
    uid = current_user.id
    
    connections = db.query(ChatConnection).filter(
        or_(ChatConnection.sender_id == uid, ChatConnection.receiver_id == uid)
    ).all()

    active, received, sent = [], [], []

    for c in connections:
        # Identify the other person in the chat
        is_sender = (c.sender_id == uid)
        other_user = c.receiver if is_sender else c.sender
        
        # Get latest message
        last_message = db.query(ChatMessage).filter(ChatMessage.connection_id == c.id).order_by(ChatMessage.created_at.desc()).first()
        
        name = getattr(other_user, 'name', None) or getattr(other_user, 'full_name', None) or getattr(other_user, 'email', "User")
        
        chat_data = {
            "id": c.id,
            "user_id": other_user.id,
            "name": name,
            "avatar": name[:2].upper() if name else "U",
            "status": c.status,
            "unread": 0,
            "message": last_message.content if last_message else "No messages yet",
            "date": last_message.created_at.strftime("%d %b") if last_message else c.created_at.strftime("%d %b")
        }

        if c.status == "accepted":
            active.append(chat_data)
        elif c.status == "pending" and not is_sender:
            received.append(chat_data)
        elif c.status == "pending" and is_sender:
            sent.append(chat_data)

    return {
        "status": "success",
        "data": {
            "active": active,
            "received": received,
            "sent": sent
        }
    }


@router.post("/request/{target_user_id}")
def send_chat_request(target_user_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Sends a new connection request to another user.
    """
    if target_user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot send a chat request to yourself.")

    target_user = db.query(User).filter(User.id == target_user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found.")

    # Check if a connection already exists
    existing = db.query(ChatConnection).filter(
        or_(
            and_(ChatConnection.sender_id == current_user.id, ChatConnection.receiver_id == target_user_id),
            and_(ChatConnection.sender_id == target_user_id, ChatConnection.receiver_id == current_user.id)
        )
    ).first()

    if existing:
        return {"status": "success", "message": f"Connection already exists with status: {existing.status}", "connection_id": existing.id}

    new_conn = ChatConnection(
        sender_id=current_user.id,
        receiver_id=target_user_id,
        status="pending"
    )
    db.add(new_conn)
    db.commit()
    db.refresh(new_conn)

    return {"status": "success", "message": "Chat request sent.", "connection_id": new_conn.id}


@router.put("/respond/{connection_id}")
def respond_to_request(connection_id: int, req: RespondRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Accepts or rejects an incoming chat request.
    """
    conn = db.query(ChatConnection).filter(ChatConnection.id == connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found.")

    if conn.receiver_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to respond to this request.")

    if req.status not in ["accepted", "rejected"]:
        raise HTTPException(status_code=400, detail="Invalid status. Must be 'accepted' or 'rejected'.")

    conn.status = req.status
    db.commit()

    return {"status": "success", "message": f"Request {req.status} successfully."}


@router.get("/{connection_id}/messages")
def get_messages(connection_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Retrieves chat history for an accepted connection.
    """
    conn = db.query(ChatConnection).filter(ChatConnection.id == connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found.")

    if current_user.id not in [conn.sender_id, conn.receiver_id]:
        raise HTTPException(status_code=403, detail="Not authorized to view these messages.")

    messages = db.query(ChatMessage).filter(ChatMessage.connection_id == connection_id).order_by(ChatMessage.created_at.asc()).all()

    formatted = []
    for m in messages:
        formatted.append({
            "id": m.id,
            "text": m.content,
            "sender": "me" if m.sender_id == current_user.id else "them",
            "time": m.created_at.strftime("%d %b, %I:%M %p")
        })

    return {"status": "success", "connection_status": conn.status, "data": formatted}


@router.post("/{connection_id}/messages")
def send_message(connection_id: int, msg: MessageCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Sends a new message in an active chat.
    """
    conn = db.query(ChatConnection).filter(ChatConnection.id == connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found.")

    if current_user.id not in [conn.sender_id, conn.receiver_id]:
        raise HTTPException(status_code=403, detail="Not authorized to send messages here.")

    if conn.status != "accepted":
        raise HTTPException(status_code=403, detail="You can only send messages in accepted chats.")

    new_msg = ChatMessage(
        connection_id=connection_id,
        sender_id=current_user.id,
        content=msg.content
    )
    
    db.add(new_msg)
    db.commit()
    db.refresh(new_msg)

    return {
        "status": "success", 
        "data": {
            "id": new_msg.id, 
            "text": new_msg.content, 
            "sender": "me", 
            "time": new_msg.created_at.strftime("%d %b, %I:%M %p")
        }
    }
