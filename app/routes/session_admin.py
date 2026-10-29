# ============================================================================
# Session Admin: create, edit, publish, remove, speaker proposals, photos
# File: app/routes/session_admin.py
# Mounted at /api/v1/session-admin
#
# GET    /me/roles                    { is_admin, is_speaker }
# POST   /sessions                    admin: create (draft or published)
# PUT    /sessions/{id}               admin: edit details
# GET    /sessions/{id}/manage        admin: full data for the edit form
# POST   /sessions/{id}/publish       admin: publish a draft
# DELETE /sessions/{id}               admin: remove (hidden from everyone)
# POST   /sessions/{id}/image         admin: upload a photo (camera or gallery)
# POST   /proposals                   speaker or admin: propose a session
# GET    /proposals                   admin: pending; speaker: own proposals
# POST   /proposals/{id}/approve      admin: approve and publish
# POST   /proposals/{id}/reject       admin: reject
# ============================================================================

import logging
import os
import uuid
from datetime import datetime
from typing import Any, List, Optional

import cloudinary
import cloudinary.uploader
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.models import Session as SessionModel, Speaker, User
from app.routes.auth import get_current_user
from app.routes.session_hub import SessionExtras

logger = logging.getLogger(__name__)
router = APIRouter()

MB = 1024 * 1024
MAX_IMAGE_BYTES = 5 * MB
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


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
    if session is None or session.status == "deleted":
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


def _commit(db: DBSession, action: str, detail: str) -> None:
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("%s failed: %s", action, exc)
        raise HTTPException(status_code=500, detail=detail)


def _payload(s: SessionModel, extras: Optional[SessionExtras]) -> dict:
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
    }


def _apply_fields(s: SessionModel, payload: SessionBase) -> None:
    s.title = payload.title.strip()
    s.description = payload.description.strip()
    s.start_time = payload.start_time
    s.end_time = payload.end_time
    s.location = (payload.location or "").strip() or None
    s.speaker_id = payload.speaker_id
    s.updated_at = datetime.utcnow()


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
# Admin: create, edit, publish, remove
# ============================================================================

@router.post("/sessions", status_code=201)
def create_session(
    payload: SessionCreate,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    _require_admin(current_user)
    _check_speaker_user(db, payload.speaker_id)

    s = SessionModel(
        title=payload.title.strip(),
        description=payload.description.strip(),
        start_time=payload.start_time,
        end_time=payload.end_time,
        location=(payload.location or "").strip() or None,
        speaker_id=payload.speaker_id,
        status="published" if payload.publish else "draft",
        is_published=payload.publish,
    )
    db.add(s)
    db.flush()
    _set_extras(db, s.id, payload.track, payload.tags)
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
    return {"status": "success", "data": _payload(s, _get_extras(db, s.id))}


@router.post("/sessions/{session_id}/publish")
def publish_session(
    session_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    _require_admin(current_user)
    s = _get_session(db, session_id)
    s.status = "published"
    s.is_published = True
    s.updated_at = datetime.utcnow()
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
    s.status = "deleted"
    s.is_published = False
    s.updated_at = datetime.utcnow()
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
    _commit(db, "Save session image", "Could not save the photo")

    return {"status": "success", "data": {"image_url": url}}


# ============================================================================
# Speaker proposals and admin decisions
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
        status="proposed",
        is_published=False,
    )
    db.add(s)
    db.flush()
    _set_extras(db, s.id, payload.track, payload.tags)
    _commit(db, "Propose session", "Could not send your proposal")
    db.refresh(s)

    return {
        "status": "success",
        "message": "Your proposal was sent to the organizers",
        "data": {"id": s.id, "status": "proposed"},
    }


@router.get("/proposals")
def list_proposals(
    limit: int = Query(50, ge=1, le=100),
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    me = current_user.id
    if getattr(current_user, "is_admin", False):
        query = db.query(SessionModel).filter(SessionModel.status == "proposed")
    else:
        query = db.query(SessionModel).filter(
            SessionModel.speaker_id == me,
            SessionModel.status.in_(["proposed", "rejected", "published"]),
        )

    rows = query.order_by(SessionModel.start_time.asc()).limit(limit).all()
    return {
        "status": "success",
        "data": [_payload(s, _get_extras(db, s.id)) for s in rows],
    }


def _decide(db: DBSession, session_id: int, new_status: str, publish: bool) -> SessionModel:
    s = (
        db.query(SessionModel)
        .filter(SessionModel.id == session_id, SessionModel.status == "proposed")
        .first()
    )
    if s is None:
        raise HTTPException(status_code=404, detail="This proposal was not found or was already decided")
    s.status = new_status
    s.is_published = publish
    s.updated_at = datetime.utcnow()
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
    s = _decide(db, session_id, "published", True)
    return {"status": "success", "message": "Session approved and published", "data": _payload(s, _get_extras(db, s.id))}


@router.post("/proposals/{session_id}/reject")
def reject_proposal(
    session_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    _require_admin(current_user)
    s = _decide(db, session_id, "rejected", False)
    return {"status": "success", "message": "Proposal rejected", "data": {"id": s.id}}