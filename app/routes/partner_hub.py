# ============================================================================
# Partner Hub: documents, videos, logos, questions, representatives
# File: app/routes/partner_hub.py
# Mounted at /api/v1/partner-hub
#
# Organizers publish directly. Representatives' uploads stay "pending"
# until an organizer approves them.
# ============================================================================

import logging
import os
import re
import uuid
from datetime import datetime
from typing import Any, Optional

import cloudinary
import cloudinary.uploader
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.models import Base, Partnership, User
from app.routes.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

MB = 1024 * 1024
MAX_DOCUMENT_BYTES = 10 * MB
MAX_VIDEO_BYTES = 100 * MB
MAX_IMAGE_BYTES = 5 * MB
MAX_DOCUMENTS_PER_PARTNER = 10

DOCUMENT_TYPES = {
    "application/pdf",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
VIDEO_TYPES = {"video/mp4", "video/quicktime", "video/webm"}
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}

VIDEO_LINK_PATTERN = re.compile(
    r"^https://(www\.)?(youtube\.com/watch\?v=|youtu\.be/|vimeo\.com/)[A-Za-z0-9_\-?=&/.]+$"
)


# ============================================================================
# Database models
# ============================================================================

class PartnerFile(Base):
    __tablename__ = "partner_files"

    id = Column(Integer, primary_key=True, index=True)
    partner_id = Column(
        Integer,
        ForeignKey(f"{Partnership.__tablename__}.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    uploaded_by = Column(
        Integer,
        ForeignKey(f"{User.__tablename__}.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    kind = Column(String(20), nullable=False)          # document | video
    source = Column(String(10), nullable=False)        # upload | link
    title = Column(String(200), nullable=False)
    url = Column(String(500), nullable=False)
    review_status = Column(String(20), nullable=False, default="approved")  # approved | pending
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class PartnerLogo(Base):
    __tablename__ = "partner_logos"

    id = Column(Integer, primary_key=True, index=True)
    partner_id = Column(
        Integer,
        ForeignKey(f"{Partnership.__tablename__}.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    uploaded_by = Column(
        Integer,
        ForeignKey(f"{User.__tablename__}.id", ondelete="SET NULL"),
        nullable=True,
    )
    url = Column(String(500), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class PartnerQuestion(Base):
    __tablename__ = "partner_questions"

    id = Column(Integer, primary_key=True, index=True)
    partner_id = Column(
        Integer,
        ForeignKey(f"{Partnership.__tablename__}.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        Integer,
        ForeignKey(f"{User.__tablename__}.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content = Column(Text, nullable=False)
    answer = Column(Text, nullable=True)
    answered_by = Column(
        Integer,
        ForeignKey(f"{User.__tablename__}.id", ondelete="SET NULL"),
        nullable=True,
    )
    answered_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class PartnerRepresentative(Base):
    __tablename__ = "partner_representatives"
    __table_args__ = (
        UniqueConstraint("partner_id", "user_id", name="uq_partner_representative"),
    )

    id = Column(Integer, primary_key=True, index=True)
    partner_id = Column(
        Integer,
        ForeignKey(f"{Partnership.__tablename__}.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        Integer,
        ForeignKey(f"{User.__tablename__}.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    designation = Column(String(120), nullable=False, default="Representative")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


# ============================================================================
# Schemas
# ============================================================================

class VideoLinkCreate(BaseModel):
    title: str = Field(..., min_length=2, max_length=200)
    url: str = Field(..., min_length=10, max_length=500)


class TextCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=1000)


class RepresentativeCreate(BaseModel):
    user_id: int
    designation: str = Field("Representative", min_length=2, max_length=120)


# ============================================================================
# Helpers
# ============================================================================

def _configure_cloudinary() -> None:
    cloudinary.config(
        cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
        api_key=os.getenv("CLOUDINARY_API_KEY"),
        api_secret=os.getenv("CLOUDINARY_API_SECRET"),
        secure=True,
    )


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def _is_organizer(user: Any) -> bool:
    return bool(getattr(user, "is_admin", False))


def _get_partner_or_404(db: DBSession, partner_id: int) -> Partnership:
    partner = db.query(Partnership).filter(Partnership.id == partner_id).first()
    if partner is None:
        raise HTTPException(status_code=404, detail="Partner not found")
    return partner


def _is_representative(db: DBSession, partner_id: int, user_id: int) -> bool:
    return (
        db.query(PartnerRepresentative.id)
        .filter(
            PartnerRepresentative.partner_id == partner_id,
            PartnerRepresentative.user_id == user_id,
        )
        .first()
        is not None
    )


def _can_manage_partner(db: DBSession, user: Any, partner_id: int) -> bool:
    return _is_organizer(user) or _is_representative(db, partner_id, user.id)


def _require_manager(db: DBSession, user: Any, partner_id: int) -> None:
    if not _can_manage_partner(db, user, partner_id):
        raise HTTPException(
            status_code=403,
            detail="Only the partner's organizer or representatives can do this",
        )


def _read_upload(upload: UploadFile, max_bytes: int, label: str) -> bytes:
    data = upload.file.read(max_bytes + 1)
    if not data:
        raise HTTPException(status_code=400, detail=f"The {label} is empty")
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"The {label} must be {max_bytes // MB} MB or smaller",
        )
    return data


def _cloud_upload(data: bytes, folder: str, resource_type: str) -> str:
    _configure_cloudinary()
    try:
        result = cloudinary.uploader.upload(
            data,
            folder=folder,
            public_id=uuid.uuid4().hex,
            resource_type=resource_type,
            overwrite=False,
        )
    except Exception as exc:
        logger.error("Cloudinary upload failed (%s): %s", resource_type, exc)
        raise HTTPException(status_code=500, detail="Could not store the file. Please try again.")

    url = result.get("secure_url")
    if not url:
        raise HTTPException(status_code=500, detail="Could not store the file. Please try again.")
    return url


def _file_payload(f: PartnerFile) -> dict:
    return {
        "id": f.id,
        "partner_id": f.partner_id,
        "uploaded_by": f.uploaded_by,
        "kind": f.kind,
        "source": f.source,
        "title": f.title,
        "url": f.url,
        "review_status": f.review_status,
        "created_at": _iso(f.created_at),
    }


def _user_summary(db: DBSession, user_id: Optional[int]) -> Optional[dict]:
    if user_id is None:
        return None
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        return None
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username
    return {
        "user_id": user.id,
        "name": full_name,
        "avatar_url": user.avatar_url,
        "job_title": user.job_title,
        "company": user.company,
    }


# ============================================================================
# Documents and videos
# ============================================================================

@router.get("/{partner_id}/files")
def list_partner_files(
    partner_id: int,
    kind: Optional[str] = Query(None, pattern="^(document|video)$"),
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    _get_partner_or_404(db, partner_id)

    query = db.query(PartnerFile).filter(PartnerFile.partner_id == partner_id)
    if kind:
        query = query.filter(PartnerFile.kind == kind)

    if not _is_organizer(current_user):
        # Everyone sees approved files, plus their own pending uploads
        query = query.filter(
            (PartnerFile.review_status == "approved")
            | (PartnerFile.uploaded_by == current_user.id)
        )

    rows = query.order_by(PartnerFile.created_at.desc()).all()
    return {"status": "success", "data": [_file_payload(f) for f in rows]}


@router.post("/{partner_id}/files", status_code=status.HTTP_201_CREATED)
def upload_partner_file(
    partner_id: int,
    title: str = Form(..., min_length=2, max_length=200),
    file: UploadFile = File(...),
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    _get_partner_or_404(db, partner_id)
    _require_manager(db, current_user, partner_id)

    content_type = file.content_type or ""
    if content_type in DOCUMENT_TYPES:
        kind, max_bytes, resource_type = "document", MAX_DOCUMENT_BYTES, "raw"
    elif content_type in VIDEO_TYPES:
        kind, max_bytes, resource_type = "video", MAX_VIDEO_BYTES, "video"
    else:
        raise HTTPException(
            status_code=400,
            detail="Upload a PDF, PowerPoint, Word, Excel, or MP4/MOV/WEBM video",
        )

    if kind == "document":
        count = (
            db.query(PartnerFile)
            .filter(PartnerFile.partner_id == partner_id, PartnerFile.kind == "document")
            .count()
        )
        if count >= MAX_DOCUMENTS_PER_PARTNER:
            raise HTTPException(
                status_code=400,
                detail=f"This partner already has {MAX_DOCUMENTS_PER_PARTNER} documents",
            )

    data = _read_upload(file, max_bytes, kind)
    url = _cloud_upload(data, f"eventai/partners/{partner_id}/{kind}s", resource_type)

    try:
        record = PartnerFile(
            partner_id=partner_id,
            uploaded_by=current_user.id,
            kind=kind,
            source="upload",
            title=title.strip(),
            url=url,
            review_status="approved" if _is_organizer(current_user) else "pending",
        )
        db.add(record)
        db.commit()
        db.refresh(record)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Save partner file failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not save the file")

    return {"status": "success", "data": _file_payload(record)}


@router.post("/{partner_id}/video-links", status_code=status.HTTP_201_CREATED)
def add_video_link(
    partner_id: int,
    payload: VideoLinkCreate,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    _get_partner_or_404(db, partner_id)
    _require_manager(db, current_user, partner_id)

    url = payload.url.strip()
    if not VIDEO_LINK_PATTERN.match(url):
        raise HTTPException(
            status_code=400,
            detail="Paste a YouTube or Vimeo link, for example https://youtu.be/...",
        )

    try:
        record = PartnerFile(
            partner_id=partner_id,
            uploaded_by=current_user.id,
            kind="video",
            source="link",
            title=payload.title.strip(),
            url=url,
            review_status="approved" if _is_organizer(current_user) else "pending",
        )
        db.add(record)
        db.commit()
        db.refresh(record)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Save video link failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not save the video link")

    return {"status": "success", "data": _file_payload(record)}


@router.post("/files/{file_id}/approve")
def approve_partner_file(
    file_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    if not _is_organizer(current_user):
        raise HTTPException(status_code=403, detail="Only organizers can approve files")

    record = db.query(PartnerFile).filter(PartnerFile.id == file_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="File not found")

    try:
        record.review_status = "approved"
        db.commit()
        db.refresh(record)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Approve file failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not approve the file")

    return {"status": "success", "data": _file_payload(record)}


@router.delete("/files/{file_id}")
def delete_partner_file(
    file_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    record = db.query(PartnerFile).filter(PartnerFile.id == file_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="File not found")

    if not (_is_organizer(current_user) or record.uploaded_by == current_user.id):
        raise HTTPException(status_code=403, detail="You can only delete your own uploads")

    try:
        db.delete(record)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Delete file failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not delete the file")

    return {"status": "success", "message": "File deleted"}


# ============================================================================
# Logo (camera or gallery photo)
# ============================================================================

@router.get("/{partner_id}/logo")
def get_partner_logo(
    partner_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    _get_partner_or_404(db, partner_id)
    latest = (
        db.query(PartnerLogo)
        .filter(PartnerLogo.partner_id == partner_id)
        .order_by(PartnerLogo.created_at.desc(), PartnerLogo.id.desc())
        .first()
    )
    return {"status": "success", "data": {"url": latest.url if latest else None}}


@router.post("/{partner_id}/logo", status_code=status.HTTP_201_CREATED)
def upload_partner_logo(
    partner_id: int,
    file: UploadFile = File(...),
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    _get_partner_or_404(db, partner_id)
    _require_manager(db, current_user, partner_id)

    if (file.content_type or "") not in IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Only JPG, PNG, or WEBP images are allowed")

    data = _read_upload(file, MAX_IMAGE_BYTES, "image")
    url = _cloud_upload(data, f"eventai/partners/{partner_id}/logos", "image")

    try:
        record = PartnerLogo(partner_id=partner_id, uploaded_by=current_user.id, url=url)
        db.add(record)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Save partner logo failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not save the logo")

    return {"status": "success", "data": {"url": url}}


# ============================================================================
# Questions and answers
# ============================================================================

@router.get("/{partner_id}/questions")
def list_partner_questions(
    partner_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    _get_partner_or_404(db, partner_id)

    query = (
        db.query(PartnerQuestion)
        .filter(PartnerQuestion.partner_id == partner_id)
        .order_by(PartnerQuestion.created_at.desc(), PartnerQuestion.id.desc())
    )
    total = query.count()
    rows = query.offset((page - 1) * limit).limit(limit).all()

    data = []
    for q in rows:
        data.append({
            "id": q.id,
            "content": q.content,
            "asked_by": _user_summary(db, q.user_id),
            "answer": q.answer,
            "answered_by": _user_summary(db, q.answered_by),
            "answered_at": _iso(q.answered_at),
            "created_at": _iso(q.created_at),
        })

    return {
        "status": "success",
        "total": total,
        "page": page,
        "limit": limit,
        "has_next": page * limit < total,
        "data": data,
    }


@router.post("/{partner_id}/questions", status_code=status.HTTP_201_CREATED)
def ask_partner_question(
    partner_id: int,
    payload: TextCreate,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    _get_partner_or_404(db, partner_id)

    try:
        record = PartnerQuestion(
            partner_id=partner_id,
            user_id=current_user.id,
            content=payload.content.strip(),
        )
        db.add(record)
        db.commit()
        db.refresh(record)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Save partner question failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not post your question")

    return {"status": "success", "data": {"id": record.id, "content": record.content}}


@router.post("/questions/{question_id}/answer")
def answer_partner_question(
    question_id: int,
    payload: TextCreate,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    record = db.query(PartnerQuestion).filter(PartnerQuestion.id == question_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Question not found")

    _require_manager(db, current_user, record.partner_id)

    try:
        record.answer = payload.content.strip()
        record.answered_by = current_user.id
        record.answered_at = datetime.utcnow()
        db.commit()
        db.refresh(record)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Save answer failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not save the answer")

    return {"status": "success", "data": {"id": record.id, "answer": record.answer}}


# ============================================================================
# Representatives (linked to registered user accounts)
# ============================================================================

@router.get("/{partner_id}/representatives")
def list_partner_representatives(
    partner_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    _get_partner_or_404(db, partner_id)
    rows = (
        db.query(PartnerRepresentative)
        .filter(PartnerRepresentative.partner_id == partner_id)
        .order_by(PartnerRepresentative.created_at.asc())
        .all()
    )

    data = []
    for rep in rows:
        person = _user_summary(db, rep.user_id) or {}
        data.append({
            "id": rep.id,
            "user_id": rep.user_id,
            "designation": rep.designation,
            "name": person.get("name"),
            "avatar_url": person.get("avatar_url"),
            "job_title": person.get("job_title"),
            "company": person.get("company"),
        })

    return {"status": "success", "data": data}


@router.post("/{partner_id}/representatives", status_code=status.HTTP_201_CREATED)
def add_partner_representative(
    partner_id: int,
    payload: RepresentativeCreate,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    _get_partner_or_404(db, partner_id)
    if not _is_organizer(current_user):
        raise HTTPException(status_code=403, detail="Only organizers can add representatives")

    person = db.query(User).filter(User.id == payload.user_id).first()
    if person is None:
        raise HTTPException(status_code=404, detail="No registered user with this ID")

    if _is_representative(db, partner_id, payload.user_id):
        raise HTTPException(status_code=400, detail="This person is already a representative")

    try:
        record = PartnerRepresentative(
            partner_id=partner_id,
            user_id=payload.user_id,
            designation=payload.designation.strip(),
        )
        db.add(record)
        db.commit()
        db.refresh(record)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Add representative failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not add the representative")

    return {"status": "success", "data": {"id": record.id, "user_id": record.user_id}}


@router.delete("/{partner_id}/representatives/{representative_id}")
def remove_partner_representative(
    partner_id: int,
    representative_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    if not _is_organizer(current_user):
        raise HTTPException(status_code=403, detail="Only organizers can remove representatives")

    record = (
        db.query(PartnerRepresentative)
        .filter(
            PartnerRepresentative.id == representative_id,
            PartnerRepresentative.partner_id == partner_id,
        )
        .first()
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Representative not found")

    try:
        db.delete(record)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Remove representative failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not remove the representative")

    return {"status": "success", "message": "Representative removed"}