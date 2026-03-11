"""
OpenAI Responses API client using direct REST API calls.
Handles API calls with retries and structured output.
"""
import json
import re
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from core.config import get_settings
from core.exceptions import ConfigurationError, LLMError
from core.logger import setup_logger

logger = setup_logger(__name__)
settings = get_settings()

# Static JSON schema for BatchOffshoreRiskResponse — built once at import time.
RESPONSE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "transaction_id": {
                        "type": "string",
                        "description": "Transaction identifier"
                    },
                    "classification": {
                        "type": "object",
                        "properties": {
                            "label": {
                                "type": "string",
                                "enum": ["OFFSHORE_YES", "OFFSHORE_SUSPECT", "OFFSHORE_NO"],
                                "description": "Offshore risk classification label"
                            },
                            "confidence": {
                                "type": "number",
                                "description": "Confidence score between 0.0 and 1.0"
                            }
                        },
                        "required": ["label", "confidence"],
                        "additionalProperties": False,
                        "description": "Offshore risk classification with confidence"
                    },
                    "reasoning_short_ru": {
                        "type": "string",
                        "description": "Brief reasoning in Russian (1-2 sentences) under 500 characters"
                    },
                    "sources": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Citation URLs from web search (include URLs if web_search was used, otherwise empty array)"
                    }
                },
                "required": [
                    "transaction_id",
                    "classification",
                    "reasoning_short_ru",
                    "sources"
                ],
                "additionalProperties": False
            }
        }
    },
    "required": ["results"],
    "additionalProperties": False
}


def extract_json_from_text(content: str) -> str:
    """
    Extract JSON from text, handling markdown code blocks and surrounding text.
    
    Args:
        content: Raw text that may contain JSON wrapped in markdown or surrounded by text
        
    Returns:
        Extracted JSON string
    """
    content = content.strip()
    
    # Try to find JSON in markdown code block first (handles ```json ... ``` or ``` ... ```)
    pattern = r'```(?:json)?\s*(\{[\s\S]*?\})\s*```'
    match = re.search(pattern, content)
    if match:
        return match.group(1)
    
    # Try to find raw JSON object with "results" key (our expected response structure)
    pattern = r'\{[\s\S]*"results"[\s\S]*\}'
    match = re.search(pattern, content)
    if match:
        return match.group(0)
    
    # Return as-is if no patterns matched (let json.loads handle the error)
    return content


class OpenAIClientWrapper:
    """Wrapper for the OpenAI Responses API with retry logic."""
    
    def __init__(self):
        """Initialize REST API client with a persistent connection pool."""
        if not settings.openai_api_key:
            raise ConfigurationError(
                "OPENAI_API_KEY environment variable not set",
                details={"required_key": "OPENAI_API_KEY"}
            )

        self.responses_url = settings.openai_responses_url
        self.api_key = settings.openai_api_key
        self.model = settings.openai_model
        self.timeout = settings.openai_timeout

        # Persistent session with connection pooling sized to concurrency limit
        pool_size = max(settings.max_concurrent_llm_calls, 5)
        self.session = requests.Session()
        adapter = HTTPAdapter(
            pool_connections=pool_size,
            pool_maxsize=pool_size,
        )
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        logger.info(
            "Initialized OpenAI Responses API client with model: %s, url: %s",
            self.model,
            self.responses_url,
        )

    def close(self) -> None:
        """Close the underlying HTTP session and release connection pool."""
        self.session.close()
    
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
        temperature: float = 0.2,
    ) -> Dict[str, Any]:
        """
        Call the OpenAI Responses API with structured output.
        
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
        # Build request payload for the Responses API.
        payload = {
            "model": self.model,
            "instructions": system_prompt,
            "reasoning": {"effort": "medium"},
            "input": user_message,
            "include": ["web_search_call.action.sources"],
            "tools": [{"type": "web_search"}],
            "tool_choice": "auto",
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "batch_offshore_risk_response",
                    "strict": True,
                    "schema": response_schema,
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
            # Make POST request via persistent session; headers passed per-request.
            response = self.session.post(
                self.responses_url,
                headers=headers,
                json=payload,
                timeout=self.timeout
            )
            
            # Raise for HTTP errors (4xx, 5xx)
            response.raise_for_status()
            
            logger.debug(
                "Responses API status: %s, length: %s",
                response.status_code,
                len(response.text),
            )

            completion_data = response.json()

            # Check for API-level error response.
            if completion_data.get("error") and "output" not in completion_data:
                error_detail = completion_data["error"]
                logger.error(
                    "Responses API returned error response: %s",
                    json.dumps(error_detail, ensure_ascii=False)
                    if isinstance(error_detail, (dict, list))
                    else error_detail,
                )
                raise ValueError(
                    f"OpenAI API error: {error_detail.get('message', error_detail) if isinstance(error_detail, dict) else error_detail}"
                )

            content = self._extract_output_text(completion_data)

            if not content:
                logger.error(f"Response keys: {list(completion_data.keys())}")
                logger.error(
                    f"Full response (truncated): {json.dumps(completion_data, ensure_ascii=False, indent=2)[:2000]}"
                )
                raise ValueError(
                    "Unexpected Responses API structure: could not find assistant output text"
                )

            # Extract JSON from response (handles markdown code blocks and surrounding text)
            content_stripped = extract_json_from_text(content)

            # Parse JSON response
            result = json.loads(content_stripped)

            shared_sources = self._extract_response_sources(completion_data)
            if shared_sources and isinstance(result, dict):
                for item in result.get("results", []):
                    if isinstance(item, dict) and item.get("sources") is None:
                        item["sources"] = shared_sources
            
            # Log token usage if available
            if 'usage' in completion_data:
                usage = completion_data['usage']
                input_tokens = usage.get('input_tokens', 'N/A')
                output_tokens = usage.get('output_tokens', 'N/A')
                logger.info(f"Token usage - Input: {input_tokens}, Output: {output_tokens}")
            
            return result

        except LLMError:
            raise
        
        except requests.exceptions.Timeout as e:
            logger.error(f"Responses API request timeout after {self.timeout}s: {e}")
            raise LLMError(
                f"Responses API request timeout after {self.timeout}s",
                details={"responses_url": self.responses_url, "timeout": self.timeout}
            )
        
        except requests.exceptions.HTTPError as e:
            logger.error(f"Responses API HTTP error: {e}")
            raise LLMError(
                f"OpenAI API returned HTTP error: {e}",
                details={
                    "responses_url": self.responses_url,
                    "status_code": getattr(e.response, "status_code", None),
                    "response_text": getattr(e.response, "text", None),
                }
            )
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Responses API request failed: {e}")
            raise LLMError(
                f"Failed to connect to OpenAI API: {str(e)}",
                details={"responses_url": self.responses_url, "error": str(e)}
            )
        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Responses API payload as JSON: {e}")
            raw_response = response.text if 'response' in locals() else "N/A"
            logger.error(f"Raw response: {raw_response}")
            raise LLMError(
                f"OpenAI API returned invalid JSON: {e}",
                details={"raw_response": raw_response}
            )
        
        except ValueError as e:
            logger.error(f"Error parsing Responses API response: {e}")
            raise LLMError(
                f"OpenAI API response parsing error: {str(e)}",
                details={"error": str(e)}
            )
        
        except Exception as e:
            logger.error(f"Unexpected error calling OpenAI API: {e}")
            raise LLMError(
                f"Unexpected error calling OpenAI API: {str(e)}",
                details={"model": self.model, "error": str(e)}
            )

    @staticmethod
    def _extract_output_text(completion_data: Dict[str, Any]) -> Optional[str]:
        """Extract the assistant output text from a Responses API payload."""
        if completion_data.get("output_text"):
            return completion_data["output_text"]

        for item in completion_data.get("output", []):
            if item.get("type") != "message" or item.get("role") != "assistant":
                continue

            for content_item in item.get("content", []):
                content_type = content_item.get("type")
                if content_type == "refusal":
                    raise LLMError(
                        "Model refused to provide a structured response",
                        details={"refusal": content_item.get("refusal")},
                    )
                if content_type == "output_text":
                    return content_item.get("text")

        return None

    @staticmethod
    def _extract_response_sources(completion_data: Dict[str, Any]) -> List[str]:
        """Collect cited URLs exposed by Responses API web-search items."""
        urls: List[str] = []
        seen = set()

        for item in completion_data.get("output", []):
            if item.get("type") == "web_search_call":
                action = item.get("action") or {}
                for source in action.get("sources", []):
                    url = source.get("url")
                    if url and url not in seen:
                        seen.add(url)
                        urls.append(url)

            if item.get("type") == "message":
                for content_item in item.get("content", []):
                    for annotation in content_item.get("annotations", []):
                        if annotation.get("type") != "url_citation":
                            continue
                        url = annotation.get("url")
                        if url and url not in seen:
                            seen.add(url)
                            urls.append(url)

        return urls


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


def close_client() -> None:
    """Close the singleton client's HTTP session if it was initialized."""
    global _client
    if _client is not None:
        _client.close()
        _client = None
