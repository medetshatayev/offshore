"""
Main entry point for the offshore risk detection application.

This module initializes the application, loads configuration,
and starts the FastAPI server.
"""
import sys
from pathlib import Path

# Add project root to Python path for module imports
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

from core.config import get_settings
from core.exceptions import ConfigurationError
from core.logger import setup_logger

# Load environment variables from .env file
_env_file = PROJECT_ROOT / ".env"
if _env_file.exists():
    load_dotenv(_env_file)
else:
    print("Warning: .env file not found. Using environment variables or defaults.")

logger = setup_logger(__name__)


def main():
    """Main application entry point."""
    try:
        # Load and validate configuration
        settings = get_settings()
        
        import uvicorn
        from app.api import app
        
        logger.info("Starting Offshore Risk Detection Service")
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
