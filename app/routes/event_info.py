from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User
from app.routes.auth import get_current_user
from app.models_event_info import FAQItem, ContactPerson, SupportChatMessage

router = APIRouter()

# --- Pydantic Schemas ---
class FAQCreate(BaseModel):
    question: str
    answer: str
    category: Optional[str] = "General"
    display_order: Optional[int] = 0

class ContactCreate(BaseModel):
    section: str  # "medical" or "organizing"
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    photo_url: Optional[str] = None

class SupportMessageCreate(BaseModel):
    message: str

def check_admin(current_user: User):
    is_admin = getattr(current_user, "is_admin", False) or current_user.email == "ravirajapanthulu@gmail.com"
    if not is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required")

# ============================================================================
# 1. FAQs Endpoints
# ============================================================================
@router.get("/faqs")
def get_faqs(db: Session = Depends(get_db)):
    faqs = db.query(FAQItem).order_by(FAQItem.display_order.asc(), FAQItem.id.asc()).all()
    # Seed default SHRM reference questions if table is empty
    if not faqs:
        seed_data = [
            ("How can I stay updated on upcoming Indian government events?", "You can enable push notifications in your profile settings and check the Announcements section daily."),
            ("National Women's Parliament", "The session details, hall allocations, and timings are listed in the Agenda tab under Day 1."),
            ("Rashtriya Sarpanch Sansad", "This forum convenes in Hall 3 from 2:00 PM to 4:30 PM. Live questions can be submitted via the Q&A panel."),
            ("UPSC Felicitation/ Social Leadership Development Program", "Eligible registered delegates should collect their program kits from the main registration desk before 11:00 AM.")
        ]
        for q, a in seed_data:
            item = FAQItem(question=q, answer=a)
            db.add(item)
        db.commit()
        faqs = db.query(FAQItem).order_by(FAQItem.id.asc()).all()
    return {"status": "success", "data": faqs}

@router.post("/faqs")
def create_faq(payload: FAQCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    check_admin(current_user)
    item = FAQItem(**payload.dict())
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"status": "success", "data": item}

@router.delete("/faqs/{faq_id}")
def delete_faq(faq_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    check_admin(current_user)
    item = db.query(FAQItem).filter(FAQItem.id == faq_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="FAQ not found")
    db.delete(item)
    db.commit()
    return {"status": "success", "message": "FAQ deleted"}

# ============================================================================
# 2. Contact Us Endpoints
# ============================================================================
@router.get("/contacts")
def get_contacts(db: Session = Depends(get_db)):
    contacts = db.query(ContactPerson).order_by(ContactPerson.id.asc()).all()
    # Seed default prototype contacts if table is empty
    if not contacts:
        db.add(ContactPerson(section="medical", name="Rahul Khanna", email="rahulkhanna23@gmai.com", phone="+91- 98280 98280"))
        db.add(ContactPerson(section="medical", name="Sally Johnson", email="sallyjohnson@gmai.com", phone="+91- 98888 88888"))
        db.add(ContactPerson(section="organizing", name="", email="jenny@gmail.com", phone="+91- 76666 66666"))
        db.add(ContactPerson(section="organizing", name="", email="jenny@gmail.com", phone=""))
        db.add(ContactPerson(section="organizing", name="", email="", phone="+91- 65555 55555"))
        db.commit()
        contacts = db.query(ContactPerson).order_by(ContactPerson.id.asc()).all()
    return {"status": "success", "data": contacts}

@router.post("/contacts")
def create_contact(payload: ContactCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    check_admin(current_user)
    contact = ContactPerson(**payload.dict())
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return {"status": "success", "data": contact}

@router.delete("/contacts/{contact_id}")
def delete_contact(contact_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    check_admin(current_user)
    contact = db.query(ContactPerson).filter(ContactPerson.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    db.delete(contact)
    db.commit()
    return {"status": "success", "message": "Contact deleted"}

# ============================================================================
# 3. Support Chat Endpoints
# ============================================================================
@router.get("/support/messages")
def get_support_messages(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    messages = db.query(SupportChatMessage).filter(SupportChatMessage.user_id == current_user.id).order_by(SupportChatMessage.created_at.asc()).all()
    if not messages:
        # Initial greeting from support
        greeting = SupportChatMessage(user_id=current_user.id, sender_type="support", message="Hello! How can we help you today?")
        db.add(greeting)
        db.commit()
        messages = [greeting]
    return {"status": "success", "data": messages}

@router.post("/support/messages")
def send_support_message(payload: SupportMessageCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    content = payload.message.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    msg = SupportChatMessage(user_id=current_user.id, sender_type="attendee", message=content)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return {"status": "success", "data": msg}

@router.delete("/support/messages/{message_id}")
def delete_support_message(message_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    msg = db.query(SupportChatMessage).filter(SupportChatMessage.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    # Allowed if author or admin
    is_admin = getattr(current_user, "is_admin", False) or current_user.email == "ravirajapanthulu@gmail.com"
    if msg.user_id != current_user.id and not is_admin:
        raise HTTPException(status_code=403, detail="Not authorized to delete this message")
    db.delete(msg)
    db.commit()
    return {"status": "success", "message": "Message deleted"}