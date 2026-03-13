"""
Pydantic schemas for request/response validation.
Defines strict JSON schema for LLM structured output with validation.
"""
from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, BeforeValidator, Field, field_validator


def normalize_sources(v):
    """
    Normalize sources field to handle None from LLM responses.

    Args:
        v: Sources value (may be None or list)

    Returns:
        Empty list if None, otherwise the value itself
    """
    return [] if v is None else v


def normalize_transaction_id(v):
    """
    Normalize transaction_id to string (LLM may return int).

    Args:
        v: Transaction ID value

    Returns:
        String representation or None
    """
    return None if v is None else str(v)


def normalize_classification(v):
    """
    Normalize classification field - handle string label or full object.

    Args:
        v: Classification value (string or dict)

    Returns:
        Normalized classification dict
    """
    if v is None:
        return v
    # LLM returned just the label string, convert to full object
    if isinstance(v, str):
        return {"label": v, "confidence": 1.0}
    return v


class Classification(BaseModel):
    """
    LLM classification result with label and confidence.

    Attributes:
        label: Risk classification label
        confidence: Confidence score between 0 and 1
    """
    label: Literal["OFFSHORE_YES", "OFFSHORE_SUSPECT", "OFFSHORE_NO"]
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0 and 1"
    )


class OffshoreRiskResponse(BaseModel):
    """
    Structured output schema for LLM offshore risk assessment.

    This is the JSON format the LLM must return for each transaction.

    Attributes:
        transaction_id: Transaction identifier
        direction: Transaction direction (incoming/outgoing)
        amount_kzt: Transaction amount in KZT (added locally)
        classification: Risk classification with confidence
        reasoning_short_ru: Brief reasoning in Russian
        sources: List of source URLs from web search
        llm_error: Error message if LLM call failed
    """
    transaction_id: Annotated[Optional[str], BeforeValidator(normalize_transaction_id)] = None
    direction: Optional[Literal["incoming", "outgoing"]] = None
    amount_kzt: Optional[float] = Field(
        None,
        description="Transaction amount in KZT (added locally)"
    )
    classification: Annotated[Classification, BeforeValidator(normalize_classification)] = Field(
        ...,
        description="Risk classification"
    )
    reasoning_short_ru: str = Field(
        ...,
        min_length=10,
        max_length=1000,
        description="Brief reasoning in Russian (1-3 sentences)"
    )
    sources: Annotated[List[str], BeforeValidator(normalize_sources)] = Field(
        default_factory=list,
        description="URLs from web_search if used, empty otherwise"
    )
    llm_error: Optional[str] = Field(
        None,
        description="Error message if LLM call failed"
    )

    @field_validator("sources")
    @classmethod
    def validate_sources(cls, v):
        """
        Ensure sources are valid URLs or empty.

        Args:
            v: Sources list to validate

        Returns:
            Filtered list of valid HTTP(S) URLs
        """
        if not v:
            return []
        # Filter to valid URLs only
        return [
            url for url in v
            if isinstance(url, str) and url.startswith(("http://", "https://"))
        ]


class BatchOffshoreRiskResponse(BaseModel):
    """
    Wrapper for batch of risk responses.

    Attributes:
        results: List of classification results for all transactions
    """
    results: List[OffshoreRiskResponse] = Field(
        ...,
        description="List of classification results"
    )


# Label translations for output
LABEL_TRANSLATIONS = {
    "OFFSHORE_YES": "ОФШОР: ДА",
    "OFFSHORE_SUSPECT": "ОФШОР: ПОДОЗРЕНИЕ",
    "OFFSHORE_NO": "ОФШОР: НЕТ"
}
