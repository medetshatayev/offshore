"""
Unit tests for custom exceptions.
"""
import pytest

from core.exceptions import (
    OffshoreRiskException,
    FileProcessingError,
    ValidationError,
    LLMError,
    ParsingError,
    ExportError,
    ConfigurationError,
    DataNotFoundError,
)


def test_base_exception():
    """Test base exception class."""
    exc = OffshoreRiskException("Test error", details={"key": "value"})
    assert str(exc) == "Test error"
    assert exc.message == "Test error"
    assert exc.details == {"key": "value"}


def test_exception_hierarchy():
    """Test exception inheritance."""
    assert issubclass(FileProcessingError, OffshoreRiskException)
    assert issubclass(ValidationError, OffshoreRiskException)
    assert issubclass(LLMError, OffshoreRiskException)
    assert issubclass(ParsingError, OffshoreRiskException)
    assert issubclass(ExportError, OffshoreRiskException)
    assert issubclass(ConfigurationError, OffshoreRiskException)
    assert issubclass(DataNotFoundError, OffshoreRiskException)


def test_exception_with_details():
    """Test exception with details dictionary."""
    details = {"file_path": "/test/path", "line": 42}
    exc = ParsingError("Parsing failed", details=details)
    assert exc.message == "Parsing failed"
    assert exc.details["file_path"] == "/test/path"
    assert exc.details["line"] == 42


def test_exception_without_details():
    """Test exception without details."""
    exc = LLMError("API call failed")
    assert exc.message == "API call failed"
    assert exc.details == {}
