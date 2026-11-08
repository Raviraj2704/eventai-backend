# ============================================================================
# Feedback Forms (Production Ready)
# File: app/routes/feedback_forms.py
# Mounted at /api/v1/feedback-forms
#
# GET    /active                 attendees: the published form (if any)
# POST   /forms                  admin: create a form (draft)
# GET    /forms                  admin: list all forms
# POST   /forms/{id}/publish     admin: publish (closes any other published form)
# POST   /forms/{id}/close       admin: stop taking responses
# GET    /forms/{id}/results     admin: counts per answer
# POST   /forms/{id}/responses   attendee: submit once per form
# ============================================================================

import logging
from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.models import Base, User
from app.routes.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

QUESTION_TYPES = {"radio", "checkbox", "dropdown", "emoji"}
EMOJI_SCALE = ["😡", "😕", "😐", "🙂", "😍"]


# ============================================================================
# Database models
# ============================================================================

class FeedbackForm(Base):
    __tablename__ = "feedback_forms"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="draft", index=True)  # draft | published | closed
    questions_json = Column(Text, nullable=False, default="[]")
    created_by = Column(Integer, ForeignKey(f"{User.__tablename__}.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    published_at = Column(DateTime, nullable=True)


class FeedbackResponse(Base):
    __tablename__ = "feedback_responses"
    __table_args__ = (
        UniqueConstraint("form_id", "user_id", name="uq_feedback_form_user"),
    )

    id = Column(Integer, primary_key=True, index=True)
    form_id = Column(Integer, ForeignKey("feedback_forms.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey(f"{User.__tablename__}.id", ondelete="CASCADE"), nullable=False, index=True)
    answers_json = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


# ============================================================================
# Schemas
# ============================================================================

class QuestionIn(BaseModel):
    text: str = Field(..., min_length=2, max_length=300)
    type: str = Field(..., pattern="^(radio|checkbox|dropdown|emoji)$")
    options: List[str] = Field(default_factory=list)
    required: bool = True

    @model_validator(mode="after")
    def check_options(self):
        if self.type == "emoji":
            self.options = EMOJI_SCALE
        elif self.type in ("radio", "checkbox", "dropdown"):
            cleaned = [o.strip() for o in self.options if o and o.strip()]
            if len(cleaned) < 2:
                raise ValueError(f"'{self.text}' needs at least 2 options")
            self.options = cleaned
        return self


class FormCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    questions: List[QuestionIn] = Field(..., min_length=1, max_length=30)


class ResponseCreate(BaseModel):
    answers: dict = Field(...)  # {question_index: value}


# ============================================================================
# Helpers
# ============================================================================

def _require_admin(current_user: Any) -> None:
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Only organizers can do this")


def _get_form(db: DBSession, form_id: int) -> FeedbackForm:
    form = db.query(FeedbackForm).filter(FeedbackForm.id == form_id).first()
    if form is None:
        raise HTTPException(status_code=404, detail="Form not found")
    return form


def _questions(form: FeedbackForm) -> list:
    import json
    try:
        return json.loads(form.questions_json or "[]")
    except ValueError:
        return []


def _form_payload(form: FeedbackForm) -> dict:
    return {
        "id": form.id,
        "title": form.title,
        "description": form.description or "",
        "status": form.status,
        "questions": _questions(form),
        "created_at": form.created_at.isoformat() if form.created_at else None,
    }


def _commit(db: DBSession, action: str, detail: str) -> None:
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("%s failed: %s", action, exc)
        raise HTTPException(status_code=500, detail=detail)


# ============================================================================
# Attendee
# ============================================================================

@router.get("/active")
def get_active_form(
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    form = (
        db.query(FeedbackForm)
        .filter(FeedbackForm.status == "published")
        .order_by(FeedbackForm.published_at.desc())
        .first()
    )
    if form is None:
        return {"status": "success", "data": None}

    already = (
        db.query(FeedbackResponse.id)
        .filter(FeedbackResponse.form_id == form.id, FeedbackResponse.user_id == current_user.id)
        .first()
    )
    payload = _form_payload(form)
    payload["already_submitted"] = already is not None
    return {"status": "success", "data": payload}


@router.post("/forms/{form_id}/responses", status_code=status.HTTP_201_CREATED)
def submit_response(
    form_id: int,
    payload: ResponseCreate,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    import json

    form = _get_form(db, form_id)
    if form.status != "published":
        raise HTTPException(status_code=400, detail="This form is not open for responses")

    questions = _questions(form)
    cleaned = {}
    for index, question in enumerate(questions):
        value = payload.answers.get(str(index), payload.answers.get(index))
        required = question.get("required", True)

        if question["type"] == "checkbox":
            values = value if isinstance(value, list) else ([] if value in (None, "") else [value])
            values = [str(v) for v in values if str(v) in question["options"]]
            if required and not values:
                raise HTTPException(status_code=400, detail=f"Please answer: {question['text']}")
            cleaned[str(index)] = values
        else:
            if value in (None, ""):
                if required:
                    raise HTTPException(status_code=400, detail=f"Please answer: {question['text']}")
                cleaned[str(index)] = None
                continue
            if str(value) not in question["options"]:
                raise HTTPException(status_code=400, detail=f"Choose a valid answer for: {question['text']}")
            cleaned[str(index)] = str(value)

    try:
        db.add(FeedbackResponse(
            form_id=form.id,
            user_id=current_user.id,
            answers_json=json.dumps(cleaned),
        ))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="You have already sent your feedback")
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Save feedback response failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not save your feedback")

    return {"status": "success", "message": "Thank you! Your feedback has been submitted"}


# ============================================================================
# Admin
# ============================================================================

@router.post("/forms", status_code=status.HTTP_201_CREATED)
def create_form(
    payload: FormCreate,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    import json

    _require_admin(current_user)
    form = FeedbackForm(
        title=payload.title.strip(),
        description=(payload.description or "").strip() or None,
        status="draft",
        questions_json=json.dumps([q.model_dump() for q in payload.questions]),
        created_by=current_user.id,
    )
    db.add(form)
    _commit(db, "Create feedback form", "Could not create the form")
    db.refresh(form)
    return {"status": "success", "message": "Form saved as draft", "data": _form_payload(form)}


@router.get("/forms")
def list_forms(
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    _require_admin(current_user)
    rows = db.query(FeedbackForm).order_by(FeedbackForm.created_at.desc()).all()
    return {"status": "success", "data": [_form_payload(f) for f in rows]}


@router.post("/forms/{form_id}/publish")
def publish_form(
    form_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    _require_admin(current_user)
    form = _get_form(db, form_id)

    # Only one form is open at a time, so attendees see one clear survey
    db.query(FeedbackForm).filter(
        FeedbackForm.status == "published",
        FeedbackForm.id != form.id,
    ).update({"status": "closed"}, synchronize_session=False)

    form.status = "published"
    form.published_at = datetime.utcnow()
    _commit(db, "Publish feedback form", "Could not publish the form")
    return {"status": "success", "message": "Form is now open to attendees"}


@router.post("/forms/{form_id}/close")
def close_form(
    form_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    _require_admin(current_user)
    form = _get_form(db, form_id)
    form.status = "closed"
    _commit(db, "Close feedback form", "Could not close the form")
    return {"status": "success", "message": "Form closed"}


@router.get("/forms/{form_id}/results")
def form_results(
    form_id: int,
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    import json
    from collections import Counter

    _require_admin(current_user)
    form = _get_form(db, form_id)
    questions = _questions(form)

    total = db.query(func.count(FeedbackResponse.id)).filter(
        FeedbackResponse.form_id == form.id
    ).scalar() or 0

    rows = db.query(FeedbackResponse.answers_json).filter(
        FeedbackResponse.form_id == form.id
    ).all()

    tallies = {str(i): Counter() for i in range(len(questions))}
    for (raw,) in rows:
        try:
            answers = json.loads(raw)
        except ValueError:
            continue
        for key, value in answers.items():
            if key not in tallies or value is None:
                continue
            values = value if isinstance(value, list) else [value]
            for v in values:
                tallies[key][v] += 1

    results = []
    for index, question in enumerate(questions):
        counts = tallies[str(index)]
        results.append({
            "text": question["text"],
            "type": question["type"],
            "options": [
                {"label": opt, "count": counts.get(opt, 0)}
                for opt in question["options"]
            ],
        })

    return {
        "status": "success",
        "data": {"form_id": form.id, "title": form.title, "total_responses": total, "questions": results},
    }