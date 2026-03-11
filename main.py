"""
Main entry point for the offshore risk detection application.

This module initializes the application, loads configuration,
and starts the FastAPI server.
"""
import sys

from core.config import get_settings
from core.exceptions import ConfigurationError
from core.logger import setup_logger

logger = setup_logger(__name__)


def main():
    """Main application entry point."""
    try:
        # Load and validate configuration
        settings = get_settings()
        
        import uvicorn
        from app.api import app
        
        logger.info("Starting Offshore Risk Detection Service")
        logger.info(f"Root Path: {settings.root_path}")
        logger.info(f"OpenAI Model: {settings.openai_model}")
        logger.info(f"Log Level: {settings.log_level}")
        logger.info(f"Amount Threshold: {settings.amount_threshold_kzt:,.0f} KZT")
        logger.info(f"Max Concurrent LLM Calls: {settings.max_concurrent_llm_calls}")
        logger.info(f"Temp Storage: {settings.temp_storage_path}")
        
        logger.info(f"Starting server on {settings.host}:{settings.port}")
        
        uvicorn.run(
            app,
            host=settings.host,
            port=settings.port,
            log_level=settings.log_level.lower()
        )
    
    except ConfigurationError as e:
        logger.error(f"Configuration error: {e.message}")
        if e.details:
            logger.error(f"Details: {e.details}")
        sys.exit(1)
    
    except Exception as e:
        logger.error(f"Failed to start application: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
