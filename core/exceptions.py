"""
Custom exceptions for better error handling.
"""
from typing import Any, Dict, Optional


class OffshoreRiskException(Exception):
    """Base exception for all offshore risk detection errors."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        """
        Initialize exception.
        
        Args:
            message: Error message
            details: Additional error details
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}


class FileProcessingError(OffshoreRiskException):
    """Raised when file processing fails."""
    pass


class ValidationError(OffshoreRiskException):
    """Raised when data validation fails."""
    pass


class LLMError(OffshoreRiskException):
    """Raised when LLM API call fails."""
    pass


class ParsingError(OffshoreRiskException):
    """Raised when Excel parsing fails."""
    pass


class ExportError(OffshoreRiskException):
    """Raised when Excel export fails."""
    pass


class ConfigurationError(OffshoreRiskException):
    """Raised when configuration is invalid."""
    pass


class DataNotFoundError(OffshoreRiskException):
    """Raised when required data is not found."""
    pass
