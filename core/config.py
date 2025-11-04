"""
Centralized configuration management.
All environment variables and settings are defined here.
"""
import os
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings
from pydantic import Field, validator


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Application
    app_name: str = Field(default="Offshore Risk Detection Service", alias="APP_NAME")
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    
    # OpenAI
    openai_api_key: str = Field(..., alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o", alias="OPENAI_MODEL")
    openai_timeout: int = Field(default=60, alias="OPENAI_TIMEOUT")
    
    # Processing
    amount_threshold_kzt: float = Field(default=5000000.0, alias="AMOUNT_THRESHOLD_KZT")
    max_concurrent_llm_calls: int = Field(default=5, alias="MAX_CONCURRENT_LLM_CALLS")
    fuzzy_match_threshold: float = Field(default=0.80, alias="FUZZY_MATCH_THRESHOLD")
    
    # Storage
    temp_storage_path: str = Field(default="/tmp/offshore_risk", alias="TEMP_STORAGE_PATH")
    
    # Data files
    offshore_countries_file: Path = Field(
        default_factory=lambda: Path(__file__).parent.parent / "data" / "offshore_countries.md"
    )
    
    @validator("log_level")
    def validate_log_level(cls, v):
        """Validate log level is one of the standard levels."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"Log level must be one of: {valid_levels}")
        return v_upper
    
    @validator("port")
    def validate_port(cls, v):
        """Validate port is in valid range."""
        if not (1 <= v <= 65535):
            raise ValueError("Port must be between 1 and 65535")
        return v
    
    @validator("max_concurrent_llm_calls")
    def validate_concurrency(cls, v):
        """Validate concurrency setting."""
        if v < 1:
            raise ValueError("Max concurrent LLM calls must be at least 1")
        if v > 50:
            raise ValueError("Max concurrent LLM calls should not exceed 50")
        return v
    
    @validator("fuzzy_match_threshold")
    def validate_threshold(cls, v):
        """Validate fuzzy match threshold."""
        if not (0.0 <= v <= 1.0):
            raise ValueError("Fuzzy match threshold must be between 0.0 and 1.0")
        return v
    
    class Config:
        """Pydantic configuration."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        
    def ensure_directories(self) -> None:
        """Ensure required directories exist."""
        Path(self.temp_storage_path).mkdir(parents=True, exist_ok=True)


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """
    Get application settings singleton.
    
    Returns:
        Settings instance
    """
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.ensure_directories()
    return _settings


def reset_settings() -> None:
    """Reset settings singleton (useful for testing)."""
    global _settings
    _settings = None
