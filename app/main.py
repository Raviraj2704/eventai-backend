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
    "*"  # For development only
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

# ============================================================================
# CORS MIDDLEWARE (MUST BE FIRST)
# ============================================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],  # Updated to allow all methods
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600  # Updated to 1 hour cache
)

# ============================================================================
# IMPORT ROUTERS (AFTER MIDDLEWARE)
# ============================================================================

from app.routes import (
    auth, users, sessions, speakers, resources, ratings,
    announcements, social, badges, challenges, learning_paths, partners
)

# ============================================================================
# INCLUDE ROUTERS
# ============================================================================

app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
app.include_router(sessions.router, prefix="/api/v1/sessions", tags=["sessions"])
app.include_router(speakers.router, prefix="/api/v1/speakers", tags=["speakers"])
app.include_router(resources.router, prefix="/api/v1/resources", tags=["resources"])
app.include_router(ratings.router, prefix="/api/v1/ratings", tags=["ratings"])
app.include_router(announcements.router, prefix="/api/v1/announcements", tags=["announcements"])
app.include_router(social.router, prefix="/api/v1/social", tags=["social"])
app.include_router(badges.router, prefix="/api/v1/badges", tags=["badges"])
app.include_router(challenges.router, prefix="/api/v1/challenges", tags=["challenges"])
app.include_router(learning_paths.router, prefix="/api/v1/learning-paths", tags=["learning_paths"])
app.include_router(partners.router, prefix="/api/v1/partners", tags=["partners"])

# ============================================================================
# ENDPOINTS (Merged existing health check + new events endpoints)
# ============================================================================

@app.get("/")
async def root():
    return {
        "message": "✅ EventAI API is running",
        "version": "1.0.0",
        "status": "active"
    }

@app.get("/api/v1/health")
async def health_check_v1():
    return {
        "status": "healthy",
        "api": "EventAI v1.0.0"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "app": os.getenv("APP_NAME", "EventAI"),
        "version": os.getenv("APP_VERSION", "1.0.0")
    }

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
# INFO LOGS
# ============================================================================

logger.info("✅ EventAI Backend initialized")
logger.info(f"📍 Running on: {settings.DATABASE_URL[:50]}...")
logger.info(f"🔐 CORS enabled for: {len(allowed_origins)} origins")

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