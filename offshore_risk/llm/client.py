"""
OpenAI client with web_search tool integration.
Handles API calls with retries and structured output.
"""
import os
import json
from typing import Dict, Any, Optional
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from core.logger import setup_logger
from core.schema import OffshoreRiskResponse

logger = setup_logger(__name__)

# OpenAI configuration from environment
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5")
OPENAI_TIMEOUT = int(os.getenv("OPENAI_TIMEOUT", "60"))


class OpenAIClientWrapper:
    """Wrapper for OpenAI client with retry logic."""
    
    def __init__(self):
        """Initialize OpenAI client."""
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        
        self.client = OpenAI(
            api_key=OPENAI_API_KEY,
            timeout=OPENAI_TIMEOUT
        )
        logger.info(f"Initialized OpenAI client with model: {OPENAI_MODEL}")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((Exception,)),
        reraise=True
    )
    def call_with_structured_output(
        self,
        system_prompt: str,
        user_message: str,
        response_schema: Dict[str, Any],
        temperature: float = 0.1,
    ) -> Dict[str, Any]:
        """
        Call OpenAI API with structured output and optional web_search.
        
        Args:
            system_prompt: System instruction
            user_message: User message with transaction data
            response_schema: JSON schema for structured output
            temperature: Model temperature (0.0-1.0)
        
        Returns:
            Parsed JSON response
        
        Raises:
            Exception: If API call fails after retries
        """
        system_prompt_with_schema = (
            f"{system_prompt}\n\n"
            "Please provide your response in a JSON format that strictly adheres to the following schema:\n"
            f"{json.dumps(response_schema, indent=2)}"
        )
        input_text = f"System: {system_prompt_with_schema}\nUser: {user_message}"
        
        # Build request parameters
        request_params = {
            "model": OPENAI_MODEL,
            "input": input_text,
            "tools": [{"type": "web_search"}],
            "tool_choice": "auto",
        }
        
        logger.debug(f"Calling OpenAI API with model={OPENAI_MODEL}, temperature={temperature}")
        
        try:
            # Make API call
            response = self.client.responses.create(**request_params)
            
            # Extract response content
            content = None
            for item in response.output:
                if item.type == 'message':
                    for content_item in item.content:
                        if content_item.type == 'output_text':
                            content = content_item.text
                            break
                if content:
                    break
            
            if not content:
                raise ValueError("Empty response from LLM")
            
            result = json.loads(content)
            logger.debug("Successfully parsed LLM JSON response")
            
            return result
        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            raise
        
        except Exception as e:
            logger.error(f"OpenAI API call failed: {e}")
            raise


def create_response_schema() -> Dict[str, Any]:
    """
    Create JSON schema for OffshoreRiskResponse.
    This ensures the LLM returns properly structured data.
    
    Returns:
        JSON schema dictionary
    """
    return {
        "type": "object",
        "properties": {
            "transaction_id": {
                "type": ["string", "null"],
                "description": "Transaction identifier"
            },
            "direction": {
                "type": "string",
                "enum": ["incoming", "outgoing"],
                "description": "Transaction direction"
            },
            "signals": {
                "type": "object",
                "properties": {
                    "swift_country_code": {"type": ["string", "null"]},
                    "swift_country_name": {"type": ["string", "null"]},
                    "is_offshore_by_swift": {"type": ["boolean", "null"]},
                    "country_name_match": {
                        "type": "object",
                        "properties": {
                            "value": {"type": ["string", "null"]},
                            "score": {"type": ["number", "null"]}
                        },
                        "required": ["value", "score"],
                        "additionalProperties": False
                    },
                    "country_code_match": {
                        "type": "object",
                        "properties": {
                            "value": {"type": ["string", "null"]},
                            "score": {"type": ["number", "null"]}
                        },
                        "required": ["value", "score"],
                        "additionalProperties": False
                    },
                    "city_match": {
                        "type": "object",
                        "properties": {
                            "value": {"type": ["string", "null"]},
                            "score": {"type": ["number", "null"]}
                        },
                        "required": ["value", "score"],
                        "additionalProperties": False
                    }
                },
                "required": [
                    "swift_country_code", "swift_country_name", "is_offshore_by_swift",
                    "country_name_match", "country_code_match", "city_match"
                ],
                "additionalProperties": False
            },
            "classification": {
                "type": "object",
                "properties": {
                    "label": {
                        "type": "string",
                        "enum": ["OFFSHORE_YES", "OFFSHORE_SUSPECT", "OFFSHORE_NO"]
                    },
                    "confidence": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0
                    }
                },
                "required": ["label", "confidence"],
                "additionalProperties": False
            },
            "reasoning_short_ru": {
                "type": "string",
                "description": "Brief reasoning in Russian (1-2 sentences)"
            },
            "sources": {
                "type": "array",
                "items": {"type": "string"},
                "description": "URLs from web_search if used"
            },
            "llm_error": {
                "type": ["string", "null"],
                "description": "Error message if any"
            }
        },
        "required": [
            "transaction_id", "direction", "signals",
            "classification", "reasoning_short_ru", "sources", "llm_error"
        ],
        "additionalProperties": False
    }


# Singleton client instance
_client: Optional[OpenAIClientWrapper] = None


def get_client() -> OpenAIClientWrapper:
    """
    Get or create OpenAI client singleton.
    
    Returns:
        OpenAI client wrapper instance
    """
    global _client
    if _client is None:
        _client = OpenAIClientWrapper()
    return _client
