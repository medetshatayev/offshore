"""
Centralized configuration management.
All environment variables and settings are defined here.
"""
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator, ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    # Application
    app_name: str = Field(default="Offshore Risk Detection Service", alias="APP_NAME")
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000)
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    
    # OpenAI
    openai_api_key: str = Field(..., alias="OPENAI_API_KEY")
    openai_gateway_url: str = Field(..., alias="OPENAI_GATEWAY_URL")
    openai_model: str = Field(default="gpt-4.1", alias="OPENAI_MODEL")
    openai_timeout: int = Field(default=60, alias="OPENAI_TIMEOUT")
    
    # Processing
    amount_threshold_kzt: float = Field(default=5000000.0, alias="AMOUNT_THRESHOLD_KZT")
    max_concurrent_llm_calls: int = Field(default=5, alias="MAX_CONCURRENT_LLM_CALLS")
    
    # Storage
    temp_storage_path: str = Field(default="files", alias="STORAGE_PATH")
    database_path: str = Field(default="offshore.db", alias="DATABASE_PATH")
    
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is one of the standard levels."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"Log level must be one of: {sorted(valid_levels)}")
        return v_upper
    
    @field_validator("port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        """Validate port is in valid range."""
        if not (1 <= v <= 65535):
            raise ValueError("Port must be between 1 and 65535")
        return v
    
    @field_validator("max_concurrent_llm_calls")
    @classmethod
    def validate_concurrency(cls, v: int) -> int:
        """Validate concurrency setting."""
        if v < 1:
            raise ValueError("Max concurrent LLM calls must be at least 1")
        if v > 50:
            raise ValueError("Max concurrent LLM calls should not exceed 50")
        return v
        
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



