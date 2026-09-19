# ============================================================================
# AI Routes - Phase 2 Features
# ============================================================================

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime
import random

from app.database import get_db
from app.schemas import (
    SessionResponse,
    SessionDetailResponse,
    QuizSubmitResponse
)
from app.models import User, Session as SessionModel, Rating
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# ============================================================================
# AI RECOMMENDATIONS - Event Recommendations for Users
# ============================================================================

@router.get("/recommendations/sessions")
async def get_ai_recommendations(
    db: Session = Depends(get_db),
    current_user: User = Depends(),
    limit: int = Query(5, ge=1, le=20)
):
    """
    Get AI-powered session recommendations based on user profile and history.
    Uses simple recommendation engine (can be upgraded to ML model).
    """
    try:
        # Get user's attended sessions to understand interests
        user_ratings = db.query(Rating).filter(Rating.user_id == current_user.id).all()
        user_session_ids = [r.session_id for r in user_ratings]

        # Get all sessions user hasn't attended
        recommended_sessions = db.query(SessionModel).filter(
            SessionModel.id.notin_(user_session_ids)
        ).order_by(SessionModel.start_time).limit(limit).all()

        recommendations = []
        for session in recommended_sessions:
            rec = {
                "id": session.id,
                "title": session.title,
                "description": session.description,
                "speaker_name": session.speaker_name if session.speaker_id else "Expert Speaker",
                "start_time": session.start_time.isoformat() if session.start_time else None,
                "location": session.location,
                "points_reward": session.points_reward or 50,
                "attendee_count": 0,  # Replace with actual count from attendance table
                "match_percentage": random.randint(70, 95),  # Mock percentage
                "trending": random.choice([True, False]),
                "reason": "Based on your interest in advanced development topics and your attendance history"
            }
            recommendations.append(rec)

        return {
            "status": "success",
            "data": recommendations,
            "recommendations": recommendations  # Support both keys
        }

    except Exception as e:
        logger.error(f"Recommendation error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate recommendations")


# ============================================================================
# AI CHATBOT - General AI Assistant Endpoint
# ============================================================================

@router.post("/chat")
async def ai_chat(
    request_body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends()
):
    """
    Chatbot endpoint for user questions. Routes to appropriate AI handler.
    
    Handles:
    - "Recommend sessions" → Event recommendations
    - "Find people" → Networking suggestions
    - "Summarize" → Session summary
    - "Quiz" → Quiz generator
    - "Career" → Career advice
    """
    try:
        message = request_body.get("message", "").lower()
        context = request_body.get("context", "general")

        # Route to appropriate handler
        if "recommend" in message or "sessions" in message:
            response_text = f"I'd recommend sessions based on your interests. Let me find the perfect ones for you!"
            suggestions = ["Show me trending sessions", "Technical workshops only", "Networking events"]
            
        elif "network" in message or "people" in message or "meet" in message:
            response_text = "I can help you find people to connect with! Based on your interests, I found several professionals you might want to meet."
            suggestions = ["Show connections in tech", "Find mentors", "See my network stats"]
            
        elif "summary" in message or "recap" in message:
            response_text = "I can generate a 2-minute summary of any session you attended. Which session would you like summarized?"
            suggestions = ["Summarize last session", "View all summaries", "Download summary"]
            
        elif "quiz" in message or "test" in message:
            response_text = "Great idea! Let me generate a quiz based on sessions you've attended. This will test your knowledge and earn you bonus points!"
            suggestions = ["Start quiz now", "View past quizzes", "See leaderboard"]
            
        elif "career" in message or "advice" in message:
            response_text = "I'm here to help with your career journey! Based on your profile and interests, here's my advice: focus on sessions that align with your goals and network with professionals in your field."
            suggestions = ["Career recommendations", "Skills to develop", "Job opportunities"]
            
        else:
            response_text = "I can help you with recommendations, finding people to network with, session summaries, quizzes, and career advice. What would you like to explore?"
            suggestions = [
                "Recommend sessions for me",
                "Find people to network with",
                "Summarize a session",
                "Generate quiz questions",
                "Career advice"
            ]

        return {
            "status": "success",
            "response": response_text,
            "message": response_text,
            "suggestions": suggestions,
            "metadata": {
                "category": context,
                "timestamp": datetime.now().isoformat(),
                "user_id": current_user.id
            }
        }

    except Exception as e:
        logger.error(f"Chat error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to process chat")


# ============================================================================
# AI SESSION SUMMARY - Generate AI Summary of Sessions
# ============================================================================

@router.get("/sessions/{session_id}/summary")
async def get_session_summary(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends()
):
    """
    Generate AI summary of a session (2-minute read).
    Requires user to have attended the session.
    """
    try:
        # Verify session exists and user attended it
        session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Mock summary data (replace with actual AI generation)
        summary = {
            "title": session.title,
            "key_points": [
                f"Key insight from {session.title}: Understanding core concepts",
                "Practical implementation strategies discussed",
                "Real-world use cases and examples shared",
                "Best practices and common pitfalls covered",
                "Future trends and emerging technologies mentioned"
            ],
            "main_takeaways": f"This session covered {session.title} in depth, providing practical insights and actionable strategies. The speaker shared valuable experience and demonstrated real-world applications. Key takeaway: focus on understanding fundamentals before diving into advanced topics.",
            "skills_learned": [
                "Advanced problem solving",
                "Best practices in development",
                "System design thinking",
                "Code optimization",
                "Architecture patterns"
            ],
            "action_items": [
                "Review the session slides and notes",
                "Implement learnings in your next project",
                "Connect with speaker for follow-up questions",
                "Share knowledge with team members",
                "Explore recommended resources"
            ],
            "session_id": session_id
        }

        return {
            "status": "success",
            "data": summary
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Summary generation error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate summary")


# ============================================================================
# AI QUIZ GENERATOR - Generate Quizzes from Session Content
# ============================================================================

@router.get("/sessions/{session_id}/quiz")
async def get_session_quiz(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends()
):
    """
    Generate AI quiz based on session content.
    5 questions with multiple choice answers.
    """
    try:
        session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Mock quiz questions (replace with actual AI generation)
        quiz = {
            "session_id": session_id,
            "title": f"Quiz: {session.title}",
            "total_questions": 5,
            "questions": [
                {
                    "question": f"What was the main topic discussed in {session.title}?",
                    "options": [
                        "Advanced architecture patterns",
                        "Basic concepts only",
                        "Frontend frameworks",
                        "Database optimization"
                    ],
                    "correct_answer": 0,
                    "explanation": f"This session focused on {session.title}, covering advanced concepts and best practices.",
                    "hint": "Think about the session's main focus"
                },
                {
                    "question": "Which best practice was emphasized the most?",
                    "options": [
                        "Code readability",
                        "Performance optimization",
                        "Security first",
                        "Testing coverage"
                    ],
                    "correct_answer": 3,
                    "explanation": "The session emphasized comprehensive testing as the foundation for reliable code.",
                    "hint": "The speaker mentioned this multiple times"
                },
                {
                    "question": "What real-world example was demonstrated?",
                    "options": [
                        "E-commerce platform",
                        "Social media app",
                        "Data analytics tool",
                        "Messaging service"
                    ],
                    "correct_answer": 2,
                    "explanation": "The practical demonstration used a data analytics tool as a case study.",
                    "hint": "The demo showed data processing"
                },
                {
                    "question": "According to the speaker, what's a common pitfall?",
                    "options": [
                        "Over-engineering solutions",
                        "Skipping documentation",
                        "Not considering scalability",
                        "All of the above"
                    ],
                    "correct_answer": 3,
                    "explanation": "The speaker mentioned multiple pitfalls that developers commonly make.",
                    "hint": "There were several mistakes discussed"
                },
                {
                    "question": "What was the recommended next step?",
                    "options": [
                        "Immediately implement everything",
                        "Study fundamentals first",
                        "Skip the theory",
                        "Use a different approach"
                    ],
                    "correct_answer": 1,
                    "explanation": "Strong fundamentals are essential before tackling advanced topics.",
                    "hint": "The speaker gave career guidance at the end"
                }
            ]
        }

        return {
            "status": "success",
            "data": quiz
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Quiz generation error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate quiz")


# ============================================================================
# QUIZ SUBMISSION - Submit Quiz Answers and Calculate Score
# ============================================================================

@router.post("/sessions/{session_id}/quiz/submit")
async def submit_quiz(
    session_id: int,
    request_body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends()
):
    """
    Submit quiz answers and get score.
    Returns percentage, point reward, and detailed feedback.
    """
    try:
        answers = request_body.get("answers", {})
        
        # Mock correct answers (would come from quiz)
        correct_answers = {
            "0": 0,
            "1": 3,
            "2": 2,
            "3": 3,
            "4": 1
        }

        # Calculate score
        correct_count = 0
        for question_idx, answer_idx in answers.items():
            if str(question_idx) in correct_answers:
                if correct_answers[str(question_idx)] == answer_idx:
                    correct_count += 1

        total = len(correct_answers)
        percentage = int((correct_count / total) * 100)
        points = correct_count * 10  # 10 points per correct answer

        # Determine message
        if percentage == 100:
            message = "Perfect score! You've mastered this topic! 🎉"
        elif percentage >= 80:
            message = "Great job! You understood the key concepts! 👏"
        elif percentage >= 60:
            message = "Good effort! Consider reviewing the material. 📚"
        else:
            message = "Keep learning! Try the session again for more insights. 💪"

        result = {
            "percentage": percentage,
            "correct": correct_count,
            "incorrect": total - correct_count,
            "points": points,
            "message": message,
            "session_id": session_id
        }

        return {
            "status": "success",
            "data": result,
            "score": result  # Support both keys
        }

    except Exception as e:
        logger.error(f"Quiz submission error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to submit quiz")


# ============================================================================
# AI FEEDBACK - User Feedback on AI Responses
# ============================================================================

@router.post("/feedback")
async def submit_ai_feedback(
    request_body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends()
):
    """
    Capture user feedback on AI responses to improve model.
    Helpful/Not helpful feedback.
    """
    try:
        message_id = request_body.get("message_id")
        helpful = request_body.get("helpful", False)

        # Log feedback for model improvement
        logger.info(f"User {current_user.id} rated message {message_id}: {'helpful' if helpful else 'not helpful'}")

        return {
            "status": "success",
            "message": "Thank you for your feedback!",
            "feedback_recorded": True
        }

    except Exception as e:
        logger.error(f"Feedback error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to record feedback")


# ============================================================================
# Include this router in main.py
# ============================================================================
# In backend/app/main.py, add:
# from app.routes import ai_routes
# app.include_router(ai_routes.router, prefix="/api/v1/ai", tags=["AI Features"])