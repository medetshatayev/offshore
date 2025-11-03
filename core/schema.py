"""
Pydantic schemas for request/response validation.
Defines strict JSON schema for LLM structured output.
"""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class MatchSignal(BaseModel):
    """Signal from fuzzy matching."""
    value: Optional[str] = None
    score: Optional[float] = Field(None, ge=0.0, le=1.0)


class TransactionSignals(BaseModel):
    """Aggregated matching signals for a transaction."""
    swift_country_code: Optional[str] = None
    swift_country_name: Optional[str] = None
    is_offshore_by_swift: Optional[bool] = None
    country_name_match: MatchSignal = Field(default_factory=MatchSignal)
    country_code_match: MatchSignal = Field(default_factory=MatchSignal)
    city_match: MatchSignal = Field(default_factory=MatchSignal)


class Classification(BaseModel):
    """LLM classification result."""
    label: Literal["OFFSHORE_YES", "OFFSHORE_SUSPECT", "OFFSHORE_NO"]
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score between 0 and 1")


class OffshoreRiskResponse(BaseModel):
    """
    Structured output schema for LLM offshore risk assessment.
    This is the JSON format the LLM must return.
    """
    transaction_id: Optional[str] = None
    direction: Literal["incoming", "outgoing"]
    amount_kzt: float = Field(..., description="Transaction amount in KZT")
    signals: TransactionSignals = Field(..., description="Matching signals from local analysis")
    classification: Classification = Field(..., description="Risk classification")
    reasoning_short_ru: str = Field(
        ...,
        min_length=10,
        max_length=500,
        description="Brief reasoning in Russian (1-2 sentences)"
    )
    sources: List[str] = Field(
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
    bank_name: Optional[str] = None
    # Pre-computed signals
    signals: Optional[dict] = None


# Label translations for output
LABEL_TRANSLATIONS = {
    "OFFSHORE_YES": "ОФШОР: ДА",
    "OFFSHORE_SUSPECT": "ОФШОР: ПОДОЗРЕНИЕ",
    "OFFSHORE_NO": "ОФШОР: НЕТ"
}
