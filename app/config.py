from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "HyperDrop"
    DATABASE_URL: str = "sqlite:///./hyperdrop.db"
    
    # Voice Provider
    VOICE_PROVIDER: str = "mock"  # "mock" or "bolna"
    BOLNA_API_KEY: Optional[str] = None
    BOLNA_BASE_URL: str = "https://api.bolna.dev"
    BOLNA_AGENT_ID: Optional[str] = None
    WEBHOOK_BASE_URL: str = "http://localhost:8000"
    
    # LLM & Translation
    ANTHROPIC_API_KEY: Optional[str] = None
    TRANSLATION_MODEL: str = "claude-3-haiku-20240307"
    
    # Safety & Business Rules
    HIGH_VALUE_THRESHOLD: float = 2000.0  # INR
    TOKEN_EXPIRY_MINUTES: int = 15
    EXCEPTION_RATE_LIMIT_PER_MINUTE: int = 20
    
    model_config = SettingsConfigDict(env_file=".env", extra="allow")

settings = Settings()
