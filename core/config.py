"""
Centralized configuration management.
All environment variables and settings are defined here.
"""
from pathlib import Path
from typing import Optional

from pydantic import AliasChoices, ConfigDict, Field, field_validator
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
    host: str = Field(..., alias="HOST")
    port: int = Field(..., alias="PORT")
    log_level: str = Field(..., alias="LOG_LEVEL")
    root_path: str = Field(..., alias="ROOT_PATH")
    
    # OpenAI
    openai_api_key: str = Field(..., alias="OPENAI_API_KEY")
    openai_responses_url: str = Field(
        default="https://api.openai.com/v1/responses",
        validation_alias=AliasChoices("OPENAI_RESPONSES_URL", "OPENAI_GATEWAY_URL"),
    )
    openai_model: str = Field(..., alias="OPENAI_MODEL")
    openai_timeout: int = Field(..., alias="OPENAI_TIMEOUT")
    
    # Processing
    amount_threshold_kzt: float = Field(..., alias="AMOUNT_THRESHOLD_KZT")
    max_concurrent_llm_calls: int = Field(..., alias="MAX_CONCURRENT_LLM_CALLS")
    batch_size: int = Field(default=10, alias="BATCH_SIZE")
    
    # Storage
    temp_storage_path: str = Field(..., alias="STORAGE_PATH")
    database_path: str = Field(default="offshore.db", alias="DATABASE_PATH")
    
    # PostgreSQL
    postgres_host: str = Field(..., alias="POSTGRES_HOST")
    postgres_port: int = Field(..., alias="POSTGRES_PORT")
    postgres_db: str = Field(..., alias="POSTGRES_DB")
    postgres_user: str = Field(..., alias="POSTGRES_USER")
    postgres_password: str = Field(..., alias="POSTGRES_PASSWORD")
    postgres_min_pool: int = Field(default=2, alias="POSTGRES_MIN_POOL")
    postgres_max_pool: int = Field(default=10, alias="POSTGRES_MAX_POOL")
    
    @property
    def postgres_dsn(self) -> str:
        """Build PostgreSQL DSN from components."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )
    
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

    @field_validator("batch_size")
    @classmethod
    def validate_batch_size(cls, v: int) -> int:
        """Validate batch size is within safe limits (1-20)."""
        if not (1 <= v <= 20):
            raise ValueError("Batch size must be between 1 and 20")
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


