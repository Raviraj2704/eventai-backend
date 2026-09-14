# ============================================================================
# SQLAlchemy Models
# ============================================================================
# File: app/models.py
# Purpose: Define ORM models for database tables
# Status: Production-Ready ✅
# NOTE: This is Part 1 - User & Auth Models
      
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, Float, DateTime, 
    ForeignKey, JSON, Enum as SQLEnum, Table, UniqueConstraint,
    Index
)
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from app.database import Base


# ============================================================================
# ENUMS
# ============================================================================

class SessionType(str, enum.Enum):
    """Session type enum"""
    KEYNOTE = "keynote"
    WORKSHOP = "workshop"
    PANEL = "panel"
    NETWORKING = "networking"


class DifficultyLevel(str, enum.Enum):
    """Difficulty level enum"""
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class ExperienceLevel(str, enum.Enum):
    """Experience level enum"""
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class ResourceType(str, enum.Enum):
    """Resource type enum"""
    PDF = "pdf"
    VIDEO = "video"
    PRESENTATION = "presentation"
    DOCUMENT = "document"
    CODE = "code"
    IMAGE = "image"


class RatingType(str, enum.Enum):
    """Rating type enum"""
    SESSION = "session"
    SPEAKER = "speaker"
    EVENT = "event"
    EXPERIENCE = "experience"
    PARTNER = "partner"


class AnnouncementType(str, enum.Enum):
    """Announcement type enum"""
    EVENT = "event"
    SCHEDULE = "schedule"
    IMPORTANT = "important"
    UPDATE = "update"
    REMINDER = "reminder"


class AnnouncementCategory(str, enum.Enum):
    """Announcement category enum"""
    GENERAL = "general"
    TECHNICAL = "technical"
    LOGISTICAL = "logistical"
    URGENT = "urgent"


class Priority(str, enum.Enum):
    """Priority level enum"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class Rarity(str, enum.Enum):
    """Badge rarity enum"""
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"


class Tier(str, enum.Enum):
    """Leaderboard tier enum"""
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"
    DIAMOND = "diamond"


class ChallengeDifficulty(str, enum.Enum):
    """Challenge difficulty enum"""
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class PartnerCategory(str, enum.Enum):
    """Partner category enum"""
    SPONSOR = "sponsor"
    PARTNER = "partner"
    VENDOR = "vendor"
    MEDIA = "media"


class PartnerTier(str, enum.Enum):
    """Partner tier enum"""
    PLATINUM = "platinum"
    GOLD = "gold"
    SILVER = "silver"
    BRONZE = "bronze"


class QuestionType(str, enum.Enum):
    """Quiz question type enum"""
    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE = "true_false"
    SHORT_ANSWER = "short_answer"


# ============================================================================
# TABLE 1: Users
# ============================================================================

class User(Base):
    """
    User account and profile information
    
    Attributes:
        id: Unique user identifier
        username: Unique username (3-50 chars)
        email: Unique email address
        password_hash: Bcrypt hashed password
        first_name: User's first name
        last_name: User's last name
        avatar_url: Cloud storage URL for profile picture
        bio: User biography
        company: Company name
        job_title: Job position
        phone: Phone number
        is_active: Account active status
        is_verified: Email verified status
        is_admin: Admin privileges flag
        last_login: Last login timestamp
        created_at: Account creation timestamp
        updated_at: Last update timestamp
    """
    __tablename__ = "users"
    
    # Primary Key
    id = Column(Integer, primary_key=True, index=True)
    
    # Authentication
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(120), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    
    # Profile
    first_name = Column(String(50))
    last_name = Column(String(50))
    avatar_url = Column(String(255))
    bio = Column(Text)
    company = Column(String(100))
    job_title = Column(String(100))
    phone = Column(String(20))
    
    # Status
    is_active = Column(Boolean, default=True, index=True)
    is_verified = Column(Boolean, default=False)
    is_admin = Column(Boolean, default=False, index=True)
    
    # Timestamps
    last_login = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    sessions_attended = relationship(
        "SessionAttendance",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    ratings = relationship(
        "Rating",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    social_posts = relationship(
        "SocialPost",
        back_populates="author",
        cascade="all, delete-orphan"
    )
    social_comments = relationship(
        "SocialComment",
        back_populates="author",
        cascade="all, delete-orphan"
    )
    badges = relationship(
        "Badge",
        secondary="user_badges",
        back_populates="users"
    )
    leaderboard = relationship(
        "Leaderboard",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan"
    )
    learning_paths_enrolled = relationship(
        "UserLearningProgress",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    challenges_joined = relationship(
        "UserChallenge",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    resources_uploaded = relationship(
        "Resource",
        back_populates="uploaded_by_user",
        foreign_keys="Resource.uploaded_by_user_id"
    )
    speaker_profile = relationship(
        "Speaker",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan"
    )
    
    # Indexes
    __table_args__ = (
        Index('idx_user_email_active', 'email', 'is_active'),
        Index('idx_user_username_active', 'username', 'is_active'),
        Index('idx_user_created_at', 'created_at'),
    )
    
    def __repr__(self):
        return f"<User(id={self.id}, username={self.username}, email={self.email})>"


# ============================================================================
# TABLE 2: Speakers
# ============================================================================

class Speaker(Base):
    """
    Speaker profile information
    
    Attributes:
        id: Unique speaker identifier
        user_id: Link to user account
        bio: Speaker biography
        expertise_areas: JSON array of expertise topics
        company: Company name
        job_title: Job position
        years_experience: Years in field
        experience_level: beginner/intermediate/advanced/expert
        total_talks: Total presentations given
        total_audience: Total people spoken to
        average_rating: Average rating (1-5)
        total_ratings: Number of ratings
        linkedin_url: LinkedIn profile URL
        twitter_url: Twitter profile URL
        website_url: Personal website URL
        is_featured: Featured speaker status
        created_at: Registration timestamp
        updated_at: Last update timestamp
    """
    __tablename__ = "speakers"
    
    # Primary Key
    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign Keys
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)
    
    # Profile
    bio = Column(Text)
    expertise_areas = Column(JSON)  # Array of strings
    company = Column(String(100))
    job_title = Column(String(100))
    years_experience = Column(Integer)
    experience_level = Column(SQLEnum(ExperienceLevel))
    
    # Stats
    total_talks = Column(Integer, default=0)
    total_audience = Column(Integer, default=0)
    average_rating = Column(Float, default=0.0)
    total_ratings = Column(Integer, default=0)
    
    # Social Links
    linkedin_url = Column(String(255))
    twitter_url = Column(String(255))
    website_url = Column(String(255))
    
    # Status
    is_featured = Column(Boolean, default=False, index=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="speaker_profile")
    sessions = relationship(
        "Session",
        secondary="session_speakers",
        back_populates="speakers"
    )
    
    def __repr__(self):
        return f"<Speaker(id={self.id}, user_id={self.user_id})>"


# ============================================================================
# TABLE 3: Sessions
# ============================================================================

class Session(Base):
    """
    Event session/talk information
    
    Attributes:
        id: Unique session identifier
        title: Session title
        description: Detailed description
        primary_speaker_id: Primary speaker (deprecated, use session_speakers)
        session_type: keynote/workshop/panel/networking
        category: Session category/track
        start_time: Session start datetime
        end_time: Session end datetime
        location: Physical or virtual location
        duration_minutes: Session length
        capacity: Max attendees
        actual_attendees: Current attendance count
        is_published: Published status
        difficulty_level: beginner/intermediate/advanced
        prerequisites: Required prior knowledge
        learning_outcomes: What attendees will learn
        resource_links: JSON array of resource URLs
        average_rating: Average session rating (1-5)
        total_ratings: Number of ratings
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """
    __tablename__ = "sessions"
    
    # Primary Key
    id = Column(Integer, primary_key=True, index=True)
    
    # Basic Info
    title = Column(String(255), nullable=False)
    description = Column(Text)
    session_type = Column(SQLEnum(SessionType), nullable=False)
    category = Column(String(50))
    
    # Time & Location
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime, nullable=False)
    location = Column(String(100))
    duration_minutes = Column(Integer)
    
    # Capacity
    capacity = Column(Integer)  # NULL = unlimited
    actual_attendees = Column(Integer, default=0)
    
    # Content
    difficulty_level = Column(SQLEnum(DifficultyLevel))
    prerequisites = Column(Text)
    learning_outcomes = Column(Text)
    resource_links = Column(JSON)  # Array of URLs
    
    # Status
    is_published = Column(Boolean, default=False, index=True)
    
    # Ratings
    average_rating = Column(Float, default=0.0)
    total_ratings = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    speakers = relationship(
        "Speaker",
        secondary="session_speakers",
        back_populates="sessions"
    )
    attendees = relationship(
        "SessionAttendance",
        back_populates="session",
        cascade="all, delete-orphan"
    )
    ratings = relationship(
        "Rating",
        back_populates="session",
        cascade="all, delete-orphan",
        foreign_keys="Rating.session_id"
    )
    resources = relationship(
        "Resource",
        back_populates="session",
        cascade="all, delete-orphan"
    )
    
    # Indexes
    __table_args__ = (
        Index('idx_session_start_time', 'start_time'),
        Index('idx_session_is_published', 'is_published'),
        Index('idx_session_category', 'category'),
    )
    
    def __repr__(self):
        return f"<Session(id={self.id}, title={self.title})>"


# ============================================================================
# TABLE 4: SessionSpeakers (Junction Table - Many-to-Many)
# ============================================================================

session_speakers = Table(
    'session_speakers',
    Base.metadata,
    Column('id', Integer, primary_key=True, index=True),
    Column('session_id', Integer, ForeignKey('sessions.id'), nullable=False, index=True),
    Column('speaker_id', Integer, ForeignKey('speakers.id'), nullable=False, index=True),
    Column('order', Integer, default=1),
    Column('created_at', DateTime, default=datetime.utcnow),
    UniqueConstraint('session_id', 'speaker_id', name='uq_session_speaker'),
)


# ============================================================================
# TABLE 5: SessionAttendance
# ============================================================================

class SessionAttendance(Base):
    """
    Track user attendance for sessions
    
    Attributes:
        id: Unique attendance record identifier
        session_id: Session reference
        user_id: User/attendee reference
        check_in_time: Check-in timestamp
        rating: User rating (1-5)
        attended: Confirmed attendance flag
        created_at: Registration timestamp
    """
    __tablename__ = "session_attendance"
    
    # Primary Key
    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign Keys
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Attendance Info
    check_in_time = Column(DateTime)
    rating = Column(Integer)  # 1-5
    attended = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    session = relationship("Session", back_populates="attendees")
    user = relationship("User", back_populates="sessions_attended")
    
    # Unique Constraint
    __table_args__ = (
        UniqueConstraint('session_id', 'user_id', name='uq_session_user_attendance'),
        Index('idx_session_user_attendance', 'session_id', 'user_id'),
    )
    
    def __repr__(self):
        return f"<SessionAttendance(session_id={self.session_id}, user_id={self.user_id})>"


# ============================================================================
# TABLE 6: Ratings
# ============================================================================

class Rating(Base):
    """
    User ratings for sessions, speakers, and other content
    
    Attributes:
        id: Unique rating identifier
        user_id: User who rated
        rating_type: session/speaker/event/experience/partner
        target_id: ID of rated item (polymorphic)
        score: Rating value (1-5)
        feedback: Optional feedback text
        is_anonymous: Anonymous rating flag
        helpful_count: Upvotes on this rating
        session_id: Session reference (if rating session)
        resource_id: Resource reference (if rating resource)
        created_at: Rating timestamp
        updated_at: Last update timestamp
    """
    __tablename__ = "ratings"

    resource_id = Column(Integer, ForeignKey("resources.id"), index=True) 
    learning_path_id = Column(Integer, ForeignKey("learning_paths.id"), nullable=True)   
    
    # Primary Key
    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign Keys
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), index=True)
    
    # Rating Info
    rating_type = Column(SQLEnum(RatingType), nullable=False)
    target_id = Column(Integer, nullable=False)  # Polymorphic reference
    score = Column(Integer, nullable=False)  # 1-5
    feedback = Column(Text)
    is_anonymous = Column(Boolean, default=False)
    helpful_count = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="ratings")
    session = relationship("Session", back_populates="ratings", foreign_keys=[session_id])
    resource = relationship("Resource", back_populates="ratings", foreign_keys=[resource_id])
    
    # Indexes
    __table_args__ = (
        Index('idx_rating_type_target', 'rating_type', 'target_id'),
        Index('idx_rating_user', 'user_id'),
    )
    
    def __repr__(self):
        return f"<Rating(id={self.id}, user_id={self.user_id}, score={self.score})>"

# ============================================================================
# TABLE 7: Resources
# ============================================================================

class Resource(Base):
    """
    Learning materials and downloadable files
    
    Attributes:
        id: Unique resource identifier
        title: Resource title
        description: Resource description
        resource_type: pdf/video/presentation/document/code/image
        category: Resource category
        file_url: Cloud storage URL
        file_size_mb: File size in megabytes
        uploaded_by_user_id: Uploader reference
        session_id: Associated session
        is_published: Publication status
        download_count: Total downloads
        average_rating: Resource rating (1-5)
        total_ratings: Number of ratings
        tags: JSON array of tags
        created_at: Upload timestamp
        updated_at: Last update timestamp
    """
    __tablename__ = "resources"
    
    # Primary Key
    id = Column(Integer, primary_key=True, index=True)
    
    # Basic Info
    title = Column(String(255), nullable=False)
    description = Column(Text)
    resource_type = Column(SQLEnum(ResourceType), nullable=False)
    category = Column(String(50), index=True)
    
    # File Info
    file_url = Column(String(255), nullable=False)
    file_size_mb = Column(Float)
    
    # Relationships
    uploaded_by_user_id = Column(Integer, ForeignKey("users.id"), index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), index=True)
    
    # Status
    is_published = Column(Boolean, default=False)
    
    # Engagement
    download_count = Column(Integer, default=0)
    average_rating = Column(Float, default=0.0)
    total_ratings = Column(Integer, default=0)
    
    # Tags
    tags = Column(JSON)  # Array of strings
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    uploaded_by_user = relationship("User", back_populates="resources_uploaded")
    session = relationship("Session", back_populates="resources")
    ratings = relationship(
        "Rating",
        back_populates="resource",
        cascade="all, delete-orphan",
        foreign_keys="Rating.resource_id"
    )
    
    # Indexes
    __table_args__ = (
        Index('idx_resource_type', 'resource_type'),
        Index('idx_resource_category', 'category'),
        Index('idx_resource_uploaded_by', 'uploaded_by_user_id'),
    )
    
    def __repr__(self):
        return f"<Resource(id={self.id}, title={self.title})>"


# ============================================================================
# TABLE 8: Announcements
# ============================================================================

class Announcement(Base):
    """
    Event announcements and notifications
    
    Attributes:
        id: Unique announcement identifier
        title: Announcement title
        content: Announcement body
        announcement_type: event/schedule/important/update/reminder
        category: general/technical/logistical/urgent
        priority: low/medium/high/urgent
        created_by_user_id: Creator/admin reference
        image_url: Optional announcement image
        expires_at: Auto-delete date
        is_published: Publication status
        view_count: Total views
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """
    __tablename__ = "announcements"
    
    # Primary Key
    id = Column(Integer, primary_key=True, index=True)
    
    # Content
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    
    # Classification
    announcement_type = Column(SQLEnum(AnnouncementType), nullable=False, index=True)
    category = Column(SQLEnum(AnnouncementCategory))
    priority = Column(SQLEnum(Priority), default=Priority.MEDIUM, index=True)
    
    # Creator
    created_by_user_id = Column(Integer, ForeignKey("users.id"), index=True)
    
    # Media
    image_url = Column(String(255))
    
    # Status & Engagement
    is_published = Column(Boolean, default=False, index=True)
    view_count = Column(Integer, default=0)
    
    # Expiry
    expires_at = Column(DateTime)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    created_by_user = relationship("User")
    
    # Indexes
    __table_args__ = (
        Index('idx_announcement_type', 'announcement_type'),
        Index('idx_announcement_priority', 'priority'),
        Index('idx_announcement_created_by', 'created_by_user_id'),
        Index('idx_announcement_is_published', 'is_published'),
    )
    
    def __repr__(self):
        return f"<Announcement(id={self.id}, title={self.title})>"


# ============================================================================
# TABLE 9: SocialPosts
# ============================================================================

class SocialPost(Base):
    """
    User-generated social wall posts
    
    Attributes:
        id: Unique post identifier
        user_id: Post author
        content: Post content
        image_url: Optional image URL
        like_count: Total likes
        comment_count: Total comments
        share_count: Total shares
        is_moderated: Moderation status
        is_approved: Approval status
        created_at: Post timestamp
        updated_at: Last edit timestamp
    """
    __tablename__ = "social_posts"
    
    # Primary Key
    id = Column(Integer, primary_key=True, index=True)
    
    # Author
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Content
    content = Column(Text, nullable=False)
    image_url = Column(String(255))
    
    # Engagement
    like_count = Column(Integer, default=0)
    comment_count = Column(Integer, default=0)
    share_count = Column(Integer, default=0)
    
    # Moderation
    is_moderated = Column(Boolean, default=False)
    is_approved = Column(Boolean, default=True, index=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    author = relationship("User", back_populates="social_posts")
    comments = relationship(
        "SocialComment",
        back_populates="post",
        cascade="all, delete-orphan"
    )
    
    # Indexes
    __table_args__ = (
        Index('idx_social_post_user', 'user_id'),
        Index('idx_social_post_created_at', 'created_at'),
        Index('idx_social_post_is_approved', 'is_approved'),
    )
    
    def __repr__(self):
        return f"<SocialPost(id={self.id}, user_id={self.user_id})>"


# ============================================================================
# TABLE 10: SocialComments
# ============================================================================

class SocialComment(Base):
    """
    Comments on social posts
    
    Attributes:
        id: Unique comment identifier
        post_id: Parent post
        user_id: Comment author
        content: Comment content
        like_count: Comment likes
        is_approved: Moderation status
        created_at: Comment timestamp
        updated_at: Last edit timestamp
    """
    __tablename__ = "social_comments"
    
    # Primary Key
    id = Column(Integer, primary_key=True, index=True)
    
    # References
    post_id = Column(Integer, ForeignKey("social_posts.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Content
    content = Column(Text, nullable=False)
    
    # Engagement
    like_count = Column(Integer, default=0)
    
    # Moderation
    is_approved = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    post = relationship("SocialPost", back_populates="comments")
    author = relationship("User", back_populates="social_comments")
    
    # Indexes
    __table_args__ = (
        Index('idx_social_comment_post', 'post_id'),
        Index('idx_social_comment_user', 'user_id'),
        Index('idx_social_comment_created_at', 'created_at'),
    )
    
    def __repr__(self):
        return f"<SocialComment(id={self.id}, post_id={self.post_id})>"

# ============================================================================
# TABLE 11: Badges
# ============================================================================

class Badge(Base):
    """
    Achievement badges for gamification
    
    Attributes:
        id: Unique badge identifier
        name: Badge name
        description: Badge description
        icon_url: Badge image/icon URL
        requirement: Condition to earn badge
        points_reward: Points awarded
        rarity: common/uncommon/rare/epic/legendary
        is_active: Active status
        created_at: Creation timestamp
    """
    __tablename__ = "badges"
    
    # Primary Key
    id = Column(Integer, primary_key=True, index=True)
    
    # Info
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text)
    icon_url = Column(String(255))
    requirement = Column(String(255))
    
    # Reward
    points_reward = Column(Integer, default=0)
    
    # Status
    rarity = Column(SQLEnum(Rarity), default=Rarity.COMMON)
    is_active = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    users = relationship(
        "User",
        secondary="user_badges",
        back_populates="badges"
    )
    
    # Indexes
    __table_args__ = (
        Index('idx_badge_name', 'name'),
        Index('idx_badge_rarity', 'rarity'),
    )
    
    def __repr__(self):
        return f"<Badge(id={self.id}, name={self.name})>"


# ============================================================================
# TABLE 12: UserBadges (Junction Table - Many-to-Many)
# ============================================================================

class UserBadge(Base):
    """
    Track badges earned by users
    
    Attributes:
        id: Unique record identifier
        user_id: User reference
        badge_id: Badge reference
        earned_at: Earning timestamp
    """
    __tablename__ = "user_badges"
    
    # Primary Key
    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign Keys
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    badge_id = Column(Integer, ForeignKey("badges.id"), nullable=False, index=True)
    
    # Timestamps
    earned_at = Column(DateTime, default=datetime.utcnow)
    
    # Unique Constraint
    __table_args__ = (
        UniqueConstraint('user_id', 'badge_id', name='uq_user_badge'),
    )
    
    def __repr__(self):
        return f"<UserBadge(user_id={self.user_id}, badge_id={self.badge_id})>"


# ============================================================================
# TABLE 13: Leaderboard
# ============================================================================

class Leaderboard(Base):
    """
    User engagement points and rankings
    
    Attributes:
        id: Unique leaderboard entry
        user_id: User reference (unique)
        total_points: Cumulative points
        sessions_attended: Count
        sessions_rated: Count
        posts_created: Count
        badges_earned: Count
        challenges_completed: Count
        rank: Current rank position
        tier: bronze/silver/gold/platinum/diamond
        last_activity: Last engagement timestamp
        updated_at: Last score update timestamp
    """
    __tablename__ = "leaderboard"
    
    # Primary Key
    id = Column(Integer, primary_key=True, index=True)
    
    # User Reference (unique)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)
    
    # Points & Ranking
    total_points = Column(Integer, default=0, index=True)
    rank = Column(Integer)
    tier = Column(SQLEnum(Tier), default=Tier.BRONZE, index=True)
    
    # Activity Counts
    sessions_attended = Column(Integer, default=0)
    sessions_rated = Column(Integer, default=0)
    posts_created = Column(Integer, default=0)
    badges_earned = Column(Integer, default=0)
    challenges_completed = Column(Integer, default=0)
    
    # Last Activity
    last_activity = Column(DateTime)
    
    # Timestamps
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="leaderboard")
    
    # Indexes
    __table_args__ = (
        Index('idx_leaderboard_total_points', 'total_points'),
        Index('idx_leaderboard_tier', 'tier'),
    )
    
    def __repr__(self):
        return f"<Leaderboard(user_id={self.user_id}, rank={self.rank})>"


# ============================================================================
# TABLE 14: Challenges
# ============================================================================

class Challenge(Base):
    """
    Engagement challenges
    
    Attributes:
        id: Unique challenge identifier
        title: Challenge title
        description: Detailed description
        icon_emoji: Challenge icon
        difficulty: easy/medium/hard
        duration_days: Challenge length
        objectives: JSON array of objectives
        points_reward: Points for completion
        badge_reward_id: Badge earned on completion
        participants_count: Total participants
        completion_rate: Completion percentage
        start_date: Challenge start
        end_date: Challenge end
        is_active: Active status
        top_participants: JSON with top performers
        created_at: Creation timestamp
    """
    __tablename__ = "challenges"
    
    # Primary Key
    id = Column(Integer, primary_key=True, index=True)
    
    # Info
    title = Column(String(255), nullable=False)
    description = Column(Text)
    icon_emoji = Column(String(10))
    
    # Details
    difficulty = Column(SQLEnum(ChallengeDifficulty), default=ChallengeDifficulty.MEDIUM)
    duration_days = Column(Integer, nullable=False)
    objectives = Column(JSON, nullable=False)  # Array of strings
    
    # Rewards
    points_reward = Column(Integer, nullable=False)
    badge_reward_id = Column(Integer, ForeignKey("badges.id"))
    
    # Dates
    start_date = Column(DateTime, nullable=False, index=True)
    end_date = Column(DateTime, nullable=False)
    
    # Status
    is_active = Column(Boolean, default=True)
    
    # Engagement
    participants_count = Column(Integer, default=0)
    completion_rate = Column(Float, default=0.0)
    top_participants = Column(JSON)  # Array with top performers
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    badge_reward = relationship("Badge")
    participants = relationship(
        "UserChallenge",
        back_populates="challenge",
        cascade="all, delete-orphan"
    )
    
    # Indexes
    __table_args__ = (
        Index('idx_challenge_start_date', 'start_date'),
        Index('idx_challenge_end_date', 'end_date'),
        Index('idx_challenge_difficulty', 'difficulty'),
    )
    
    def __repr__(self):
        return f"<Challenge(id={self.id}, title={self.title})>"


# ============================================================================
# TABLE 15: UserChallenges (Many-to-Many)
# ============================================================================

class UserChallenge(Base):
    """
    Track user participation in challenges
    
    Attributes:
        id: Unique participation record
        user_id: Participant
        challenge_id: Challenge
        score: Challenge score
        is_completed: Completion status
        joined_at: Join date
        completed_at: Completion date
    """
    __tablename__ = "user_challenges"
    
    # Primary Key
    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign Keys
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    challenge_id = Column(Integer, ForeignKey("challenges.id"), nullable=False, index=True)
    
    # Participation
    score = Column(Integer, default=0)
    is_completed = Column(Boolean, default=False)
    
    # Timestamps
    joined_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    
    # Relationships
    user = relationship("User", back_populates="challenges_joined")
    challenge = relationship("Challenge", back_populates="participants")
    
    # Unique Constraint
    __table_args__ = (
        UniqueConstraint('user_id', 'challenge_id', name='uq_user_challenge'),
    )
    
    def __repr__(self):
        return f"<UserChallenge(user_id={self.user_id}, challenge_id={self.challenge_id})>"


# ============================================================================
# TABLE 16: Partnerships/Sponsors
# ============================================================================

class Partnership(Base):
    """
    Sponsor and partner information
    
    Attributes:
        id: Unique partner identifier
        name: Partner name
        category: sponsor/partner/vendor/media
        description: Partner description
        logo_url: Partner logo URL
        website_url: Company website
        contact_email: Contact email
        contact_name: Contact person name
        tier: platinum/gold/silver/bronze
        featured: Featured partner status
        created_at: Partnership start
        updated_at: Last update
    """
    __tablename__ = "partnerships"
    
    # Primary Key
    id = Column(Integer, primary_key=True, index=True)
    
    # Info
    name = Column(String(255), nullable=False)
    category = Column(SQLEnum(PartnerCategory), nullable=False, index=True)
    description = Column(Text)
    
    # Contact & Links
    logo_url = Column(String(255))
    website_url = Column(String(255))
    contact_email = Column(String(120))
    contact_name = Column(String(100))
    
    # Status
    tier = Column(SQLEnum(PartnerTier))
    featured = Column(Boolean, default=False, index=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Indexes
    __table_args__ = (
        Index('idx_partnership_category', 'category'),
        Index('idx_partnership_tier', 'tier'),
    )
    
    def __repr__(self):
        return f"<Partnership(id={self.id}, name={self.name})>"

# ============================================================================
# TABLE 17: LearningPaths
# ============================================================================

class LearningPath(Base):
    """
    Structured learning path definitions
    
    Attributes:
        id: Unique path identifier
        title: Path title
        description: Detailed description
        icon_emoji: Emoji icon
        difficulty_level: beginner/intermediate/advanced/expert
        duration_weeks: Estimated completion time
        outcomes: JSON array of learning outcomes
        benefits: JSON array of benefits
        prerequisites: JSON array of prerequisites
        instructor_id: Instructor/creator reference
        total_modules: Number of modules
        average_rating: Path rating (1-5)
        total_ratings: Number of ratings
        enrollments: Total enrollments
        is_published: Publication status
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """
    __tablename__ = "learning_paths"
    
    # Primary Key
    id = Column(Integer, primary_key=True, index=True)
    
    # Info
    title = Column(String(255), nullable=False)
    description = Column(Text)
    icon_emoji = Column(String(10))
    
    # Details
    difficulty_level = Column(SQLEnum(DifficultyLevel), nullable=False)
    duration_weeks = Column(Integer)
    
    # Content
    outcomes = Column(JSON)  # Array of strings
    benefits = Column(JSON)  # Array of strings
    prerequisites = Column(JSON)  # Array of strings
    
    # Instructor
    instructor_id = Column(Integer, ForeignKey("users.id"), index=True)
    
    # Structure
    total_modules = Column(Integer, default=0)
    
    # Engagement
    average_rating = Column(Float, default=0.0)
    total_ratings = Column(Integer, default=0)
    enrollments = Column(Integer, default=0)
    
    # Status
    is_published = Column(Boolean, default=False, index=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    instructor = relationship("User")
    modules = relationship(
        "LearningModule",
        back_populates="learning_path",
        cascade="all, delete-orphan"
    )
    user_progress = relationship(
        "UserLearningProgress",
        back_populates="learning_path",
        cascade="all, delete-orphan"
    )
    ratings = relationship(
        "Rating",
        back_populates="learning_path",
        cascade="all, delete-orphan",
        foreign_keys="Rating.learning_path_id"
    )
    
    # Indexes
    __table_args__ = (
        Index('idx_learning_path_difficulty', 'difficulty_level'),
        Index('idx_learning_path_instructor', 'instructor_id'),
        Index('idx_learning_path_is_published', 'is_published'),
    )
    
    def __repr__(self):
        return f"<LearningPath(id={self.id}, title={self.title})>"


# ============================================================================
# TABLE 18: LearningModules
# ============================================================================

class LearningModule(Base):
    """
    Modules within learning paths
    
    Attributes:
        id: Unique module identifier
        learning_path_id: Parent path reference
        title: Module title
        description: Module description
        module_order: Order in path
        duration_hours: Time to complete
        lessons_json: JSON array of lessons
        skills_taught: JSON array of skills
        created_at: Creation timestamp
    """
    __tablename__ = "learning_modules"
    
    # Primary Key
    id = Column(Integer, primary_key=True, index=True)
    
    # Reference
    learning_path_id = Column(Integer, ForeignKey("learning_paths.id"), nullable=False, index=True)
    
    # Info
    title = Column(String(255), nullable=False)
    description = Column(Text)
    
    # Structure
    module_order = Column(Integer, nullable=False)
    duration_hours = Column(Float)
    
    # Content
    lessons_json = Column(JSON)  # Array of strings
    skills_taught = Column(JSON)  # Array of strings
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    learning_path = relationship("LearningPath", back_populates="modules")
    
    # Indexes
    __table_args__ = (
        Index('idx_learning_module_path', 'learning_path_id'),
        Index('idx_learning_module_order', 'module_order'),
    )
    
    def __repr__(self):
        return f"<LearningModule(id={self.id}, title={self.title})>"


# ============================================================================
# TABLE 19: UserLearningProgress
# ============================================================================

class UserLearningProgress(Base):
    """
    Track user progress in learning paths
    
    Attributes:
        id: Unique progress record
        user_id: Student reference
        learning_path_id: Path reference
        progress_percentage: Completion percentage (0-100)
        modules_completed: Completed module count
        current_module_id: Current working module
        started_at: Enrollment date
        completed_at: Completion date
        is_completed: Completion status
        certificate_issued: Certificate awarded flag
        updated_at: Last update timestamp
    """
    __tablename__ = "user_learning_progress"
    
    # Primary Key
    id = Column(Integer, primary_key=True, index=True)
    
    # References
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    learning_path_id = Column(Integer, ForeignKey("learning_paths.id"), nullable=False, index=True)
    current_module_id = Column(Integer, ForeignKey("learning_modules.id"))
    
    # Progress
    progress_percentage = Column(Integer, default=0)
    modules_completed = Column(Integer, default=0)
    
    # Status
    is_completed = Column(Boolean, default=False)
    certificate_issued = Column(Boolean, default=False)
    
    # Timestamps
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="learning_paths_enrolled")
    learning_path = relationship("LearningPath", back_populates="user_progress")
    
    # Unique Constraint
    __table_args__ = (
        UniqueConstraint('user_id', 'learning_path_id', name='uq_user_learning_path'),
    )
    
    def __repr__(self):
        return f"<UserLearningProgress(user_id={self.user_id}, learning_path_id={self.learning_path_id})>"


# Add relationship to Rating model for learning_paths
learning_path_id = Column(Integer, ForeignKey("learning_paths.id"), index=True)
learning_path = relationship("LearningPath", back_populates="ratings", foreign_keys=[learning_path_id])

# ============================================================================
# TABLE 20: Polls (Page 21: Engagement Center)
# ============================================================================

class Poll(Base):
    """
    User polls for engagement
    
    Attributes:
        id: Unique poll identifier
        question: Poll question (max 500 chars)
        description: Optional description
        created_by_user_id: Creator reference
        total_votes: Total votes cast
        expires_at: Poll expiration
        is_active: Active status
        created_at: Creation timestamp
    """
    __tablename__ = "polls"
    
    # Primary Key
    id = Column(Integer, primary_key=True, index=True)
    
    # Content
    question = Column(String(500), nullable=False)
    description = Column(Text)
    
    # Creator
    created_by_user_id = Column(Integer, ForeignKey("users.id"), index=True)
    
    # Engagement
    total_votes = Column(Integer, default=0)
    
    # Status
    is_active = Column(Boolean, default=True, index=True)
    
    # Expiry
    expires_at = Column(DateTime)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    created_by_user = relationship("User")
    options = relationship(
        "PollOption",
        back_populates="poll",
        cascade="all, delete-orphan"
    )
    votes = relationship(
        "PollVote",
        back_populates="poll",
        cascade="all, delete-orphan"
    )
    
    # Indexes
    __table_args__ = (
        Index('idx_poll_is_active', 'is_active'),
        Index('idx_poll_created_by', 'created_by_user_id'),
    )
    
    def __repr__(self):
        return f"<Poll(id={self.id}, question={self.question[:50]})>"


# ============================================================================
# TABLE 21: PollOptions
# ============================================================================

class PollOption(Base):
    """
    Options in a poll
    
    Attributes:
        id: Unique option identifier
        poll_id: Parent poll reference
        option_text: Option text
        vote_count: Votes for this option
        percentage: Vote percentage
        order: Display order
    """
    __tablename__ = "poll_options"
    
    # Primary Key
    id = Column(Integer, primary_key=True, index=True)
    
    # Reference
    poll_id = Column(Integer, ForeignKey("polls.id"), nullable=False, index=True)
    
    # Content
    option_text = Column(String(255), nullable=False)
    
    # Stats
    vote_count = Column(Integer, default=0)
    percentage = Column(Float, default=0.0)
    
    # Display
    order = Column(Integer, default=1)
    
    # Relationships
    poll = relationship("Poll", back_populates="options")
    
    # Indexes
    __table_args__ = (
        Index('idx_poll_option_poll', 'poll_id'),
    )
    
    def __repr__(self):
        return f"<PollOption(id={self.id}, option_text={self.option_text})>"


# ============================================================================
# TABLE 22: PollVotes
# ============================================================================

class PollVote(Base):
    """
    Track user votes on polls
    
    Attributes:
        id: Unique vote record
        poll_id: Poll reference
        user_id: Voter reference
        option_id: Selected option
        voted_at: Vote timestamp
    """
    __tablename__ = "poll_votes"
    
    # Primary Key
    id = Column(Integer, primary_key=True, index=True)
    
    # References
    poll_id = Column(Integer, ForeignKey("polls.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    option_id = Column(Integer, ForeignKey("poll_options.id"), nullable=False, index=True)
    
    # Timestamp
    voted_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    poll = relationship("Poll", back_populates="votes")
    user = relationship("User")
    
    # Unique Constraint (one vote per user per poll)
    __table_args__ = (
        UniqueConstraint('poll_id', 'user_id', name='uq_poll_user_vote'),
    )
    
    def __repr__(self):
        return f"<PollVote(poll_id={self.poll_id}, user_id={self.user_id})>"


# ============================================================================
# TABLE 23: Quizzes (Page 21: Engagement Center)
# ============================================================================

class Quiz(Base):
    """
    Quiz assessments
    
    Attributes:
        id: Unique quiz identifier
        title: Quiz title
        description: Quiz description
        difficulty: easy/medium/hard
        duration_minutes: Time limit
        passing_score: Required % to pass
        total_questions: Number of questions
        points_reward: Points for completion
        created_by_user_id: Creator reference
        is_published: Publication status
        created_at: Creation timestamp
    """
    __tablename__ = "quizzes"
    
    # Primary Key
    id = Column(Integer, primary_key=True, index=True)
    
    # Content
    title = Column(String(255), nullable=False)
    description = Column(Text)
    
    # Settings
    difficulty = Column(SQLEnum(ChallengeDifficulty), default=ChallengeDifficulty.MEDIUM)
    duration_minutes = Column(Integer, nullable=False)
    passing_score = Column(Integer, nullable=False)  # Percentage
    points_reward = Column(Integer, nullable=False)
    
    # Structure
    total_questions = Column(Integer, nullable=False)
    
    # Creator
    created_by_user_id = Column(Integer, ForeignKey("users.id"), index=True)
    
    # Status
    is_published = Column(Boolean, default=False, index=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    created_by_user = relationship("User")
    questions = relationship(
        "QuizQuestion",
        back_populates="quiz",
        cascade="all, delete-orphan"
    )
    attempts = relationship(
        "UserQuizAttempt",
        back_populates="quiz",
        cascade="all, delete-orphan"
    )
    
    # Indexes
    __table_args__ = (
        Index('idx_quiz_difficulty', 'difficulty'),
        Index('idx_quiz_is_published', 'is_published'),
    )
    
    def __repr__(self):
        return f"<Quiz(id={self.id}, title={self.title})>"


# ============================================================================
# TABLE 24: QuizQuestions
# ============================================================================

class QuizQuestion(Base):
    """
    Quiz questions
    
    Attributes:
        id: Unique question identifier
        quiz_id: Parent quiz reference
        question_text: Question text
        question_order: Display order
        question_type: multiple_choice/true_false/short_answer
        options_json: JSON array of options (for multiple choice)
        correct_answer: Correct answer
        points_value: Points for correct answer
    """
    __tablename__ = "quiz_questions"
    
    # Primary Key
    id = Column(Integer, primary_key=True, index=True)
    
    # Reference
    quiz_id = Column(Integer, ForeignKey("quizzes.id"), nullable=False, index=True)
    
    # Content
    question_text = Column(String(500), nullable=False)
    
    # Structure
    question_order = Column(Integer, nullable=False)
    question_type = Column(SQLEnum(QuestionType), nullable=False)
    
    # Options
    options_json = Column(JSON)  # For multiple_choice
    
    # Answer
    correct_answer = Column(String(255), nullable=False)
    points_value = Column(Integer, nullable=False)
    
    # Relationships
    quiz = relationship("Quiz", back_populates="questions")
    
    # Indexes
    __table_args__ = (
        Index('idx_quiz_question_quiz', 'quiz_id'),
        Index('idx_quiz_question_order', 'question_order'),
    )
    
    def __repr__(self):
        return f"<QuizQuestion(id={self.id}, quiz_id={self.quiz_id})>"


# ============================================================================
# TABLE 25: UserQuizAttempts
# ============================================================================

class UserQuizAttempt(Base):
    """
    Track user quiz attempts
    
    Attributes:
        id: Unique attempt record
        user_id: Quiz taker reference
        quiz_id: Quiz reference
        score: Points earned
        percentage: Score percentage
        passed: Pass/fail status
        completed_at: Completion timestamp
        time_spent_minutes: Time used
    """
    __tablename__ = "user_quiz_attempts"
    
    # Primary Key
    id = Column(Integer, primary_key=True, index=True)
    
    # References
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    quiz_id = Column(Integer, ForeignKey("quizzes.id"), nullable=False, index=True)
    
    # Results
    score = Column(Integer, default=0)
    percentage = Column(Float, default=0.0)
    passed = Column(Boolean, default=False)
    time_spent_minutes = Column(Integer)
    
    # Timestamp
    completed_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User")
    quiz = relationship("Quiz", back_populates="attempts")
    answers = relationship(
        "QuizAnswer",
        back_populates="attempt",
        cascade="all, delete-orphan"
    )
    
    # Indexes
    __table_args__ = (
        Index('idx_user_quiz_attempt_user', 'user_id'),
        Index('idx_user_quiz_attempt_quiz', 'quiz_id'),
    )
    
    def __repr__(self):
        return f"<UserQuizAttempt(user_id={self.user_id}, quiz_id={self.quiz_id})>"


# ============================================================================
# TABLE 26: QuizAnswers
# ============================================================================

class QuizAnswer(Base):
    """
    User answers to quiz questions
    
    Attributes:
        id: Unique answer record
        attempt_id: Quiz attempt reference
        question_id: Question reference
        user_answer: Answer provided
        is_correct: Correct/incorrect flag
        points_earned: Points awarded
    """
    __tablename__ = "quiz_answers"
    
    # Primary Key
    id = Column(Integer, primary_key=True, index=True)
    
    # References
    attempt_id = Column(Integer, ForeignKey("user_quiz_attempts.id"), nullable=False, index=True)
    question_id = Column(Integer, ForeignKey("quiz_questions.id"), nullable=False, index=True)
    
    # Answer
    user_answer = Column(String(255), nullable=False)
    is_correct = Column(Boolean, nullable=False)
    points_earned = Column(Integer, default=0)
    
    # Relationships
    attempt = relationship("UserQuizAttempt", back_populates="answers")
    
    # Indexes
    __table_args__ = (
        Index('idx_quiz_answer_attempt', 'attempt_id'),
        Index('idx_quiz_answer_question', 'question_id'),
    )
    
    def __repr__(self):
        return f"<QuizAnswer(attempt_id={self.attempt_id}, question_id={self.question_id})>"


# ============================================================================
# TABLE 27: Activities (Page 21: Engagement Center)
# ============================================================================

class Activity(Base):
    """
    Engagement activities
    
    Attributes:
        id: Unique activity identifier
        title: Activity title
        description: Activity description
        activity_type: Type of activity
        priority: low/medium/high
        instructions: How to complete
        points_reward: Points for completion
        deadline: Activity deadline
        created_at: Creation timestamp
    """
    __tablename__ = "activities"
    
    # Primary Key
    id = Column(Integer, primary_key=True, index=True)
    
    # Content
    title = Column(String(255), nullable=False)
    description = Column(Text)
    activity_type = Column(String(50), nullable=False)
    instructions = Column(Text)
    
    # Details
    priority = Column(SQLEnum(Priority), default=Priority.MEDIUM)
    points_reward = Column(Integer, default=0)
    deadline = Column(DateTime)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    completions = relationship(
        "UserActivityCompletion",
        back_populates="activity",
        cascade="all, delete-orphan"
    )
    
    def __repr__(self):
        return f"<Activity(id={self.id}, title={self.title})>"


# ============================================================================
# TABLE 28: UserActivityCompletions
# ============================================================================

class UserActivityCompletion(Base):
    """
    Track activity completions by users
    
    Attributes:
        id: Unique completion record
        user_id: User reference
        activity_id: Activity reference
        completion_notes: Notes on completion
        completed_at: Completion timestamp
    """
    __tablename__ = "user_activity_completions"
    
    # Primary Key
    id = Column(Integer, primary_key=True, index=True)
    
    # References
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    activity_id = Column(Integer, ForeignKey("activities.id"), nullable=False, index=True)
    
    # Completion
    completion_notes = Column(Text)
    completed_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User")
    activity = relationship("Activity", back_populates="completions")
    
    # Unique Constraint
    __table_args__ = (
        UniqueConstraint('user_id', 'activity_id', name='uq_user_activity_completion'),
    )
    
    def __repr__(self):
        return f"<UserActivityCompletion(user_id={self.user_id}, activity_id={self.activity_id})>"

# ============================================================================
# TABLE 29: AdminLogs
# ============================================================================

class AdminLog(Base):
    """
    Audit trail for admin actions
    
    Attributes:
        id: Unique log entry identifier
        admin_id: Admin who acted
        action: Action type
        entity_type: Entity modified
        entity_id: Entity ID
        old_values: Previous values (JSON)
        new_values: Updated values (JSON)
        ip_address: Admin IP address
        timestamp: Action timestamp
    """
    __tablename__ = "admin_logs"
    
    # Primary Key
    id = Column(Integer, primary_key=True, index=True)
    
    # Admin Info
    admin_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Action Details
    action = Column(String(100), nullable=False)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(Integer)
    
    # Changes
    old_values = Column(JSON)
    new_values = Column(JSON)
    
    # Security
    ip_address = Column(String(45))
    
    # Timestamp
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Relationships
    admin = relationship("User")
    
    # Indexes
    __table_args__ = (
        Index('idx_admin_log_admin_id', 'admin_id'),
        Index('idx_admin_log_entity_type', 'entity_type'),
        Index('idx_admin_log_timestamp', 'timestamp'),
    )
    
    def __repr__(self):
        return f"<AdminLog(id={self.id}, action={self.action})>"  

# ============= NOTIFICATION MODELS =============
class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    event_id = Column(Integer, index=True)
    notification_type = Column(String(50))  
    title = Column(String(200))
    message = Column(Text)
    icon_emoji = Column(String(10))
    related_id = Column(Integer, nullable=True)  
    is_read = Column(Boolean, default=False)
    action_url = Column(String(500), nullable=True)  
    created_at = Column(DateTime, default=datetime.utcnow)
    read_at = Column(DateTime, nullable=True)

class NotificationPreference(Base):
    __tablename__ = "notification_preferences"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, unique=True)
    event_id = Column(Integer, index=True)
    enable_session_reminders = Column(Boolean, default=True)
    enable_review_notifications = Column(Boolean, default=True)
    enable_connection_requests = Column(Boolean, default=True)
    enable_messages = Column(Boolean, default=True)
    enable_announcements = Column(Boolean, default=True)
    enable_email = Column(Boolean, default=False)
    enable_push = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)