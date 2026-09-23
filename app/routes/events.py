from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Session as SessionModel

router = APIRouter()

@router.get("/{event_id}")
def get_event_by_id(event_id: int, db: Session = Depends(get_db)):
    """Get specific event details by ID"""
    event = db.query(SessionModel).filter(SessionModel.id == event_id).first()
    
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    return event