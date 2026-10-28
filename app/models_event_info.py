from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class FAQItem(Base):
    __tablename__ = "faq_items"

    id = Column(Integer, primary_key=True, index=True)
    question = Column(String(500), nullable=False)
    answer = Column(Text, nullable=False)
    category = Column(String(100), default="General")
    display_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

class ContactPerson(Base):
    __tablename__ = "contact_persons"

    id = Column(Integer, primary_key=True, index=True)
    section = Column(String(50), nullable=False)  # "medical" or "organizing"
    name = Column(String(200), nullable=True)     # Medical has name; Organizing is optional
    email = Column(String(200), nullable=True)
    phone = Column(String(50), nullable=True)
    photo_url = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class SupportChatMessage(Base):
    __tablename__ = "support_chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_type = Column(String(20), nullable=False)  # "attendee" or "support"
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)