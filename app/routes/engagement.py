# ============================================================================
# Engagement Routes
# ============================================================================
# File: app/routes/engagement.py
# Purpose: Engagement center - polls, quizzes, activities
# Status: Production-Ready ✅
# NOTE: Page 21 - Engagement Center features

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from datetime import datetime
from typing import Optional, List
import logging

from app.database import get_db
from app.models import (
    Poll, PollOption, PollVote, Quiz, QuizQuestion, UserQuizAttempt,
    QuizAnswer, Activity, UserActivityCompletion, User, Leaderboard,
    Challenge, UserChallenge, Badge
)
from app.schemas import (
    PollResponse, PollVoteRequest, QuizResponse, QuizDetailResponse,
    QuizSubmitRequest, QuizSubmitResponse, ActivityResponse,
    ActivityDetailResponse, ActivityCompleteRequest,
    EngagementSummaryResponse, ErrorResponse
)
from app.routes.users import get_current_user


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/engagement", tags=["Engagement"])


# ============================================================================
# POLLS - GET ALL ACTIVE POLLS
# ============================================================================

@router.get(
    "/polls",
    response_model=dict,
    responses={400: {"model": ErrorResponse}}
)
async def get_polls(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    status_filter: Optional[str] = "active",
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all polls with options
    
    Args:
        page: Page number
        limit: Results per page
        status_filter: active/expired
        current_user: Optional authenticated user
        db: Database session
    
    Returns:
        dict: Paginated polls list
    """
    try:
        query = db.query(Poll)
        
        if status_filter == "active":
            query = query.filter(
                or_(
                    Poll.expires_at == None,
                    Poll.expires_at > datetime.utcnow()
                ),
                Poll.is_active == True
            )
        elif status_filter == "expired":
            query = query.filter(
                Poll.expires_at <= datetime.utcnow()
            )
        
        query = query.order_by(Poll.created_at.desc())
        
        total = query.count()
        polls = query.offset((page - 1) * limit).limit(limit).all()
        
        polls_data = []
        for poll in polls:
            poll_resp = PollResponse.model_validate(poll)
            
            # Get options
            options = db.query(PollOption).filter(
                PollOption.poll_id == poll.id
            ).order_by(PollOption.order).all()
            
            poll_resp.options = [
                {
                    "id": opt.id,
                    "text": opt.option_text,
                    "vote_count": opt.vote_count,
                    "percentage": opt.percentage,
                    "user_selected": False
                }
                for opt in options
            ]
            
            # Check if user voted
            if current_user:
                user_vote = db.query(PollVote).filter(
                    and_(
                        PollVote.poll_id == poll.id,
                        PollVote.user_id == current_user.id
                    )
                ).first()
                
                poll_resp.user_voted = user_vote is not None
                
                if user_vote:
                    for opt in poll_resp.options:
                        if opt["id"] == user_vote.option_id:
                            opt["user_selected"] = True
            
            polls_data.append(poll_resp)
        
        return {
            "total": total,
            "page": page,
            "limit": limit,
            "data": polls_data
        }
    
    except Exception as e:
        logger.error(f"Get polls error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch polls"
        )


# ============================================================================
# POLLS - VOTE ON POLL
# ============================================================================

@router.post(
    "/polls/{poll_id}/vote",
    response_model=dict,
    responses={
        401: {"model": ErrorResponse}, 
        404: {"model": ErrorResponse}, 
        409: {"model": ErrorResponse}
    }
)
async def vote_poll(
    poll_id: int,
    request: PollVoteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Vote on a poll
    
    Args:
        poll_id: Poll ID
        request: Vote option ID
        current_user: Authenticated user
        db: Database session
    
    Returns:
        dict: Updated poll results
    """
    try:
        # Get poll
        poll = db.query(Poll).filter(Poll.id == poll_id).first()
        if not poll:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Poll not found"
            )
        
        # Check if expired
        if poll.expires_at and poll.expires_at <= datetime.utcnow():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Poll has expired"
            )
        
        # Check if already voted
        existing_vote = db.query(PollVote).filter(
            and_(
                PollVote.poll_id == poll_id,
                PollVote.user_id == current_user.id
            )
        ).first()
        
        if existing_vote:
            # Update vote
            old_option = existing_vote.option_id
            existing_vote.option_id = request.option_id
            existing_vote.voted_at = datetime.utcnow()
            
            # Update option counts
            old_opt = db.query(PollOption).filter(PollOption.id == old_option).first()
            if old_opt and old_opt.vote_count > 0:
                old_opt.vote_count -= 1
        else:
            # Create new vote
            new_vote = PollVote(
                poll_id=poll_id,
                user_id=current_user.id,
                option_id=request.option_id,
                voted_at=datetime.utcnow()
            )
            db.add(new_vote)
            poll.total_votes += 1
        
        # Update option vote count
        option = db.query(PollOption).filter(
            PollOption.id == request.option_id
        ).first()
        
        if not option:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Option not found"
            )
        
        option.vote_count += 1
        
        # Update percentages
        if poll.total_votes > 0:
            all_options = db.query(PollOption).filter(
                PollOption.poll_id == poll_id
            ).all()
            
            for opt in all_options:
                opt.percentage = (opt.vote_count / poll.total_votes) * 100
        
        # Award points
        leaderboard = db.query(Leaderboard).filter(
            Leaderboard.user_id == current_user.id
        ).first()
        
        if leaderboard:
            leaderboard.total_points += 2  # 2 points for voting
            leaderboard.last_activity = datetime.utcnow()
        
        db.commit()
        
        logger.info(f"User {current_user.id} voted on poll {poll_id}")
        
        return {
            "message": "Vote recorded successfully",
            "poll_id": poll_id,
            "option_id": request.option_id,
            "total_votes": poll.total_votes
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Vote poll error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record vote"
        )


# ============================================================================
# QUIZZES - GET ALL QUIZZES
# ============================================================================

@router.get(
    "/quizzes",
    response_model=dict,
    responses={400: {"model": ErrorResponse}}
)
async def get_quizzes(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    difficulty: Optional[str] = None,
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all quizzes
    
    Args:
        page: Page number
        limit: Results per page
        difficulty: Filter by difficulty
        current_user: Optional authenticated user
        db: Database session
    
    Returns:
        dict: Paginated quizzes list
    """
    try:
        query = db.query(Quiz).filter(Quiz.is_published == True)
        
        if difficulty:
            query = query.filter(Quiz.difficulty == difficulty)
        
        query = query.order_by(Quiz.created_at.desc())
        
        total = query.count()
        quizzes = query.offset((page - 1) * limit).limit(limit).all()
        
        quizzes_data = []
        for quiz in quizzes:
            quiz_resp = QuizResponse.model_validate(quiz)
            
            # Check user attempt
            if current_user:
                attempt = db.query(UserQuizAttempt).filter(
                    and_(
                        UserQuizAttempt.user_id == current_user.id,
                        UserQuizAttempt.quiz_id == quiz.id
                    )
                ).order_by(UserQuizAttempt.completed_at.desc()).first()
                
                if attempt:
                    quiz_resp.user_attempt = {
                        "score": attempt.score,
                        "percentage": attempt.percentage,
                        "passed": attempt.passed,
                        "completed_at": attempt.completed_at
                    }
            
            quizzes_data.append(quiz_resp)
        
        return {
            "total": total,
            "page": page,
            "limit": limit,
            "data": quizzes_data
        }
    
    except Exception as e:
        logger.error(f"Get quizzes error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch quizzes"
        )


# ============================================================================
# QUIZZES - GET QUIZ DETAIL
# ============================================================================

@router.get(
    "/quizzes/{quiz_id}",
    response_model=QuizDetailResponse,
    responses={404: {"model": ErrorResponse}}
)
async def get_quiz_detail(
    quiz_id: int,
    db: Session = Depends(get_db)
):
    """
    Get quiz with questions
    
    Args:
        quiz_id: Quiz ID
        db: Database session
    
    Returns:
        QuizDetailResponse: Quiz with questions
    """
    try:
        quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
        
        if not quiz:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Quiz not found"
            )
        
        detail = QuizDetailResponse.model_validate(quiz)
        
        # Get questions
        questions = db.query(QuizQuestion).filter(
            QuizQuestion.quiz_id == quiz_id
        ).order_by(QuizQuestion.question_order).all()
        
        detail.questions = [
            {
                "id": q.id,
                "text": q.question_text,
                "type": q.question_type,
                "options": q.options_json if q.question_type == "multiple_choice" else None,
                "points_value": q.points_value
            }
            for q in questions
        ]
        
        return detail
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get quiz error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch quiz"
        )


# ============================================================================
# QUIZZES - SUBMIT QUIZ
# ============================================================================

@router.post(
    "/quizzes/{quiz_id}/submit",
    response_model=QuizSubmitResponse,
    responses={
        401: {"model": ErrorResponse}, 
        404: {"model": ErrorResponse}
    }
)
async def submit_quiz(
    quiz_id: int,
    request: QuizSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Submit quiz answers
    
    Args:
        quiz_id: Quiz ID
        request: User answers
        current_user: Authenticated user
        db: Database session
    
    Returns:
        QuizSubmitResponse: Quiz results
    """
    try:
        # Get quiz
        quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
        if not quiz:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Quiz not found"
            )
        
        # Create attempt
        attempt = UserQuizAttempt(
            user_id=current_user.id,
            quiz_id=quiz_id,
            completed_at=datetime.utcnow()
        )
        db.add(attempt)
        db.flush() # Flush to get attempt.id generated safely
        
        total_points = 0
        correct_count = 0
        
        # Grade answers
        for answer_req in request.answers:
            question = db.query(QuizQuestion).filter(
                QuizQuestion.id == answer_req.question_id
            ).first()
            
            if not question:
                continue
            
            is_correct = answer_req.answer.lower() == question.correct_answer.lower()
            points = question.points_value if is_correct else 0
            
            if is_correct:
                correct_count += 1
                total_points += points
            
            # Record answer
            quiz_answer = QuizAnswer(
                attempt_id=attempt.id,
                question_id=answer_req.question_id,
                user_answer=answer_req.answer,
                is_correct=is_correct,
                points_earned=points
            )
            db.add(quiz_answer)
        
        # Calculate score
        attempt.score = total_points
        attempt.percentage = (correct_count / len(request.answers) * 100) if request.answers else 0
        attempt.passed = attempt.percentage >= quiz.passing_score
        
        # Award points if passed
        if attempt.passed:
            leaderboard = db.query(Leaderboard).filter(
                Leaderboard.user_id == current_user.id
            ).first()
            
            if leaderboard:
                leaderboard.total_points += quiz.points_reward
                leaderboard.last_activity = datetime.utcnow()
        
        db.commit()
        
        logger.info(f"User {current_user.id} submitted quiz {quiz_id}")
        
        return QuizSubmitResponse(
            message="Quiz submitted successfully",
            score=total_points,
            percentage=attempt.percentage,
            passed=attempt.passed,
            points_earned=quiz.points_reward if attempt.passed else 0,
            correct_answers=correct_count,
            incorrect_answers=len(request.answers) - correct_count
        )
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Submit quiz error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit quiz"
        )


# ============================================================================
# ACTIVITIES - GET ALL ACTIVITIES
# ============================================================================

@router.get(
    "/activities",
    response_model=dict,
    responses={400: {"model": ErrorResponse}}
)
async def get_activities(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    priority: Optional[str] = None,
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all activities
    
    Args:
        page: Page number
        limit: Results per page
        priority: Filter by priority
        current_user: Optional authenticated user
        db: Database session
    
    Returns:
        dict: Paginated activities list
    """
    try:
        query = db.query(Activity)
        
        if priority:
            query = query.filter(Activity.priority == priority)
        
        query = query.order_by(Activity.deadline.asc())
        
        total = query.count()
        activities = query.offset((page - 1) * limit).limit(limit).all()
        
        activities_data = []
        for activity in activities:
            activity_resp = ActivityResponse.model_validate(activity)
            
            # Check if user completed
            if current_user:
                completion = db.query(UserActivityCompletion).filter(
                    and_(
                        UserActivityCompletion.user_id == current_user.id,
                        UserActivityCompletion.activity_id == activity.id
                    )
                ).first()
                
                activity_resp.is_completed_by_user = completion is not None
                if completion:
                    activity_resp.completed_at = completion.completed_at
            
            activities_data.append(activity_resp)
        
        return {
            "total": total,
            "page": page,
            "limit": limit,
            "data": activities_data
        }
    
    except Exception as e:
        logger.error(f"Get activities error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch activities"
        )


# ============================================================================
# ACTIVITIES - COMPLETE ACTIVITY
# ============================================================================

@router.post(
    "/activities/{activity_id}/complete",
    response_model=dict,
    responses={
        401: {"model": ErrorResponse}, 
        404: {"model": ErrorResponse}, 
        409: {"model": ErrorResponse}
    }
)
async def complete_activity(
    activity_id: int,
    request: ActivityCompleteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Mark activity as completed
    
    Args:
        activity_id: Activity ID
        request: Completion notes
        current_user: Authenticated user
        db: Database session
    
    Returns:
        dict: Success message
    """
    try:
        # Get activity
        activity = db.query(Activity).filter(Activity.id == activity_id).first()
        if not activity:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Activity not found"
            )
        
        # Check if already completed
        existing = db.query(UserActivityCompletion).filter(
            and_(
                UserActivityCompletion.user_id == current_user.id,
                UserActivityCompletion.activity_id == activity_id
            )
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Activity already completed"
            )
        
        # Create completion
        completion = UserActivityCompletion(
            user_id=current_user.id,
            activity_id=activity_id,
            completion_notes=request.completion_notes,
            completed_at=datetime.utcnow()
        )
        
        # Award points
        leaderboard = db.query(Leaderboard).filter(
            Leaderboard.user_id == current_user.id
        ).first()
        
        if leaderboard:
            leaderboard.total_points += activity.points_reward
            leaderboard.last_activity = datetime.utcnow()
        
        db.add(completion)
        db.commit()
        
        logger.info(f"User {current_user.id} completed activity {activity_id}")
        
        return {
            "message": "Activity completed successfully",
            "points_earned": activity.points_reward
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Complete activity error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to complete activity"
        )


# ============================================================================
# ENGAGEMENT SUMMARY
# ============================================================================

@router.get(
    "/summary",
    response_model=dict,
    responses={401: {"model": ErrorResponse}}
)
async def get_engagement_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get engagement center summary for user
    
    Args:
        current_user: Authenticated user
        db: Database session
    
    Returns:
        dict: Engagement summary
    """
    try:
        # Count active challenges
        active_challenges = db.query(Challenge).filter(
            and_(
                Challenge.start_date <= datetime.utcnow(),
                Challenge.end_date >= datetime.utcnow(),
                Challenge.is_active == True
            )
        ).count()
        
        # Count user challenges
        user_challenges_joined = db.query(UserChallenge).filter(
            UserChallenge.user_id == current_user.id
        ).count()
        
        user_challenges_completed = db.query(UserChallenge).filter(
            and_(
                UserChallenge.user_id == current_user.id,
                UserChallenge.is_completed == True
            )
        ).count()
        
        # Count polls
        active_polls = db.query(Poll).filter(
            Poll.is_active == True
        ).count()
        
        user_polls = db.query(PollVote).filter(
            PollVote.user_id == current_user.id
        ).count()
        
        # Count quizzes
        available_quizzes = db.query(Quiz).filter(
            Quiz.is_published == True
        ).count()
        
        user_quiz_attempts = db.query(UserQuizAttempt).filter(
            UserQuizAttempt.user_id == current_user.id
        ).count()
        
        # Count activities
        pending_activities = db.query(Activity).filter(
            or_(
                Activity.deadline == None,
                Activity.deadline > datetime.utcnow()
            )
        ).count()
        
        completed_activities = db.query(UserActivityCompletion).filter(
            UserActivityCompletion.user_id == current_user.id
        ).count()
        
        # Get user leaderboard stats
        leaderboard = db.query(Leaderboard).filter(
            Leaderboard.user_id == current_user.id
        ).first()
        
        return {
            "message": "success",
            "data": {
                "active_challenges": active_challenges,
                "challenges_joined": user_challenges_joined,
                "challenges_completed": user_challenges_completed,
                "active_polls": active_polls,
                "polls_participated": user_polls,
                "available_quizzes": available_quizzes,
                "quizzes_completed": user_quiz_attempts,
                "pending_activities": pending_activities,
                "activities_completed": completed_activities,
                "total_points_this_week": leaderboard.total_points if leaderboard else 0,
                "current_rank": db.query(Leaderboard).filter(
                    Leaderboard.total_points > (leaderboard.total_points if leaderboard else 0)
                ).count() + 1 if leaderboard else None,
                "current_tier": leaderboard.tier if leaderboard else "bronze",
                "badges_earned_this_month": db.query(Badge).join(
                    Badge.users
                ).filter(Badge.users.contains(current_user)).count()
            }
        }
    
    except Exception as e:
        logger.error(f"Get engagement summary error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch engagement summary"
        )