from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel
from app.database import get_db
from app.models import User, ChatConnection, ChatMessage

router = APIRouter(prefix="/api/v1/chat", tags=["Chat"])

# --- Pydantic Schemas ---
class ChatRequest(BaseModel):
    receiver_id: int

class ChatRespond(BaseModel):
    status: str  # 'accepted' or 'rejected'

class MessageCreate(BaseModel):
    content: str

# Note: Replace `get_current_user` with your actual auth dependency if it's located elsewhere.
# For now, we will expect a `user_id` query parameter for easy testing, 
# but in production this should be extracted from the JWT token.
def get_user_id(user_id: int) -> int:
    return user_id

@router.get("/list")
async def get_chat_list(user_id: int, db: Session = Depends(get_db)):
    """Groups chats into Active, Request Received, and Request Sent matching the UI tabs."""
    connections = db.query(ChatConnection).filter(
        or_(ChatConnection.sender_id == user_id, ChatConnection.receiver_id == user_id)
    ).all()

    active_chats = []
    requests_received = []
    requests_sent = []

    for conn in connections:
        other_user_id = conn.receiver_id if conn.sender_id == user_id else conn.sender_id
        other_user = db.query(User).filter(User.id == other_user_id).first()
        
        if not other_user:
            continue
            
        chat_data = {
            "connection_id": conn.id,
            "user": {
                "id": other_user.id,
                "name": f"{other_user.first_name} {other_user.last_name}",
                "avatar": other_user.avatar_url
            },
            "status": conn.status,
            "updated_at": conn.updated_at
        }

        if conn.status == "accepted":
            active_chats.append(chat_data)
        elif conn.status == "pending":
            if conn.receiver_id == user_id:
                requests_received.append(chat_data)
            else:
                requests_sent.append(chat_data)

    return {
        "active": active_chats,
        "received": requests_received,
        "sent": requests_sent,
        "total_found": len(active_chats) + len(requests_received) + len(requests_sent)
    }

@router.post("/request")
async def send_chat_request(req: ChatRequest, user_id: int, db: Session = Depends(get_db)):
    """Sends a new chat request to a user (Waiting for approval state)."""
    existing = db.query(ChatConnection).filter(
        or_(
            and_(ChatConnection.sender_id == user_id, ChatConnection.receiver_id == req.receiver_id),
            and_(ChatConnection.sender_id == req.receiver_id, ChatConnection.receiver_id == user_id)
        )
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail=f"Chat connection already exists (Status: {existing.status})")

    new_conn = ChatConnection(sender_id=user_id, receiver_id=req.receiver_id, status="pending")
    db.add(new_conn)
    db.commit()
    db.refresh(new_conn)
    return {"message": "Chat request sent", "connection_id": new_conn.id}

@router.put("/respond/{connection_id}")
async def respond_to_request(connection_id: int, req: ChatRespond, user_id: int, db: Session = Depends(get_db)):
    """Accepts or rejects an inbound chat request."""
    conn = db.query(ChatConnection).filter(ChatConnection.id == connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
        
    if conn.receiver_id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to respond to this request")

    if req.status not in ["accepted", "rejected"]:
        raise HTTPException(status_code=400, detail="Invalid status")

    conn.status = req.status
    conn.updated_at = datetime.utcnow()
    db.commit()
    return {"message": f"Chat request {req.status}", "connection_id": conn.id}

@router.get("/{connection_id}/messages")
async def get_messages(connection_id: int, user_id: int, db: Session = Depends(get_db)):
    """Fetches the message history for a specific chat connection."""
    conn = db.query(ChatConnection).filter(ChatConnection.id == connection_id).first()
    if not conn or (conn.sender_id != user_id and conn.receiver_id != user_id):
        raise HTTPException(status_code=404, detail="Chat not found")

    messages = db.query(ChatMessage).filter(ChatMessage.connection_id == connection_id).order_by(ChatMessage.created_at.asc()).all()
    return {"status": conn.status, "messages": messages}

@router.post("/{connection_id}/messages")
async def send_message(connection_id: int, req: MessageCreate, user_id: int, db: Session = Depends(get_db)):
    """Sends a message in an active chat."""
    conn = db.query(ChatConnection).filter(ChatConnection.id == connection_id).first()
    if not conn or (conn.sender_id != user_id and conn.receiver_id != user_id):
        raise HTTPException(status_code=404, detail="Chat not found")
        
    if conn.status != "accepted":
        raise HTTPException(status_code=403, detail="Cannot send messages. Chat is not active.")

    msg = ChatMessage(connection_id=connection_id, sender_id=user_id, content=req.content)
    db.add(msg)
    conn.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(msg)
    return {"message": "Message sent", "data": msg}