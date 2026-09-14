# ============================================================================
# COMPLETE EventAI Backend Schemas
# ============================================================================
# File: backend/app/schemas.py
# Includes: All 22 features with exact imports your routes need
# Status: PRODUCTION READY ✅

from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime

# ============================================================================
# 1. AUTH & USER SCHEMAS
# ============================================================================

class RegisterSchema(BaseModel):
    first_name: str = Field(..., min_length=1)
    last_name: str = Field(..., min_length=1)
    email: EmailStr
    password: str = Field(..., min_length=8)
    class Config:
        from_attributes = True

class LoginSchema(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"

class UserResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str
    company: Optional[str] = None
    designation: Optional[str] = None
    location: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: bool = True
    created_at: datetime
    class Config:
        from_attributes = True

class UserProfileResponse(BaseModel):
    id: int
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company: Optional[str] = None
    designation: Optional[str] = None
    location: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    class Config:
        from_attributes = True

class UserUpdateRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    designation: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    bio: Optional[str] = None

class UserUpdateResponse(BaseModel):
    message: str
    user: Optional[UserResponse] = None

class AvatarUploadResponse(BaseModel):
    avatar_url: str
    message: str = "Avatar uploaded successfully"

# ============================================================================
# 2. SESSIONS SCHEMAS
# ============================================================================

class SessionCreate(BaseModel):
    title: str
    description: Optional[str] = None
    speaker_id: int
    start_time: datetime
    end_time: datetime
    location: Optional[str] = None
    capacity: int = 100

class SessionUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    location: Optional[str] = None
    capacity: Optional[int] = None

class SessionResponse(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    speaker_id: int
    start_time: datetime
    end_time: datetime
    location: Optional[str] = None
    capacity: int
    created_at: datetime
    class Config:
        from_attributes = True

class SessionDetailResponse(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    speaker_id: int
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    location: Optional[str] = None
    capacity: Optional[int] = None
    attendee_count: int = 0
    class Config:
        from_attributes = True

class SessionListRequest(BaseModel):
    page: int = 1
    limit: int = 10
    speaker_id: Optional[int] = None

class SessionAttendanceRequest(BaseModel):
    status: str = "registered"

class SessionAttendanceResponse(BaseModel):
    message: str
    status: str

class SessionCheckInRequest(BaseModel):
    session_id: int

class SessionCheckInResponse(BaseModel):
    message: str
    checked_in_at: datetime

class SessionRatingRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    feedback: Optional[str] = None

# ============================================================================
# 3. SPEAKERS SCHEMAS
# ============================================================================

class SpeakerCreate(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    bio: Optional[str] = None
    designation: Optional[str] = None
    company: Optional[str] = None
    expertise: Optional[str] = None

class SpeakerUpdate(BaseModel):
    bio: Optional[str] = None
    designation: Optional[str] = None
    company: Optional[str] = None
    expertise: Optional[str] = None

class SpeakerResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    designation: Optional[str] = None
    company: Optional[str] = None
    expertise: Optional[str] = None
    session_count: int = 0
    class Config:
        from_attributes = True

class SpeakerDetailResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str
    bio: Optional[str] = None
    designation: Optional[str] = None
    company: Optional[str] = None
    expertise: Optional[str] = None
    sessions: List = []
    average_rating: float = 0.0
    class Config:
        from_attributes = True

class SpeakerRatingRequest(BaseModel):
    score: int = Field(..., ge=1, le=5)
    comment: Optional[str] = Field(None, max_length=1000)

class SpeakerRatingResponse(BaseModel):
    id: int
    speaker_id: int
    score: int
    comment: Optional[str] = None
    created_at: datetime

# ============================================================================
# 4. ANNOUNCEMENTS SCHEMAS
# ============================================================================

class AnnouncementCreate(BaseModel):
    title: str = Field(..., max_length=255)
    content: str = Field(..., max_length=2000)
    category: Optional[str] = "General"
    priority: str = "low"

class AnnouncementCreateRequest(BaseModel):
    title: str
    content: str
    category: Optional[str] = None
    priority: str = "low"

class AnnouncementListRequest(BaseModel):
    page: int = 1
    limit: int = 10
    category: Optional[str] = None

class AnnouncementResponse(BaseModel):
    id: int
    title: str
    content: str
    creator_id: int
    category: Optional[str] = None
    priority: str
    created_at: datetime
    class Config:
        from_attributes = True

class AnnouncementDetailResponse(BaseModel):
    id: int
    title: str
    content: str
    creator_id: int
    category: Optional[str] = None
    priority: str
    views: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None
    class Config:
        from_attributes = True

# ============================================================================
# 5. RATINGS SCHEMAS
# ============================================================================

class RatingCreate(BaseModel):
    score: int = Field(..., ge=1, le=5)
    comment: Optional[str] = Field(None, max_length=1000)
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None

class RatingResponse(BaseModel):
    id: int
    user_id: int
    score: int
    comment: Optional[str] = None
    created_at: datetime
    class Config:
        from_attributes = True

class RatingDistribution(BaseModel):
    five_star: int = 0
    four_star: int = 0
    three_star: int = 0
    two_star: int = 0
    one_star: int = 0
    average: float = 0.0
    total: int = 0

class RatingDashboardResponse(BaseModel):
    entity_id: int
    entity_type: str
    total_ratings: int = 0
    average_rating: float = 0.0
    distribution: RatingDistribution
    recent_ratings: List[RatingResponse] = []

# ============================================================================
# 6. RESOURCES SCHEMAS
# ============================================================================

class ResourceCreate(BaseModel):
    session_id: Optional[int] = None
    title: str
    description: Optional[str] = None
    resource_type: Optional[str] = None
    file_url: str

class ResourceUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    resource_type: Optional[str] = None
    file_url: Optional[str] = None

class ResourceResponse(BaseModel):
    id: int
    session_id: Optional[int] = None
    title: str
    description: Optional[str] = None
    resource_type: Optional[str] = None
    file_url: str
    download_count: int = 0
    created_at: datetime
    class Config:
        from_attributes = True

class ResourceDetailResponse(BaseModel):
    id: int
    session_id: Optional[int] = None
    title: str
    description: Optional[str] = None
    resource_type: Optional[str] = None
    file_url: str
    download_count: int = 0
    average_rating: float = 0.0
    created_at: datetime
    class Config:
        from_attributes = True

class ResourceListRequest(BaseModel):
    page: int = 1
    limit: int = 10
    resource_type: Optional[str] = None

class ResourceRatingRequest(BaseModel):
    score: int = Field(..., ge=1, le=5)
    comment: Optional[str] = Field(None, max_length=1000)

# ============================================================================
# 7. SOCIAL SCHEMAS
# ============================================================================

class SocialPostCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)
    image_url: Optional[str] = None

class SocialPostCreateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)
    image_url: Optional[str] = None

class SocialPostListRequest(BaseModel):
    page: int = 1
    limit: int = 10
    user_id: Optional[int] = None

class SocialPostResponse(BaseModel):
    id: int
    user_id: int
    content: str
    image_url: Optional[str] = None
    like_count: int = 0
    comment_count: int = 0
    is_approved: bool = True
    created_at: datetime
    class Config:
        from_attributes = True

class CommentCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=1000)

class SocialCommentCreateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=1000)

class SocialCommentResponse(BaseModel):
    id: int
    user_id: int
    post_id: int
    content: str
    like_count: int = 0
    is_approved: bool = True
    created_at: datetime
    class Config:
        from_attributes = True

class LikeCreate(BaseModel):
    post_id: int

# ============================================================================
# 8. BADGES SCHEMAS
# ============================================================================

class BadgeCreate(BaseModel):
    name: str
    description: Optional[str] = None
    icon_url: Optional[str] = None
    rarity: str = "common"
    points_reward: int = 0

class BadgeResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    icon_url: Optional[str] = None
    rarity: str = "common"
    points_reward: int = 0
    created_at: datetime
    class Config:
        from_attributes = True

class BadgeDetailResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    icon_url: Optional[str] = None
    rarity: str
    points_reward: int
    recipients_count: int = 0
    created_at: datetime
    class Config:
        from_attributes = True

class EarnedBadgeResponse(BaseModel):
    id: int
    badge_id: int
    user_id: int
    badge_name: str
    icon_url: Optional[str] = None
    earned_at: datetime
    rarity: str
    class Config:
        from_attributes = True

# ============================================================================
# 9. CHALLENGES SCHEMAS
# ============================================================================

class ChallengeCreate(BaseModel):
    title: str
    description: Optional[str] = None
    difficulty: str = "medium"
    points_reward: int = 20

class ChallengeResponse(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    difficulty: str = "medium"
    points_reward: int = 20
    completion_count: int = 0
    created_at: datetime
    class Config:
        from_attributes = True

class ChallengeDetailResponse(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    difficulty: str
    points_reward: int
    completion_count: int = 0
    your_status: Optional[str] = None
    created_at: datetime
    class Config:
        from_attributes = True

class ChallengeJoinRequest(BaseModel):
    challenge_id: int

class ChallengeCompleteRequest(BaseModel):
    challenge_id: int
    proof_url: Optional[str] = None

class ChallengeListRequest(BaseModel):
    page: int = 1
    limit: int = 10
    difficulty: Optional[str] = None

# ============================================================================
# 10. LEADERBOARD SCHEMAS
# ============================================================================

class LeaderboardResponse(BaseModel):
    id: int
    user_id: int
    total_points: int = 0
    current_rank: int = 0
    tier: str = "bronze"
    updated_at: datetime
    class Config:
        from_attributes = True

class LeaderboardListRequest(BaseModel):
    page: int = 1
    limit: int = 10
    tier: Optional[str] = None

class LeaderboardUserResponse(BaseModel):
    rank: int
    user_id: int
    first_name: str
    last_name: str
    total_points: int
    tier: str
    badges_earned: int = 0
    class Config:
        from_attributes = True

class UserLeaderboardStatsResponse(BaseModel):
    user_id: int
    rank: int
    total_points: int
    tier: str
    badges_earned: int = 0
    sessions_attended: int = 0
    challenges_completed: int = 0
    class Config:
        from_attributes = True

# ============================================================================
# 11. LEARNING PATHS SCHEMAS
# ============================================================================

class ModuleCreate(BaseModel):
    title: str
    description: Optional[str] = None
    order: int = 0
    duration: int = 30

class LearningModuleResponse(BaseModel):
    id: int
    learning_path_id: int
    title: str
    description: Optional[str] = None
    order: int = 0
    duration: int = 30
    created_at: datetime
    class Config:
        from_attributes = True

class LearningPathCreate(BaseModel):
    title: str
    description: Optional[str] = None
    difficulty: str = "Beginner"
    duration_weeks: int = 4
    points_reward: int = 50

class LearningPathResponse(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    difficulty: str = "Beginner"
    duration_weeks: int = 4
    points_reward: int = 50
    enrolled_count: int = 0
    created_at: datetime
    class Config:
        from_attributes = True

class LearningPathDetailResponse(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    difficulty: str
    duration_weeks: int
    points_reward: int
    enrolled_count: int
    modules: List[LearningModuleResponse] = []
    created_at: datetime
    class Config:
        from_attributes = True

class LearningPathListRequest(BaseModel):
    page: int = 1
    limit: int = 10
    difficulty: Optional[str] = None

class LearningPathEnrollRequest(BaseModel):
    learning_path_id: int

class LearningPathProgressRequest(BaseModel):
    learning_path_id: int
    module_id: int
    progress_percentage: int = Field(..., ge=0, le=100)

# ============================================================================
# 12. ENGAGEMENT SCHEMAS
# ============================================================================

class EngagementSummaryResponse(BaseModel):
    active_challenges: int = 0
    active_polls: int = 0
    available_quizzes: int = 0
    pending_activities: int = 0
    total_points_this_week: int = 0
    current_rank: int = 0
    current_tier: str = "bronze"
    class Config:
        from_attributes = True

class ActivityResponse(BaseModel):
    id: int
    user_id: int
    activity_type: str
    description: Optional[str] = None
    points_earned: int = 0
    created_at: datetime
    class Config:
        from_attributes = True

class ActivityDetailResponse(BaseModel):
    id: int
    user_id: int
    activity_type: str
    description: Optional[str] = None
    points_earned: int = 0
    status: str = "completed"
    created_at: datetime
    completed_at: Optional[datetime] = None
    class Config:
        from_attributes = True

class ActivityCompleteRequest(BaseModel):
    activity_id: int
    proof_url: Optional[str] = None

# ============================================================================
# 13. PARTNERSHIPS SCHEMAS
# ============================================================================

class PartnershipCreate(BaseModel):
    name: str
    description: Optional[str] = None
    logo_url: Optional[str] = None
    website_url: Optional[str] = None

class PartnershipResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    logo_url: Optional[str] = None
    website_url: Optional[str] = None
    created_at: datetime
    class Config:
        from_attributes = True

class PartnershipDetailResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    logo_url: Optional[str] = None
    website_url: Optional[str] = None
    events_sponsored: int = 0
    created_at: datetime
    class Config:
        from_attributes = True

class PartnershipListRequest(BaseModel):
    page: int = 1
    limit: int = 10

# ============================================================================
# 14. POLLS & QUIZZES SCHEMAS
# ============================================================================

class PollOptionCreate(BaseModel):
    option_text: str

class PollCreate(BaseModel):
    question: str
    description: Optional[str] = None
    options: List[PollOptionCreate]

class PollVoteRequest(BaseModel):
    poll_id: int
    option_id: int

class PollResponse(BaseModel):
    id: int
    question: str
    description: Optional[str] = None
    total_votes: int = 0
    options: List = []
    created_at: datetime
    class Config:
        from_attributes = True

class QuizQuestionCreate(BaseModel):
    question_text: str
    question_type: str = "multiple_choice"
    order: int = 0

class QuizCreate(BaseModel):
    title: str
    description: Optional[str] = None
    difficulty: str = "medium"
    passing_score: int = 70
    duration_minutes: int = 30
    questions: List[QuizQuestionCreate] = []

class QuizSubmitRequest(BaseModel):
    quiz_id: int
    answers: dict

class QuizSubmitResponse(BaseModel):
    message: str
    score: int
    passing: bool
    correct_answers: int
    total_questions: int
    class Config:
        from_attributes = True

class QuizResponse(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    difficulty: str
    passing_score: int
    duration_minutes: int
    total_questions: int = 0
    created_at: datetime
    class Config:
        from_attributes = True

class QuizDetailResponse(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    difficulty: str
    passing_score: int
    duration_minutes: int
    questions: List = []
    your_attempts: int = 0
    your_best_score: Optional[int] = None
    created_at: datetime
    class Config:
        from_attributes = True

# ============================================================================
# 15. ADMIN SCHEMAS
# ============================================================================

class AdminUserResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str
    company: Optional[str] = None
    is_active: bool
    created_at: datetime
    class Config:
        from_attributes = True

class AdminUserDetailResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str
    company: Optional[str] = None
    is_active: bool
    last_login: Optional[datetime] = None
    sessions_attended: int = 0
    total_points: int = 0
    created_at: datetime
    class Config:
        from_attributes = True

class AdminUserUpdateRequest(BaseModel):
    is_active: Optional[bool] = None
    designation: Optional[str] = None

class AdminListRequest(BaseModel):
    page: int = 1
    limit: int = 10
    is_active: Optional[bool] = None

class AdminContentResponse(BaseModel):
    id: int
    content_type: str
    title: str
    creator_id: int
    is_approved: bool
    created_at: datetime
    class Config:
        from_attributes = True

class AdminContentActionRequest(BaseModel):
    content_id: int
    action: str  # "approve", "reject", "delete"
    reason: Optional[str] = None

class AdminLogResponse(BaseModel):
    id: int
    admin_id: int
    action: str
    entity_type: str
    entity_id: int
    details: Optional[dict] = None
    created_at: datetime
    class Config:
        from_attributes = True

# ============================================================================
# GENERIC ERROR RESPONSE
# ============================================================================

class ErrorResponse(BaseModel):
    detail: str
    status_code: int = 400

class MessageResponse(BaseModel):
    message: str

class SuccessResponse(BaseModel):
    success: bool
    message: str
    data: Optional[dict] = None

# ============= NOTIFICATION SCHEMAS =============
class NotificationCreate(BaseModel):
    user_id: int
    event_id: int
    notification_type: str
    title: str
    message: str
    icon_emoji: str
    related_id: Optional[int] = None
    action_url: Optional[str] = None

class NotificationResponse(BaseModel):
    id: int
    user_id: int
    event_id: int
    notification_type: str
    title: str
    message: str
    icon_emoji: str
    related_id: Optional[int]
    is_read: bool
    action_url: Optional[str]
    created_at: datetime
    read_at: Optional[datetime]

    class Config:
        from_attributes = True

class NotificationsListResponse(BaseModel):
    total: int
    unread_count: int
    notifications: List[NotificationResponse]

class NotificationPreferenceResponse(BaseModel):
    user_id: int
    event_id: int
    enable_session_reminders: bool
    enable_review_notifications: bool
    enable_connection_requests: bool
    enable_messages: bool
    enable_announcements: bool
    enable_email: bool
    enable_push: bool

    class Config:
        from_attributes = True

class NotificationPreferenceUpdate(BaseModel):
    enable_session_reminders: Optional[bool] = None
    enable_review_notifications: Optional[bool] = None
    enable_connection_requests: Optional[bool] = None
    enable_messages: Optional[bool] = None
    enable_announcements: Optional[bool] = None
    enable_email: Optional[bool] = None
    enable_push: Optional[bool] = None    