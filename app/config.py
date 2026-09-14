# ============================================================================
# Application Configuration
# ============================================================================

from pydantic_settings import BaseSettings, SettingsConfigDict
import os
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

class Settings(BaseSettings):
    # Database - Safely defaults to empty so it forces loading from .env
    DATABASE_URL: str = os.getenv("DATABASE_URL", "") 
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "") # <-- Add this line
    
    # JWT - Uses a dummy fallback for safety
    SECRET_KEY: str = os.getenv("SECRET_KEY", "fallback-secret-key-do-not-use-in-prod")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # URLs
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "https://frontend-livid-two-96gqet7oy4.vercel.app")
    BACKEND_URL: str = os.getenv("BACKEND_URL", "https://event-ai-backend-o2f3.onrender.com")
    
    # Email
    SMTP_SERVER: str = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    
    # App
    APP_NAME: str = "EventAI"
    APP_VERSION: str = "1.0.0"
    
    # AI Keys
    groq_api_key: str | None = None
    
    # Pydantic V2 Configuration
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

settings = Settings()