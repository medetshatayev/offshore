"""
Pydantic schemas for request/response validation.
Defines strict JSON schema for LLM structured output.
"""
from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, BeforeValidator, Field, field_validator


def normalize_sources(v):
    """Normalize sources field to handle None from LLM responses."""
    if v is None:
        return []
    return v


def normalize_transaction_id(v):
    """Normalize transaction_id to string (LLM may return int)."""
    if v is None:
        return None
    return str(v)


def normalize_classification(v):
    """Normalize classification field - handle string label or full object."""
    if v is None:
        return v
    if isinstance(v, str):
        # LLM returned just the label string, convert to full object with default confidence
        return {"label": v, "confidence": 1.0}
    return v


class Classification(BaseModel):
    """LLM classification result."""
    label: Literal["OFFSHORE_YES", "OFFSHORE_SUSPECT", "OFFSHORE_NO"]
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score between 0 and 1")


class OffshoreRiskResponse(BaseModel):
    """
    Structured output schema for LLM offshore risk assessment.
    This is the JSON format the LLM must return.
    """
    transaction_id: Annotated[Optional[str], BeforeValidator(normalize_transaction_id)] = None
    direction: Optional[Literal["incoming", "outgoing"]] = None
    amount_kzt: Optional[float] = Field(None, description="Transaction amount in KZT (added locally)")
    classification: Annotated[Classification, BeforeValidator(normalize_classification)] = Field(
        ..., description="Risk classification"
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
        """Ensure sources are valid URLs or empty."""
        if not v:
            return []
        # Basic URL validation
        validated = []
        for url in v:
            if isinstance(url, str) and (url.startswith("http://") or url.startswith("https://")):
                validated.append(url)
        return validated


class BatchOffshoreRiskResponse(BaseModel):
    """Wrapper for a list of risk responses."""
    results: List[OffshoreRiskResponse] = Field(..., description="List of classification results")


class TransactionInput(BaseModel):
    """Input transaction for LLM classification."""
    id: Optional[str] = None
    direction: Literal["incoming", "outgoing"]
    amount_kzt: float
    currency: Optional[str] = None
    swift_code: Optional[str] = None
    country_residence: Optional[str] = None
    country_code: Optional[str] = None
    recipient_country: Optional[str] = None
    payer_country: Optional[str] = None
    city: Optional[str] = None
    payer: Optional[str] = None
    recipient: Optional[str] = None
    recipient_address: Optional[str] = None
    bank_name: Optional[str] = None
    payer_bank: Optional[str] = None
    recipient_bank: Optional[str] = None
    payer_bank_address: Optional[str] = None
    recipient_bank_address: Optional[str] = None
    bank_country: Optional[str] = None
    client_category: Optional[str] = None
    payment_details: Optional[str] = None
    # New fields for incoming transactions
    beneficiary_address: Optional[str] = None
    beneficiary_bank_swift: Optional[str] = None
    beneficiary_correspondent_swift: Optional[str] = None
    payer_address: Optional[str] = None
    payer_correspondent_swift: Optional[str] = None
    payer_correspondent_name: Optional[str] = None
    payer_correspondent_address: Optional[str] = None
    intermediary_bank_1: Optional[str] = None
    intermediary_bank_2: Optional[str] = None
    intermediary_bank_3: Optional[str] = None


# Label translations for output
LABEL_TRANSLATIONS = {
    "OFFSHORE_YES": "ОФШОР: ДА",
    "OFFSHORE_SUSPECT": "ОФШОР: ПОДОЗРЕНИЕ",
    "OFFSHORE_NO": "ОФШОР: НЕТ"
}
