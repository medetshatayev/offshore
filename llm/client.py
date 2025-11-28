"""
OpenAI client with web_search tool integration.
Handles API calls with retries and structured output.
"""
import json
from typing import Any, Dict, Optional

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from core.config import get_settings
from core.exceptions import LLMError, ConfigurationError
from core.logger import setup_logger

logger = setup_logger(__name__)
settings = get_settings()


class OpenAIClientWrapper:
    """Wrapper for OpenAI client with retry logic."""
    
    def __init__(self):
        """Initialize OpenAI client."""
        if not settings.openai_api_key:
            raise ConfigurationError(
                "OPENAI_API_KEY environment variable not set",
                details={"required_key": "OPENAI_API_KEY"}
            )
        
        self.client = OpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.openai_timeout
        )
        logger.info(f"Initialized OpenAI client with model: {settings.openai_model}")
    
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
        Call OpenAI Responses API with structured output and web_search.
        
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
        # Enhance system prompt with schema instructions
        system_prompt_with_schema = (
            f"{system_prompt}\n\n"
            "Please provide your response in a JSON format that strictly adheres to the following schema:\n"
            f"{json.dumps(response_schema, indent=2)}\n\n"
            "Respond ONLY with valid JSON, no additional text before or after."
        )
        
        # Build input combining system and user messages
        input_text = f"System: {system_prompt_with_schema}\n\nUser: {user_message}"
        
        # Build request parameters for Responses API
        request_params = {
            "model": settings.openai_model,
            "input": input_text,
            "tools": [{"type": "web_search"}],
            "tool_choice": "auto",
            "temperature": temperature,
        }
        
        logger.debug(f"Calling OpenAI Responses API with model={settings.openai_model}, temperature={temperature}")
        
        try:
            # Make API call using Responses API
            response = self.client.responses.create(**request_params)
            
            # Extract response content and citations
            content = None
            citations = []
            
            for item in response.output:
                if item.type == 'message':
                    for content_item in item.content:
                        if content_item.type == 'output_text':
                            content = content_item.text
                            # Extract URL citations from annotations
                            if hasattr(content_item, 'annotations') and content_item.annotations:
                                for annotation in content_item.annotations:
                                    if annotation.type == 'url_citation' and hasattr(annotation, 'url'):
                                        citations.append(annotation.url)
                            break
                if content:
                    break
            
            if not content:
                raise ValueError("Empty response from LLM")
            
            # Strip markdown code blocks if present
            content_stripped = content.strip()
            if content_stripped.startswith("```"):
                # Remove opening
                lines = content_stripped.split('\n')
                if lines[0].startswith("```"):
                    lines = lines[1:]
                # Remove closing
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                content_stripped = '\n'.join(lines).strip()
            
            # Parse JSON response
            result = json.loads(content_stripped)
            
            # Add extracted citations to root sources (assuming batch structure allows it or just log)
            # For batch response, citations might belong to specific items. 
            # Since we can't easily map citations to specific batch items without more complex logic,
            # we'll log them. If the schema has a top-level 'sources', we'd add them there.
            # But BatchOffshoreRiskResponse doesn't have top-level sources.
            if citations:
                logger.debug(f"Extracted {len(citations)} citations from web_search (batch mode)")
            
            logger.debug("Successfully parsed LLM JSON response")
            if hasattr(response, 'usage'):
                logger.debug(f"Token usage - Input: {response.usage.input_tokens}, Output: {response.usage.output_tokens}")
            
            return result
        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.error(f"Raw response: {content if 'content' in locals() else 'N/A'}")
            if 'content_stripped' in locals() and content_stripped != content:
                logger.error(f"After stripping markdown: {content_stripped}")
            raise LLMError(
                f"LLM returned invalid JSON: {e}",
                details={"raw_response": content if 'content' in locals() else None}
            )
        
        except Exception as e:
            logger.error(f"OpenAI API call failed: {e}")
            raise LLMError(
                f"OpenAI API call failed: {str(e)}",
                details={"model": settings.openai_model, "error": str(e)}
            )


def create_response_schema() -> Dict[str, Any]:
    """
    Create JSON schema for BatchOffshoreRiskResponse.
    This ensures the LLM returns properly structured data for a batch of transactions.
    
    Returns:
        JSON schema dictionary
    """
    return {
        "type": "object",
        "properties": {
            "results": {
                "type": "array",
                "items": {
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
                        "transaction_id", "direction",
                        "classification", "reasoning_short_ru", "sources", "llm_error"
                    ],
                    "additionalProperties": False
                },
                "description": "List of classification results"
            }
        },
        "required": ["results"],
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
