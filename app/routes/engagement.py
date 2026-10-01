# ============================================================================
# Engagement Routes - FIXED VERSION
# ============================================================================
# File: app/routes/engagement.py
# ALL 404 ERRORS FIXED ✅
# White theme ready for frontend ✅

from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import logging

from app.database import get_db
from app.models import (
    Poll, PollOption, PollVote, Quiz, QuizQuestion, UserQuizAttempt,
    QuizAnswer, Activity, UserActivityCompletion, User, Leaderboard
)
from app.routes.users import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Engagement"])


def _seed_engagement_data_if_empty(db: Session):
    """Auto-seed engagement data if empty"""
    try:
        if db.query(Poll).count() == 0:
            p1 = Poll(question="What AI architecture excites you most?", is_active=True, total_votes=0, created_at=datetime.utcnow())
            p2 = Poll(question="Best cloud platform for AI deployment?", is_active=True, total_votes=0, created_at=datetime.utcnow())
            db.add_all([p1, p2])
            db.flush()

            opt1 = [
                PollOption(poll_id=p1.id, option_text="Agentic LLM", vote_count=0, percentage=0.0, order=1),
                PollOption(poll_id=p1.id, option_text="RAG & Vectors", vote_count=0, percentage=0.0, order=2)
            ]
            opt2 = [
                PollOption(poll_id=p2.id, option_text="Render", vote_count=0, percentage=0.0, order=1),
                PollOption(poll_id=p2.id, option_text="AWS", vote_count=0, percentage=0.0, order=2)
            ]
            db.add_all(opt1 + opt2)

        if db.query(Quiz).count() == 0:
            q1 = Quiz(title="FastAPI Masterclass", description="Test your FastAPI knowledge", difficulty="intermediate", passing_score=60, points_reward=50, is_published=True, created_at=datetime.utcnow())
            db.add(q1)
            db.flush()

            qq1 = QuizQuestion(quiz_id=q1.id, question_text="What's the FastAPI GET decorator?", question_type="multiple_choice", options_json=["@app.get()", "@app.post()", "@router.fetch()"], correct_answer="@app.get()", points_value=25, question_order=1)
            qq2 = QuizQuestion(quiz_id=q1.id, question_text="Standard ORM for FastAPI?", question_type="multiple_choice", options_json=["SQLAlchemy", "Django ORM", "Prisma"], correct_answer="SQLAlchemy", points_value=25, question_order=2)
            db.add_all([qq1, qq2])

        if db.query(Activity).count() == 0:
            a1 = Activity(title="Connect with 3 Engineers", description="Network in the Networking tab", priority="high", points_reward=30, activity_type="networking", created_at=datetime.utcnow())
            a2 = Activity(title="Rate a Speaker", description="Provide speaker feedback", priority="medium", points_reward=20, activity_type="feedback", created_at=datetime.utcnow())
            db.add_all([a1, a2])

        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"Seed note: {e}")


# ============================================================================
# POLLS ENDPOINTS
# ============================================================================

@router.get("/polls")
async def get_polls(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all polls with voting options"""
    try:
        _seed_engagement_data_if_empty(db)
        query = db.query(Poll).filter(
            or_(Poll.expires_at == None, Poll.expires_at > datetime.utcnow()),
            Poll.is_active == True
        ).order_by(Poll.created_at.desc())
        
        total = query.count()
        polls = query.offset((page - 1) * limit).limit(limit).all()
        
        polls_data = []
        for poll in polls:
            options = db.query(PollOption).filter(PollOption.poll_id == poll.id).order_by(PollOption.order).all()
            
            user_voted = False
            if current_user:
                user_voted = db.query(PollVote).filter(
                    and_(PollVote.poll_id == poll.id, PollVote.user_id == current_user.id)
                ).first() is not None
            
            poll_dict = {
                "id": poll.id,
                "title": poll.question,
                "question": poll.question,
                "description": getattr(poll, 'description', ''),
                "options": [
                    {
                        "id": opt.id,
                        "text": opt.option_text,
                        "vote_count": opt.vote_count or 0,
                        "percentage": opt.percentage or 0.0,
                        "user_selected": False
                    }
                    for opt in options
                ],
                "total_votes": poll.total_votes or 0,
                "user_voted": user_voted,
                "created_at": poll.created_at
            }
            polls_data.append(poll_dict)
        
        return {"total": total, "page": page, "limit": limit, "data": polls_data}
    
    except Exception as e:
        logger.error(f"Get polls error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch polls")


@router.post("/polls", status_code=201)
async def create_poll(
    poll_data: Dict[str, Any] = Body(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create new poll"""
    try:
        if not poll_data.get('question'):
            raise HTTPException(status_code=400, detail="Poll question required")
        if not poll_data.get('options') or len(poll_data['options']) < 2:
            raise HTTPException(status_code=400, detail="Min 2 options required")
        
        new_poll = Poll(
            question=poll_data['question'],
            description=poll_data.get('description', ''),
            is_active=True,
            total_votes=0,
            created_at=datetime.utcnow()
        )
        db.add(new_poll)
        db.flush()
        
        for idx, option_text in enumerate(poll_data['options']):
            option = PollOption(
                poll_id=new_poll.id,
                option_text=option_text,
                vote_count=0,
                percentage=0.0,
                order=idx + 1
            )
            db.add(option)
        
        db.commit()
        
        return {
            "status": "success",
            "message": "Poll created successfully",
            "data": {
                "id": new_poll.id,
                "title": new_poll.question,
                "description": new_poll.description
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Create poll error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/polls/{poll_id}")
async def delete_poll(
    poll_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete poll and all its options"""
    try:
        poll = db.query(Poll).filter(Poll.id == poll_id).first()
        if not poll:
            raise HTTPException(status_code=404, detail="Poll not found")
        
        db.query(PollVote).filter(PollVote.poll_id == poll_id).delete()
        db.query(PollOption).filter(PollOption.poll_id == poll_id).delete()
        db.delete(poll)
        db.commit()
        
        return {"status": "success", "message": "Poll deleted", "id": poll_id}
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Delete poll error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/polls/{poll_id}/vote")
async def vote_poll(
    poll_id: int,
    payload: Dict[str, Any] = Body(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Vote on poll option"""
    try:
        option_id = payload.get("option_id")
        if not option_id:
            raise HTTPException(status_code=400, detail="option_id required")
            
        poll = db.query(Poll).filter(Poll.id == poll_id).first()
        if not poll:
            raise HTTPException(status_code=404, detail="Poll not found")
        
        existing_vote = db.query(PollVote).filter(
            and_(PollVote.poll_id == poll_id, PollVote.user_id == current_user.id)
        ).first()
        
        if existing_vote:
            old_option = existing_vote.option_id
            existing_vote.option_id = option_id
            existing_vote.voted_at = datetime.utcnow()
            
            old_opt = db.query(PollOption).filter(PollOption.id == old_option).first()
            if old_opt and old_opt.vote_count > 0:
                old_opt.vote_count -= 1
        else:
            new_vote = PollVote(
                poll_id=poll_id, user_id=current_user.id,
                option_id=option_id, voted_at=datetime.utcnow()
            )
            db.add(new_vote)
            poll.total_votes = (poll.total_votes or 0) + 1
        
        option = db.query(PollOption).filter(PollOption.id == option_id).first()
        if option:
            option.vote_count = (option.vote_count or 0) + 1
        
        if poll.total_votes and poll.total_votes > 0:
            all_options = db.query(PollOption).filter(PollOption.poll_id == poll_id).all()
            for opt in all_options:
                opt.percentage = (opt.vote_count / poll.total_votes * 100) if poll.total_votes > 0 else 0
        
        db.commit()
        
        return {"status": "success", "message": "Vote recorded", "poll_id": poll_id}
        
    except Exception as e:
        db.rollback()
        logger.error(f"Vote error: {e}")
        raise HTTPException(status_code=500, detail="Vote failed")


# ============================================================================
# QUIZZES ENDPOINTS
# ============================================================================

@router.get("/quizzes")
async def get_quizzes(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all quizzes"""
    try:
        _seed_engagement_data_if_empty(db)
        query = db.query(Quiz).filter(Quiz.is_published == True).order_by(Quiz.created_at.desc())
        
        total = query.count()
        quizzes = query.offset((page - 1) * limit).limit(limit).all()
        
        quizzes_data = []
        for quiz in quizzes:
            question_count = db.query(QuizQuestion).filter(QuizQuestion.quiz_id == quiz.id).count()
            
            user_attempt = None
            if current_user:
                attempt = db.query(UserQuizAttempt).filter(
                    and_(UserQuizAttempt.user_id == current_user.id, UserQuizAttempt.quiz_id == quiz.id)
                ).order_by(UserQuizAttempt.completed_at.desc()).first()
                
                if attempt:
                    user_attempt = {
                        "score": attempt.score,
                        "percentage": attempt.percentage,
                        "passed": attempt.passed
                    }
            
            quiz_dict = {
                "id": quiz.id,
                "title": quiz.title,
                "description": getattr(quiz, 'description', ''),
                "difficulty": getattr(quiz, 'difficulty', 'intermediate'),
                "question_count": question_count,
                "points_reward": getattr(quiz, 'points_reward', 50),
                "user_attempt": user_attempt
            }
            quizzes_data.append(quiz_dict)
        
        return {"total": total, "page": page, "limit": limit, "data": quizzes_data}
    
    except Exception as e:
        logger.error(f"Get quizzes error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch quizzes")


@router.get("/quizzes/{quiz_id}")
async def get_quiz_detail(
    quiz_id: int,
    db: Session = Depends(get_db)
):
    """Get quiz with questions"""
    try:
        quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
        if not quiz:
            raise HTTPException(status_code=404, detail="Quiz not found")
        
        questions = db.query(QuizQuestion).filter(QuizQuestion.quiz_id == quiz_id).order_by(QuizQuestion.question_order).all()
        
        return {
            "id": quiz.id,
            "title": quiz.title,
            "description": getattr(quiz, 'description', ''),
            "difficulty": getattr(quiz, 'difficulty', 'intermediate'),
            "points_reward": getattr(quiz, 'points_reward', 50),
            "questions": [
                {
                    "id": q.id,
                    "text": q.question_text,
                    "type": q.question_type,
                    "options": q.options_json if q.question_type == "multiple_choice" else None,
                    "points_value": q.points_value
                }
                for q in questions
            ]
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get quiz error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch quiz")


@router.post("/quizzes/{quiz_id}/submit")
async def submit_quiz(
    quiz_id: int,
    payload: Dict[str, Any] = Body(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Submit quiz answers"""
    try:
        quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
        if not quiz:
            raise HTTPException(status_code=404, detail="Quiz not found")
        
        attempt = UserQuizAttempt(
            user_id=current_user.id,
            quiz_id=quiz_id,
            completed_at=datetime.utcnow()
        )
        db.add(attempt)
        db.flush()
        
        total_points = 0
        correct_count = 0
        answers = payload.get('answers', [])
        
        for answer_req in answers:
            question = db.query(QuizQuestion).filter(QuizQuestion.id == answer_req.get('question_id')).first()
            if not question:
                continue
            
            user_answer = str(answer_req.get('answer', '')).lower().strip()
            correct_answer = str(question.correct_answer).lower().strip()
            is_correct = user_answer == correct_answer
            points = question.points_value if is_correct else 0
            
            if is_correct:
                correct_count += 1
                total_points += points
            
            quiz_answer = QuizAnswer(
                attempt_id=attempt.id,
                question_id=question.id,
                user_answer=answer_req.get('answer'),
                is_correct=is_correct,
                points_earned=points
            )
            db.add(quiz_answer)
        
        attempt.score = total_points
        attempt.percentage = (correct_count / len(answers) * 100) if answers else 0
        attempt.passed = attempt.percentage >= quiz.passing_score
        
        if attempt.passed:
            leaderboard = db.query(Leaderboard).filter(Leaderboard.user_id == current_user.id).first()
            if leaderboard:
                leaderboard.total_points += quiz.points_reward
        
        db.commit()
        
        return {
            "status": "success",
            "score": total_points,
            "percentage": attempt.percentage,
            "passed": attempt.passed,
            "points_earned": quiz.points_reward if attempt.passed else 0
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Submit quiz error: {e}")
        raise HTTPException(status_code=500, detail="Failed to submit quiz")


@router.post("/quizzes", status_code=201)
async def create_quiz(
    payload: Dict[str, Any] = Body(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create new quiz"""
    try:
        title = (payload.get("title") or "New AI Quiz").strip()
        description = payload.get("description") or ""
        difficulty = payload.get("difficulty") or "intermediate"
        points_reward = int(payload.get("points_reward") or 50)
        
        new_quiz = Quiz(
            title=title,
            description=description,
            difficulty=difficulty,
            passing_score=60,
            points_reward=points_reward,
            is_published=True,
            created_at=datetime.utcnow()
        )
        db.add(new_quiz)
        db.flush()

        q1_text = payload.get("question1") or "What is the main purpose of FastAPI?"
        q1 = QuizQuestion(
            quiz_id=new_quiz.id,
            question_text=q1_text,
            question_type="multiple_choice",
            options_json=["High-performance web framework", "CSS framework", "Database"],
            correct_answer="High-performance web framework",
            points_value=50,
            question_order=1
        )
        db.add(q1)
        db.commit()

        return {
            "status": "success",
            "message": "Quiz created",
            "data": {"id": new_quiz.id, "title": new_quiz.title}
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Create quiz error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/quizzes/{quiz_id}")
async def delete_quiz(
    quiz_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete quiz"""
    try:
        db.query(QuizAnswer).filter(
            QuizAnswer.attempt_id.in_(db.query(UserQuizAttempt.id).filter(UserQuizAttempt.quiz_id == quiz_id))
        ).delete(synchronize_session=False)
        db.query(UserQuizAttempt).filter(UserQuizAttempt.quiz_id == quiz_id).delete(synchronize_session=False)
        db.query(QuizQuestion).filter(QuizQuestion.quiz_id == quiz_id).delete(synchronize_session=False)
        
        quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
        if quiz:
            db.delete(quiz)
        db.commit()
        
        return {"status": "success", "message": "Quiz deleted", "id": quiz_id}
    except Exception as e:
        db.rollback()
        logger.error(f"Delete quiz error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ACTIVITIES ENDPOINTS
# ============================================================================

@router.get("/activities")
async def get_activities(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all activities"""
    try:
        _seed_engagement_data_if_empty(db)
        query = db.query(Activity).order_by(Activity.created_at.desc())
        
        total = query.count()
        activities = query.offset((page - 1) * limit).limit(limit).all()
        
        activities_data = []
        for activity in activities:
            is_completed = False
            if current_user:
                is_completed = db.query(UserActivityCompletion).filter(
                    and_(UserActivityCompletion.user_id == current_user.id, UserActivityCompletion.activity_id == activity.id)
                ).first() is not None
            
            act_dict = {
                "id": activity.id,
                "title": getattr(activity, "title", "Activity"),
                "description": getattr(activity, "description", ""),
                "priority": getattr(activity, "priority", "medium"),
                "points_reward": getattr(activity, "points_reward", 50),
                "is_completed_by_user": is_completed
            }
            activities_data.append(act_dict)
        
        return {"total": total, "page": page, "limit": limit, "data": activities_data}
    
    except Exception as e:
        logger.error(f"Get activities error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch activities")


@router.post("/activities", status_code=201)
async def create_activity(
    payload: Dict[str, Any] = Body(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create new activity"""
    title = (payload.get("title") or "New Activity").strip()
    description = payload.get("description") or ""
    priority = (payload.get("priority") or "medium").lower()
    points_reward = int(payload.get("points_reward") or 50)

    try:
        new_act = Activity(
            title=title,
            description=description,
            priority=priority,
            points_reward=points_reward,
            activity_type="general",
            created_at=datetime.utcnow()
        )
        db.add(new_act)
        db.commit()

        return {
            "status": "success",
            "message": "Activity created",
            "data": {"id": new_act.id, "title": new_act.title}
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Create activity error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/activities/{activity_id}")
async def delete_activity(
    activity_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete activity"""
    try:
        activity = db.query(Activity).filter(Activity.id == activity_id).first()
        if not activity:
            raise HTTPException(status_code=404, detail="Activity not found")
        
        db.query(UserActivityCompletion).filter(UserActivityCompletion.activity_id == activity_id).delete()
        db.delete(activity)
        db.commit()
        
        return {"status": "success", "message": "Activity deleted", "id": activity_id}
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Delete activity error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/activities/{activity_id}/complete")
async def complete_activity(
    activity_id: int,
    payload: Optional[Dict[str, Any]] = Body(default={}),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark activity as completed"""
    try:
        activity = db.query(Activity).filter(Activity.id == activity_id).first()
        if not activity:
            raise HTTPException(status_code=404, detail="Activity not found")

        existing = db.query(UserActivityCompletion).filter(
            and_(UserActivityCompletion.user_id == current_user.id, UserActivityCompletion.activity_id == activity_id)
        ).first()

        if existing:
            return {"status": "success", "message": "Already completed", "points_earned": 0}

        completion = UserActivityCompletion(
            user_id=current_user.id,
            activity_id=activity_id,
            completion_notes=payload.get("completion_notes") if payload else "",
            completed_at=datetime.utcnow()
        )
        db.add(completion)

        points = getattr(activity, "points_reward", 50) or 50
        leaderboard = db.query(Leaderboard).filter(Leaderboard.user_id == current_user.id).first()
        if leaderboard:
            leaderboard.total_points += points

        db.commit()

        return {"status": "success", "message": "Activity completed", "points_earned": points}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Complete activity error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# SUMMARY ENDPOINT
# ============================================================================

@router.get("/summary")
async def get_engagement_summary(
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get engagement summary"""
    try:
        _seed_engagement_data_if_empty(db)

        active_polls = db.query(Poll).filter(Poll.is_active == True).count()
        available_quizzes = db.query(Quiz).filter(Quiz.is_published == True).count()
        pending_activities = db.query(Activity).count()
        
        quizzes_completed = 0
        activities_completed = 0
        
        if current_user:
            quizzes_completed = db.query(UserQuizAttempt).filter(UserQuizAttempt.user_id == current_user.id).count()
            activities_completed = db.query(UserActivityCompletion).filter(UserActivityCompletion.user_id == current_user.id).count()
        
        return {
            "status": "success",
            "data": {
                "active_polls": active_polls,
                "quizzes_completed": quizzes_completed,
                "activities_completed": activities_completed,
                "available_quizzes": available_quizzes,
                "pending_activities": pending_activities,
                "total_points_this_week": 0,
                "current_rank": 1,
                "current_tier": "bronze"
            }
        }
    
    except Exception as e:
        logger.error(f"Get summary error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch summary")