# ============================================================================
# Session Admin (Production Ready)
# File: app/routes/session_admin.py
# Mounted at /api/v1/session-admin
#
# Status flow:
#   draft     -> published   (organizer publishes)
#   proposed  -> published   (organizer approves)
#   proposed  -> rejected    (organizer rejects, optional note for the speaker)
#   rejected  -> proposed    (speaker edits and resends)
#   any       -> deleted     (organizer removes; hidden from everyone)
#
# Every change is written to session_admin_audit_logs.
# ============================================================================

import logging
import os
import uuid
from datetime import datetime
from typing import Any, List, Optional

import cloudinary
import cloudinary.uploader
from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.models import Base, Session as SessionModel, Speaker, User
from app.routes.auth import get_current_user
from app.routes.session_hub import SessionExtras

logger = logging.getLogger(__name__)
router = APIRouter()

MB = 1024 * 1024
MAX_IMAGE_BYTES = 5 * MB
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}

DRAFT = "draft"
PROPOSED = "proposed"
PUBLISHED = "published"
REJECTED = "rejected"
DELETED = "deleted"


# ============================================================================
# Audit log (who did what, and when)
# ============================================================================

class SessionAuditLog(Base):
    __tablename__ = "session_admin_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        Integer,
        ForeignKey(f"{SessionModel.__tablename__}.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_user_id = Column(
        Integer,
        ForeignKey(f"{User.__tablename__}.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action = Column(String(40), nullable=False)
    from_status = Column(String(20), nullable=True)
    to_status = Column(String(20), nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


# ============================================================================
# Schemas
# ============================================================================

class SessionBase(BaseModel):
    title: str = Field(..., min_length=3, max_length=255)
    description: str = Field("", max_length=5000)
    start_time: datetime
    end_time: datetime
    location: Optional[str] = Field(None, max_length=255)
    track: Optional[str] = Field(None, max_length=100)
    tags: List[str] = Field(default_factory=list)
    speaker_id: Optional[int] = None

    @model_validator(mode="after")
    def check_times(self):
        if self.end_time <= self.start_time:
            raise ValueError("End time must be after start time")
        return self


class SessionCreate(SessionBase):
    publish: bool = False


class RejectRequest(BaseModel):
    note: Optional[str] = Field(None, max_length=500)


# ============================================================================
# Helpers
# ============================================================================

def _require_admin(current_user: Any) -> None:
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Only organizers can do this")


def _is_speaker(db: DBSession, user_id: int) -> bool:
    return db.query(Speaker.id).filter(Speaker.user_id == user_id).first() is not None


def _check_speaker_user(db: DBSession, user_id: Optional[int]) -> None:
    if user_id is None:
        return
    if db.query(User.id).filter(User.id == user_id).first() is None:
        raise HTTPException(status_code=400, detail="Choose a registered speaker")


def _get_session(db: DBSession, session_id: int) -> SessionModel:
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if session is None or session.status == DELETED:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def _get_extras(db: DBSession, session_id: int) -> Optional[SessionExtras]:
    return db.query(SessionExtras).filter(SessionExtras.session_id == session_id).first()


def _set_extras(db: DBSession, session_id: int, track: Optional[str], tags: List[str]) -> None:
    extras = _get_extras(db, session_id)
    if extras is None:
        extras = SessionExtras(session_id=session_id, is_live=False)
        db.add(extras)
    extras.track = (track or "").strip() or None
    cleaned = ",".join(t.strip() for t in tags if t and t.strip())
    extras.tags = cleaned[:255] or None
    extras.updated_at = datetime.utcnow()


def _audit(
    db: DBSession,
    session_id: int,
    actor_id: Optional[int],
    action: str,
    from_status: Optional[str],
    to_status: Optional[str],
    note: Optional[str] = None,
) -> None:
    db.add(
        SessionAuditLog(
            session_id=session_id,
            actor_user_id=actor_id,
            action=action,
            from_status=from_status,
            to_status=to_status,
            note=note,
        )
    )


def _commit(db: DBSession, action: str, detail: str) -> None:
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("%s failed: %s", action, exc)
        raise HTTPException(status_code=500, detail=detail)


def _latest_rejection_note(db: DBSession, session_id: int) -> Optional[str]:
    row = (
        db.query(SessionAuditLog.note)
        .filter(
            SessionAuditLog.session_id == session_id,
            SessionAuditLog.action == "rejected",
        )
        .order_by(SessionAuditLog.id.desc())
        .first()
    )
    return row[0] if row else None


def _payload(db: DBSession, s: SessionModel, extras: Optional[SessionExtras]) -> dict:
    rejection_note = _latest_rejection_note(db, s.id) if s.status == REJECTED else None
    return {
        "id": s.id,
        "title": s.title,
        "description": s.description or "",
        "location": s.location or "",
        "start_time": s.start_time.isoformat() if s.start_time else None,
        "end_time": s.end_time.isoformat() if s.end_time else None,
        "track": extras.track if extras and extras.track else "",
        "tags": [t for t in (extras.tags or "").split(",") if t] if extras else [],
        "image_url": extras.image_url if extras else None,
        "speaker_id": s.speaker_id,
        "publish_status": s.status,
        "is_published": bool(s.is_published),
        "rejection_note": rejection_note,
    }


def _apply_fields(s: SessionModel, payload: SessionBase) -> None:
    s.title = payload.title.strip()
    s.description = payload.description.strip()
    s.start_time = payload.start_time
    s.end_time = payload.end_time
    s.location = (payload.location or "").strip() or None
    s.speaker_id = payload.speaker_id
    s.updated_at = datetime.utcnow()


def _user_name(user: User) -> str:
    full = f"{user.first_name or ''} {user.last_name or ''}".strip()
    return full or user.username or "Organizer"


def _configure_cloudinary() -> None:
    cloudinary.config(
        cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
        api_key=os.getenv("CLOUDINARY_API_KEY"),
        api_secret=os.getenv("CLOUDINARY_API_SECRET"),
        secure=True,
    )


# ============================================================================
# Roles
# ============================================================================

@router.get("/me/roles")
def my_roles(
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    return {
        "status": "success",
        "data": {
            "is_admin": bool(getattr(current_user, "is_admin", False)),
            "is_speaker": _is_speaker(db, current_user.id),
        },
    }


# ============================================================================
# Organizer: create, edit, publish, remove, photo, history
# ============================================================================

@router.post("/sessions", status_code=201)
def create_session(
    payload: SessionCreate,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    _require_admin(current_user)
    _check_speaker_user(db, payload.speaker_id)

    new_status = PUBLISHED if payload.publish else DRAFT
    s = SessionModel(
        title=payload.title.strip(),
        description=payload.description.strip(),
        start_time=payload.start_time,
        end_time=payload.end_time,
        location=(payload.location or "").strip() or None,
        speaker_id=payload.speaker_id,
        status=new_status,
        is_published=payload.publish,
    )
    db.add(s)
    db.flush()
    _set_extras(db, s.id, payload.track, payload.tags)
    _audit(db, s.id, current_user.id, "created", None, new_status)
    _commit(db, "Create session", "Could not create the session")
    db.refresh(s)

    return {
        "status": "success",
        "message": "Session published" if payload.publish else "Draft saved",
        "data": {"id": s.id, "publish_status": s.status},
    }


@router.put("/sessions/{session_id}")
def update_session(
    session_id: int,
    payload: SessionBase,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    _require_admin(current_user)
    s = _get_session(db, session_id)
    _check_speaker_user(db, payload.speaker_id)

    _apply_fields(s, payload)
    _set_extras(db, s.id, payload.track, payload.tags)
    _audit(db, s.id, current_user.id, "edited", s.status, s.status)
    _commit(db, "Update session", "Could not save the session")

    return {"status": "success", "message": "Session saved", "data": {"id": s.id}}


@router.get("/sessions/{session_id}/manage")
def manage_session(
    session_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    _require_admin(current_user)
    s = _get_session(db, session_id)
    return {"status": "success", "data": _payload(db, s, _get_extras(db, s.id))}


@router.post("/sessions/{session_id}/publish")
def publish_session(
    session_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    _require_admin(current_user)
    s = _get_session(db, session_id)
    if s.status != DRAFT:
        raise HTTPException(
            status_code=400,
            detail="Only drafts can be published. Proposals are approved from Pending.",
        )

    previous = s.status
    s.status = PUBLISHED
    s.is_published = True
    s.updated_at = datetime.utcnow()
    _audit(db, s.id, current_user.id, "published", previous, PUBLISHED)
    _commit(db, "Publish session", "Could not publish the session")

    return {"status": "success", "message": "Session published", "data": {"id": s.id}}


@router.delete("/sessions/{session_id}")
def remove_session(
    session_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    _require_admin(current_user)
    s = _get_session(db, session_id)

    previous = s.status
    s.status = DELETED
    s.is_published = False
    s.updated_at = datetime.utcnow()
    _audit(db, s.id, current_user.id, "removed", previous, DELETED)
    _commit(db, "Remove session", "Could not remove the session")

    return {"status": "success", "message": "Session removed"}


@router.post("/sessions/{session_id}/image", status_code=201)
async def upload_session_image(
    session_id: int,
    file: UploadFile = File(...),
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    _require_admin(current_user)
    s = _get_session(db, session_id)

    if (file.content_type or "") not in IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Only JPG, PNG, or WEBP images are allowed")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="The photo is empty")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="Photo must be 5 MB or smaller")

    _configure_cloudinary()
    try:
        result = cloudinary.uploader.upload(
            data,
            folder=f"eventai/sessions/{s.id}",
            public_id=uuid.uuid4().hex,
            resource_type="image",
            overwrite=False,
            transformation=[{"width": 1200, "height": 675, "crop": "fill"}],
        )
    except Exception as exc:
        logger.error("Cloudinary session image failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not store the photo. Please try again.")

    url = result.get("secure_url")
    if not url:
        raise HTTPException(status_code=500, detail="Could not store the photo. Please try again.")

    extras = _get_extras(db, s.id)
    if extras is None:
        extras = SessionExtras(session_id=s.id, is_live=False)
        db.add(extras)
    extras.image_url = url
    extras.updated_at = datetime.utcnow()
    _audit(db, s.id, current_user.id, "photo_updated", s.status, s.status)
    _commit(db, "Save session image", "Could not save the photo")

    return {"status": "success", "data": {"image_url": url}}


@router.get("/sessions/{session_id}/history")
def session_history(
    session_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    _require_admin(current_user)
    exists = db.query(SessionModel.id).filter(SessionModel.id == session_id).first()
    if exists is None:
        raise HTTPException(status_code=404, detail="Session not found")

    rows = (
        db.query(SessionAuditLog)
        .filter(SessionAuditLog.session_id == session_id)
        .order_by(SessionAuditLog.id.desc())
        .limit(200)
        .all()
    )

    actor_ids = {r.actor_user_id for r in rows if r.actor_user_id}
    names = {}
    if actor_ids:
        for u in db.query(User).filter(User.id.in_(actor_ids)).all():
            names[u.id] = _user_name(u)

    return {
        "status": "success",
        "data": [
            {
                "id": r.id,
                "action": r.action,
                "from_status": r.from_status,
                "to_status": r.to_status,
                "note": r.note,
                "actor_name": names.get(r.actor_user_id, "Organizer"),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


# ============================================================================
# Speakers: propose, edit and resend, see own status
# ============================================================================

@router.post("/proposals", status_code=201)
def propose_session(
    payload: SessionBase,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = current_user.id
    if not (getattr(current_user, "is_admin", False) or _is_speaker(db, me)):
        raise HTTPException(status_code=403, detail="Only registered speakers can propose sessions")

    s = SessionModel(
        title=payload.title.strip(),
        description=payload.description.strip(),
        start_time=payload.start_time,
        end_time=payload.end_time,
        location=(payload.location or "").strip() or None,
        speaker_id=me,
        status=PROPOSED,
        is_published=False,
    )
    db.add(s)
    db.flush()
    _set_extras(db, s.id, payload.track, payload.tags)
    _audit(db, s.id, me, "proposed", None, PROPOSED)
    _commit(db, "Propose session", "Could not send your proposal")
    db.refresh(s)

    return {
        "status": "success",
        "message": "Your proposal was sent to the organizers",
        "data": {"id": s.id, "status": PROPOSED},
    }


@router.put("/proposals/{session_id}")
def update_proposal(
    session_id: int,
    payload: SessionBase,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    s = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if s is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if s.speaker_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only change your own proposals")
    if s.status not in (PROPOSED, REJECTED):
        raise HTTPException(
            status_code=400,
            detail="This proposal can no longer be changed",
        )

    previous = s.status
    _apply_fields(s, payload)
    s.speaker_id = current_user.id
    s.status = PROPOSED
    s.is_published = False
    _set_extras(db, s.id, payload.track, payload.tags)

    action = "resubmitted" if previous == REJECTED else "edited"
    _audit(db, s.id, current_user.id, action, previous, PROPOSED)
    _commit(db, "Update proposal", "Could not save your proposal")

    return {
        "status": "success",
        "message": "Your proposal was sent to the organizers again",
        "data": {"id": s.id, "status": PROPOSED},
    }


@router.get("/proposals")
def list_proposals(
    limit: int = Query(50, ge=1, le=100),
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = current_user.id
    if getattr(current_user, "is_admin", False):
        query = db.query(SessionModel).filter(SessionModel.status == PROPOSED)
    else:
        query = db.query(SessionModel).filter(
            SessionModel.speaker_id == me,
            SessionModel.status.in_([PROPOSED, REJECTED, PUBLISHED]),
        )

    rows = query.order_by(SessionModel.start_time.asc()).limit(limit).all()
    return {
        "status": "success",
        "data": [_payload(db, s, _get_extras(db, s.id)) for s in rows],
    }


# ============================================================================
# Organizer decisions on proposals
# ============================================================================

def _decide(
    db: DBSession,
    session_id: int,
    actor_id: int,
    new_status: str,
    publish: bool,
    note: Optional[str] = None,
) -> SessionModel:
    s = (
        db.query(SessionModel)
        .filter(SessionModel.id == session_id, SessionModel.status == PROPOSED)
        .first()
    )
    if s is None:
        raise HTTPException(
            status_code=404,
            detail="This proposal was not found or was already decided",
        )

    previous = s.status
    s.status = new_status
    s.is_published = publish
    s.updated_at = datetime.utcnow()

    action = "approved" if new_status == PUBLISHED else "rejected"
    _audit(db, s.id, actor_id, action, previous, new_status, note)
    _commit(db, "Decide proposal", "Could not update the proposal")
    db.refresh(s)
    return s


@router.post("/proposals/{session_id}/approve")
def approve_proposal(
    session_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    _require_admin(current_user)
    s = _decide(db, session_id, current_user.id, PUBLISHED, True)
    return {
        "status": "success",
        "message": "Session approved and published",
        "data": _payload(db, s, _get_extras(db, s.id)),
    }


@router.post("/proposals/{session_id}/reject")
def reject_proposal(
    session_id: int,
    payload: Optional[RejectRequest] = Body(default=None),
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    _require_admin(current_user)
    note = (payload.note or "").strip() if payload and payload.note else None
    s = _decide(db, session_id, current_user.id, REJECTED, False, note or None)
    return {
        "status": "success",
        "message": "Proposal rejected",
        "data": {"id": s.id, "status": REJECTED},
    }