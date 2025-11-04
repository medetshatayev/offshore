"""
Unit tests for configuration module.
"""
import pytest
from pydantic import ValidationError

from core.config import Settings, get_settings, reset_settings


def test_settings_defaults():
    """Test default configuration values."""
    reset_settings()
    # Mock environment with minimal required vars
    import os
    os.environ["OPENAI_API_KEY"] = "test-key"
    
    settings = get_settings()
    assert settings.app_name == "Offshore Risk Detection Service"
    assert settings.host == "0.0.0.0"
    assert settings.port == 8000
    assert settings.log_level == "INFO"
    assert settings.openai_model == "gpt-4o"
    assert settings.amount_threshold_kzt == 5000000.0
    assert settings.max_concurrent_llm_calls == 5


def test_settings_validation_port():
    """Test port validation."""
    import os
    os.environ["OPENAI_API_KEY"] = "test-key"
    os.environ["PORT"] = "99999"
    
    reset_settings()
    with pytest.raises(ValidationError):
        get_settings()


def test_settings_validation_log_level():
    """Test log level validation."""
    import os
    os.environ["OPENAI_API_KEY"] = "test-key"
    os.environ["LOG_LEVEL"] = "INVALID"
    
    reset_settings()
    with pytest.raises(ValidationError):
        get_settings()


def test_settings_singleton():
    """Test settings singleton behavior."""
    import os
    os.environ["OPENAI_API_KEY"] = "test-key"
    
    reset_settings()
    settings1 = get_settings()
    settings2 = get_settings()
    assert settings1 is settings2
