"""
Main entry point for the offshore risk detection application.
"""
import os
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from core.logger import setup_logger

# Load environment variables
env_file = project_root / ".env"
if env_file.exists():
    load_dotenv(env_file)
else:
    print("Warning: .env file not found. Using environment variables or defaults.")

logger = setup_logger(__name__)


def main():
    """Main application entry point."""
    import uvicorn
    from app.api import app
    
    logger.info("Starting Offshore Risk Detection Service")
    logger.info(f"OpenAI Model: {os.getenv('OPENAI_MODEL', 'gpt-4o')}")
    logger.info(f"Log Level: {os.getenv('LOG_LEVEL', 'INFO')}")
    logger.info(f"Amount Threshold: {os.getenv('AMOUNT_THRESHOLD_KZT', '5000000')} KZT")
    logger.info(f"Max Concurrent LLM Calls: {os.getenv('MAX_CONCURRENT_LLM_CALLS', '5')}")
    
    # Start server
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")
    
    logger.info(f"Starting server on {host}:{port}")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
        timeout_keep_alive=0,  # No timeout - keep connections alive indefinitely
        timeout_graceful_shutdown=30
    )


if __name__ == "__main__":
    main()
