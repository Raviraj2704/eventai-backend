# ============================================================================
# Challenge Routes
# ============================================================================
# File: app/routes/challenges.py
# Purpose: Challenge management and participation
# Status: Production-Ready ✅

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import datetime
from typing import Optional
import logging

from app.database import get_db
from app.models import (
    Challenge, UserChallenge, User, Badge, UserBadge, Leaderboard    
)
from app.schemas import (
    ChallengeResponse, ChallengeDetailResponse, ChallengeJoinRequest,
    ChallengeCompleteRequest, ChallengeListRequest, ErrorResponse
)
from app.routes.users import get_current_user
from app.utils.email import send_badge_earned_email


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/challenges", tags=["Challenges"])


# ============================================================================
# GET ALL CHALLENGES
# ============================================================================

@router.get(
    "",
    response_model=dict,
    responses={400: {"model": ErrorResponse}}
)
async def get_challenges(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    difficulty: Optional[str] = None,
    status_filter: Optional[str] = None,
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all challenges with filtering
    
    Args:
        page: Page number
        limit: Results per page
        difficulty: Filter by difficulty
        status_filter: Filter by status (active/past/upcoming)
        current_user: Optional authenticated user
        db: Database session
    
    Returns:
        dict: Paginated challenges list
    """
    try:
        query = db.query(Challenge)
        
        if difficulty:
            query = query.filter(Challenge.difficulty == difficulty)
        
        if status_filter == "active":
            query = query.filter(
                and_(
                    Challenge.start_date <= datetime.utcnow(),
                    Challenge.end_date >= datetime.utcnow(),
                    Challenge.is_active == True
                )
            )
        elif status_filter == "upcoming":
            query = query.filter(Challenge.start_date > datetime.utcnow())
        elif status_filter == "past":
            query = query.filter(Challenge.end_date < datetime.utcnow())
        
        query = query.order_by(Challenge.start_date.desc())
        
        total = query.count()
        challenges = query.offset((page - 1) * limit).limit(limit).all()
        
        challenges_data = []
        for challenge in challenges:
            challenge_resp = ChallengeResponse.model_validate(challenge)
            
            # Check user participation
            if current_user:
                participation = db.query(UserChallenge).filter(
                    and_(
                        UserChallenge.user_id == current_user.id,
                        UserChallenge.challenge_id == challenge.id
                    )
                ).first()
                
                if participation:
                    challenge_resp.user_participation = {
                        "joined": True,
                        "score": participation.score,
                        "completed": participation.is_completed
                    }
            
            challenges_data.append(challenge_resp)
        
        return {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit,
            "has_next": page * limit < total,
            "has_prev": page > 1,
            "data": challenges_data
        }
    
    except Exception as e:
        logger.error(f"Get challenges error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch challenges"
        )


# ============================================================================
# GET CHALLENGE BY ID
# ============================================================================

@router.get(
    "/{challenge_id}",
    response_model=ChallengeDetailResponse,
    responses={404: {"model": ErrorResponse}}
)
async def get_challenge_by_id(
    challenge_id: int,
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get challenge by ID with full details
    
    Args:
        challenge_id: Challenge ID
        current_user: Optional authenticated user
        db: Database session
    
    Returns:
        ChallengeDetailResponse: Challenge details
    """
    try:
        challenge = db.query(Challenge).filter(Challenge.id == challenge_id).first()
        
        if not challenge:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Challenge not found"
            )
        
        detail = ChallengeDetailResponse.model_validate(challenge)
        
        # Get badge reward info
        if challenge.badge_reward_id:
            badge = db.query(Badge).filter(Badge.id == challenge.badge_reward_id).first()
            if badge:
                detail.badge_reward = {
                    "id": badge.id,
                    "name": badge.name,
                    "icon_url": badge.icon_url,
                    "rarity": badge.rarity
                }
        
        # Check user participation
        if current_user:
            participation = db.query(UserChallenge).filter(
                and_(
                    UserChallenge.user_id == current_user.id,
                    UserChallenge.challenge_id == challenge_id
                )
            ).first()
            
            if participation:
                detail.user_participation = {
                    "joined": True,
                    "score": participation.score,
                    "completed": participation.is_completed
                }
        
        return detail
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get challenge error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch challenge"
        )


# ============================================================================
# JOIN CHALLENGE
# ============================================================================

@router.post(
    "/{challenge_id}/join",
    response_model=dict,
    responses={
        401: {"model": ErrorResponse}, 
        404: {"model": ErrorResponse}, 
        409: {"model": ErrorResponse}
    }
)
async def join_challenge(
    challenge_id: int,
    request: ChallengeJoinRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Join a challenge
    
    Args:
        challenge_id: Challenge ID
        request: Join request
        current_user: Authenticated user
        db: Database session
    
    Returns:
        dict: Success message
    """
    try:
        # Get challenge
        challenge = db.query(Challenge).filter(Challenge.id == challenge_id).first()
        if not challenge:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Challenge not found"
            )
        
        # Check if already joined
        existing = db.query(UserChallenge).filter(
            and_(
                UserChallenge.user_id == current_user.id,
                UserChallenge.challenge_id == challenge_id
            )
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Already joined this challenge"
            )
        
        # Create participation
        participation = UserChallenge(
            user_id=current_user.id,
            challenge_id=challenge_id,
            joined_at=datetime.utcnow()
        )
        
        # Update challenge participants count
        challenge.participants_count += 1
        
        db.add(participation)
        db.commit()
        
        logger.info(f"User {current_user.id} joined challenge {challenge_id}")
        
        return {
            "message": "Successfully joined challenge",
            "challenge_id": challenge_id
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Join challenge error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to join challenge"
        )


# ============================================================================
# COMPLETE CHALLENGE
# ============================================================================

@router.post(
    "/{challenge_id}/complete",
    response_model=dict,
    responses={
        401: {"model": ErrorResponse}, 
        404: {"model": ErrorResponse}, 
        409: {"model": ErrorResponse}
    }
)
async def complete_challenge(
    challenge_id: int,
    request: ChallengeCompleteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Mark challenge as completed
    
    Args:
        challenge_id: Challenge ID
        request: Completion request
        current_user: Authenticated user
        db: Database session
    
    Returns:
        dict: Success message with rewards
    """
    try:
        # Get challenge
        challenge = db.query(Challenge).filter(Challenge.id == challenge_id).first()
        if not challenge:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Challenge not found"
            )
        
        # Get participation
        participation = db.query(UserChallenge).filter(
            and_(
                UserChallenge.user_id == current_user.id,
                UserChallenge.challenge_id == challenge_id
            )
        ).first()
        
        if not participation:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Not joined this challenge"
            )
        
        if participation.is_completed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Already completed this challenge"
            )
        
        # Mark as completed
        participation.is_completed = True
        participation.completed_at = datetime.utcnow()
        participation.score = request.score or 0
        
        # Award points to leaderboard
        leaderboard = db.query(Leaderboard).filter(
            Leaderboard.user_id == current_user.id
        ).first()
        
        points_earned = challenge.points_reward
        
        if leaderboard:
            leaderboard.total_points += points_earned
            leaderboard.challenges_completed += 1
            leaderboard.last_activity = datetime.utcnow()
        
        # Award badge if applicable
        badge_awarded = None
        if challenge.badge_reward_id:
            badge = db.query(Badge).filter(Badge.id == challenge.badge_reward_id).first()
            
            # Check if user already has badge
            existing_badge = db.query(UserBadge).filter(
                and_(
                    UserBadge.user_id == current_user.id,
                    UserBadge.badge_id == challenge.badge_reward_id
                )
            ).first()
            
            if not existing_badge:
                user_badge = UserBadge(
                    user_id=current_user.id,
                    badge_id=challenge.badge_reward_id,
                    earned_at=datetime.utcnow()
                )
                db.add(user_badge)
                
                if leaderboard:
                    leaderboard.total_points += badge.points_reward
                    leaderboard.badges_earned += 1
                
                badge_awarded = {
                    "id": badge.id,
                    "name": badge.name,
                    "icon_url": badge.icon_url,
                    "points": badge.points_reward
                }
                
                # Send badge earned email
                send_badge_earned_email(
                    current_user.email,
                    current_user.username,
                    badge.name
                )
        
        db.commit()
        
        logger.info(f"User {current_user.id} completed challenge {challenge_id}")
        
        return {
            "message": "Challenge completed successfully",
            "points_earned": points_earned,
            "badge_awarded": badge_awarded
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Complete challenge error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to complete challenge"
        )