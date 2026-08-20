from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """Application configuration settings loaded from environment variables."""

    # Server settings
    APP_HOST: str = Field(default="0.0.0.0", description="Host address to bind the FastAPI server")
    APP_PORT: int = Field(default=8000, description="Port number to bind the FastAPI server")
    LOG_LEVEL: str = Field(default="INFO", description="Structured logging level")

    # Redis Cache settings
    REDIS_URL: str = Field(default="redis://localhost:6379/0", description="Redis connection URL")

    # LLM Settings
    LLM_PROVIDER: Literal["gemini", "mock"] = Field(
        default="gemini", description="Selected LLM provider backend"
    )
    GEMINI_API_KEY: str = Field(default="", description="Google Gemini API Key")
    GEMINI_MODEL: str = Field(default="gemini-2.5-flash", description="Gemini model name")

    # Intent routing settings
    ENABLE_EMBEDDING_ROUTING: bool = Field(
        default=False, description="Enable embedding-based routing via sentence-transformers"
    )

    # CropO Live API settings
    CROPO_API_BASE_URL: str = Field(
        default="https://cropoappapis.up.railway.app",
        description="Base URL for live CropO Railway API",
    )
    CROPO_API_KEY: str = Field(default="", description="Optional Auth API Key for CropO API")
    DEFAULT_FARM_LAT: float = Field(default=18.5204, description="Default latitude for weather queries")
    DEFAULT_FARM_LON: float = Field(default=73.8567, description="Default longitude for weather queries")
    DEFAULT_PLOT_NAMES: str = Field(
        default="1,2,3,4,5,6,7,8,9,10", description="Comma-separated list of priority plots to monitor"
    )

    # Legacy/Mock API compatibility
    CROP_API_BASE_URL: str = Field(
        default="https://cropoappapis.up.railway.app", description="Base URL for Crop Index API"
    )
    CROP_API_KEY: str = Field(default="", description="Auth token for Crop Index API")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


settings = Settings()
