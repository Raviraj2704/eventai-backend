# ============================================================================
# Main FastAPI Application
# ============================================================================

import logging
import os
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.database import init_db
from app.config import settings
from app.routes.auth import get_current_user

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# CORS CONFIGURATION LOGIC
# ============================================================================
# Combine the hardcoded origins from your existing code with the dynamic env variable

env_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
hardcoded_origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "https://frontend-livid-two-96gqet7oy4.vercel.app",
    "https://event-ai-psi.vercel.app",
]

# Merge lists and remove duplicates
allowed_origins = list(set(env_origins + hardcoded_origins))

# ============================================================================
# LIFESPAN EVENT (Merged startup/shutdown logic)
# ============================================================================
# Note: FastAPI warns against using both @app.on_event and lifespan. 
# The prints from the updated code have been safely merged into the lifespan here.

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup Events
    logger.info("🚀 Starting EventAI Backend...")
    print(f"🚀 EventAI API starting...")
    print(f"📍 Environment: {os.getenv('ENVIRONMENT', 'development')}")
    print(f"🔐 Allowed Origins: {allowed_origins}")
    
    init_db()
    logger.info("✅ Database ready")
    
    yield
    
    # Shutdown Events
    logger.info("👋 Shutting down EventAI Backend...")
    print("🛑 EventAI API shutting down...")

# ============================================================================
# FASTAPI APP
# ============================================================================

app = FastAPI(
    title="EventAI API",
    description="Intelligent Enterprise Event Management Platform",
    version="1.0.0",
    lifespan=lifespan
)

# ================================================
# CORS MIDDLEWARE CONFIGURATION (MUST BE FIRST)
# ================================================

# Get allowed origins from environment variable
allowed_origins_str = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,http://localhost:3000,"
    "https://frontend-livid-two-96gqet7oy4.vercel.app"
)
allowed_origins = [origin.strip() for origin in allowed_origins_str.split(",")]

print("=" * 80)
print("🔐 CORS CONFIGURATION")
print("=" * 80)
print(f"Allowed Origins: {allowed_origins}")
print("=" * 80)

# Add CORS middleware (MUST BE BEFORE OTHER MIDDLEWARE)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,  # Use environment variable
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "Authorization",
        "X-Request-ID",
        "X-Client-Version",
        "Accept",
        "Origin",
    ],
    expose_headers=["Content-Length", "Content-Range", "X-Request-ID"],
    max_age=86400,  # 24 hours
)



# ============================================================================
# IMPORT ROUTERS (AFTER MIDDLEWARE)
# ============================================================================

# Import all 19 route files (includes analytics and AI routes)
from app.routes import (
    auth, sessions, speakers, resources, badges, 
    challenges, leaderboard, learning_paths, ratings,
    social, announcements, engagement, partners, users, admin, analytics, ai_routes, admin
)
# ============================================================================
# INCLUDE ROUTERS
# ============================================================================

app.include_router(auth.router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(users.router, prefix="/api/v1/users", tags=["Users"])
app.include_router(sessions.router, prefix="/api/v1/sessions", tags=["Sessions"])
app.include_router(speakers.router, prefix="/api/v1/speakers", tags=["Speakers"])
app.include_router(resources.router, prefix="/api/v1/resources", tags=["Resources"])
app.include_router(ratings.router, prefix="/api/v1/ratings", tags=["Ratings"])
app.include_router(announcements.router, prefix="/api/v1/announcements", tags=["Announcements"])
app.include_router(social.router, prefix="/api/v1/social", tags=["Social"])
app.include_router(badges.router, prefix="/api/v1/badges", tags=["Badges"])
app.include_router(challenges.router, prefix="/api/v1/challenges", tags=["Challenges"])
app.include_router(leaderboard.router, prefix="/api/v1/leaderboard", tags=["Leaderboard"])
app.include_router(learning_paths.router, prefix="/api/v1/learning_paths", tags=["Learning Paths"])
app.include_router(engagement.router, prefix="/api/v1/engagement", tags=["Engagement"])
app.include_router(partners.router, prefix="/api/v1/partners", tags=["Partners"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["Admin"])
app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["Analytics"])
app.include_router(ai_routes.router, prefix="/api/v1/ai", tags=["AI Features"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["Admin"])

# ============================================================================
# HEALTH CHECK ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "✅ EventAI API is running",
        "version": "1.0.0",
        "status": "active"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "app": os.getenv("APP_NAME", "EventAI"),
        "version": os.getenv("APP_VERSION", "1.0.0")
    }

@app.get("/api/v1/health")
async def health_check_v1():
    """Health check endpoint v1"""
    return {
        "status": "healthy",
        "api": "EventAI v1.0.0"
    }

# ============================================================================
# GENERIC API ENDPOINTS (for testing)
# ============================================================================

@app.get("/api/events")
async def get_events():
    """Get all events"""
    return {
        "data": [],
        "message": "Events retrieved successfully"
    }

@app.post("/api/events")
async def create_event(event_data: dict):
    """Create new event"""
    return {
        "data": event_data,
        "message": "Event created successfully"
    }

# ============================================================================
# LOGGING & INFO
# ============================================================================

logger.info("✅ EventAI Backend initialized")
logger.info(f"📍 Database: {settings.DATABASE_URL[:50]}...")
logger.info(f"🔐 CORS enabled for: {len(allowed_origins)} origins")
logger.info(f"🛣️  Routes loaded: 19 route files + health endpoints")

# ============================================================================
# STARTUP EXECUTION
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", 8000)),
    )