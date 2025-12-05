"""
OpenAI client using direct REST API calls to internal gateway.
Handles API calls with retries and structured output.
"""
import json
from typing import Any, Dict, Optional

import requests
import urllib3
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from core.config import get_settings
from core.exceptions import ConfigurationError, LLMError
from core.logger import setup_logger

# Disable SSL warnings for internal gateway
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = setup_logger(__name__)
settings = get_settings()


class OpenAIClientWrapper:
    """Wrapper for OpenAI REST API with retry logic."""
    
    def __init__(self):
        """Initialize REST API client."""
        if not settings.openai_api_key:
            raise ConfigurationError(
                "OPENAI_API_KEY environment variable not set",
                details={"required_key": "OPENAI_API_KEY"}
            )
        
        self.gateway_url = settings.openai_gateway_url
        self.api_key = settings.openai_api_key
        self.model = settings.openai_model
        self.timeout = settings.openai_timeout
        
        logger.info(f"Initialized OpenAI REST client with model: {self.model}, gateway: {self.gateway_url}")
    
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
        Call OpenAI Gateway completions API with structured output.
        
        Args:
            system_prompt: System instruction
            user_message: User message with transaction data
            response_schema: JSON schema for structured output
            temperature: Model temperature (0.0-1.0)
        
        Returns:
            Parsed JSON response
        
        Raises:
            LLMError: If API call fails after retries
        """
        # Build combined content (system + user message)
        content = f"System: {system_prompt}\n\nUser: {user_message}"
        
        # Build request payload for gateway
        payload = {
            "model": self.model,
            "input": content,
            "tools": [{"type": "web_search"}],
            "tool_choice": "auto",
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "batch_offshore_risk_response",
                    "strict": True,
                    "schema": response_schema
                }
            }
        }
        
        # Add temperature only for non-GPT-5 models (GPT-5 doesn't support temperature)
        if "gpt-5" not in self.model.lower():
            payload["temperature"] = temperature
        
        # Build headers
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        try:
            # Make POST request to gateway
            response = requests.post(
                self.gateway_url,
                headers=headers,
                data=json.dumps(payload),
                verify=False,  # Disable SSL verification for internal gateway
                timeout=self.timeout
            )
            
            # Raise for HTTP errors (4xx, 5xx)
            response.raise_for_status()
            
            # Parse NDJSON response (split by newlines)
            response_text = response.text.strip()
            json_objects = response_text.split('\n')

            # According to the test example, we need the second JSON object
            if len(json_objects) < 2:
                # If only one object, check if it has the expected structure
                if len(json_objects) == 1:
                    completion_data = json.loads(json_objects[0])
                else:
                    raise ValueError("Empty response from gateway")
            else:
                # Parse the second JSON object (index 1)
                completion_data = json.loads(json_objects[1])
            
            # Extract assistant's message content
            content = None
            
            # Check if it's a standard OpenAI response with choices
            if "choices" in completion_data:
                try:
                    content = completion_data["choices"][0]["message"]["content"]
                except (KeyError, IndexError):
                    pass
            
            # Check if it's a response with output list (as seen in logs)
            if not content and "output" in completion_data:
                for item in completion_data["output"]:
                    if item.get("type") == "message" and item.get("role") == "assistant":
                        for content_item in item.get("content", []):
                            if content_item.get("type") == "output_text":
                                content = content_item.get("text")
                                break
                    if content:
                        break
            
            if not content:
                logger.error(f"Response keys: {list(completion_data.keys())}")
                logger.debug(f"Full response: {json.dumps(completion_data, indent=2)}")
                raise ValueError(
                    "Unexpected response structure: could not find content in 'choices' or 'output'"
                )
            
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
            
            # Log token usage if available
            if 'usage' in completion_data:
                usage = completion_data['usage']
                input_tokens = usage.get('prompt_tokens', 'N/A')
                output_tokens = usage.get('completion_tokens', 'N/A')
                logger.debug(f"Token usage - Input: {input_tokens}, Output: {output_tokens}")
            
            return result
        
        except requests.exceptions.Timeout as e:
            logger.error(f"Gateway request timeout after {self.timeout}s: {e}")
            raise LLMError(
                f"Gateway request timeout after {self.timeout}s",
                details={"gateway_url": self.gateway_url, "timeout": self.timeout}
            )
        
        except requests.exceptions.HTTPError as e:
            logger.error(f"Gateway HTTP error: {e}")
            raise LLMError(
                f"Gateway returned HTTP error: {e}",
                details={
                    "gateway_url": self.gateway_url,
                    "status_code": getattr(e.response, "status_code", None),
                    "response_text": getattr(e.response, "text", None),
                }
            )
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Gateway request failed: {e}")
            raise LLMError(
                f"Failed to connect to gateway: {str(e)}",
                details={"gateway_url": self.gateway_url, "error": str(e)}
            )
        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse gateway response as JSON: {e}")
            raw_response = response.text if "response" in dir() else "N/A"
            logger.error(f"Raw response: {raw_response}")
            raise LLMError(
                f"Gateway returned invalid JSON: {e}",
                details={"raw_response": raw_response}
            )
        
        except ValueError as e:
            logger.error(f"Error parsing gateway response: {e}")
            raise LLMError(
                f"Gateway response parsing error: {str(e)}",
                details={"error": str(e)}
            )
        
        except Exception as e:
            logger.error(f"Unexpected error calling gateway: {e}")
            raise LLMError(
                f"Unexpected error calling gateway: {str(e)}",
                details={"model": self.model, "error": str(e)}
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
                            "type": ["string", "integer", "null"],
                            "description": "Transaction identifier (string or integer)"
                        },
                        "direction": {
                            "type": ["string", "null"],
                            "enum": ["incoming", "outgoing", None],
                            "description": "Transaction direction (optional)"
                        },
                        "classification": {
                            "oneOf": [
                                {
                                    "type": "string",
                                    "enum": ["OFFSHORE_YES", "OFFSHORE_SUSPECT", "OFFSHORE_NO"],
                                    "description": "Classification label only"
                                },
                                {
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
                                    "required": ["label"],
                                    "additionalProperties": False
                                }
                            ],
                            "description": "Classification result (string label or object with label and confidence)"
                        },
                        "reasoning_short_ru": {
                            "type": "string",
                            "description": "Brief reasoning in Russian (1-2 sentences)"
                        },
                        "sources": {
                            "type": ["array", "null"],
                            "items": {"type": "string"},
                            "description": "URLs from web_search if used, can be null or empty array"
                        },
                        "llm_error": {
                            "type": ["string", "null"],
                            "description": "Error message if any"
                        }
                    },
                    "required": [
                        "transaction_id",
                        "classification", "reasoning_short_ru"
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
