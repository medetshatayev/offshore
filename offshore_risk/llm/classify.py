"""
Transaction classification using LLM with structured output.
Handles per-transaction LLM calls with error handling.
"""
from typing import Dict, Any, Optional
from pydantic import ValidationError
from core.logger import setup_logger
from core.schema import OffshoreRiskResponse
from llm.client import get_client, create_response_schema
from llm.prompts import build_system_prompt, build_websearch_system_prompt, build_user_message

logger = setup_logger(__name__)


def classify_transaction(
    transaction_data: Dict[str, Any],
    temperature: float = 0.1
) -> OffshoreRiskResponse:
    """
    Classify a single transaction for offshore risk using LLM.
    
    Args:
        transaction_data: Normalized transaction dictionary with signals
        temperature: LLM temperature (0.0-1.0)
    
    Returns:
        OffshoreRiskResponse with classification result
    """
    txn_id = transaction_data.get("id", "unknown")
    logger.info(f"Classifying transaction {txn_id}")
    
    try:
        # Build prompts
        system_prompt = build_system_prompt()
        system_prompt += "\n\n" + build_websearch_system_prompt()
        
        user_message = build_user_message(transaction_data)
        
        # Get LLM client
        client = get_client()
        
        # Create response schema
        response_schema = create_response_schema()
        
        # Call LLM
        llm_response = client.call_with_structured_output(
            system_prompt=system_prompt,
            user_message=user_message,
            response_schema=response_schema,
            temperature=temperature,
        )
        
        # Validate response with pydantic
        result = OffshoreRiskResponse(**llm_response)
        
        logger.info(
            f"Transaction {txn_id} classified: {result.classification.label} "
            f"(confidence: {result.classification.confidence:.2f})"
        )
        
        return result
    
    except ValidationError as e:
        logger.error(f"LLM response validation failed for transaction {txn_id}: {e}")
        # Return error response
        return create_error_response(
            transaction_data,
            error_msg=f"Validation error: {str(e)}"
        )
    
    except Exception as e:
        logger.error(f"LLM classification failed for transaction {txn_id}: {e}")
        # Return error response
        return create_error_response(
            transaction_data,
            error_msg=f"LLM error: {str(e)}"
        )


def create_error_response(
    transaction_data: Dict[str, Any],
    error_msg: str
) -> OffshoreRiskResponse:
    """
    Create error response when LLM call fails.
    
    Args:
        transaction_data: Transaction data
        error_msg: Error message
    
    Returns:
        OffshoreRiskResponse with error
    """
    from core.schema import TransactionSignals, Classification, MatchSignal
    
    # Extract basic signals
    signals_data = transaction_data.get("signals", {})
    
    return OffshoreRiskResponse(
        transaction_id=str(transaction_data.get("id", "")),
        direction=transaction_data.get("direction", "incoming"),
        amount_kzt=transaction_data.get("amount_kzt", 0.0),
        signals=TransactionSignals(
            swift_country_code=signals_data.get("swift_country_code"),
            swift_country_name=signals_data.get("swift_country_name"),
            is_offshore_by_swift=signals_data.get("is_offshore_by_swift"),
            country_code_match=MatchSignal(
                value=signals_data.get("country_code_match", {}).get("value"),
                score=signals_data.get("country_code_match", {}).get("score")
            ),
            country_name_match=MatchSignal(
                value=signals_data.get("country_name_match", {}).get("value"),
                score=signals_data.get("country_name_match", {}).get("score")
            ),
            city_match=MatchSignal(
                value=signals_data.get("city_match", {}).get("value"),
                score=signals_data.get("city_match", {}).get("score")
            )
        ),
        classification=Classification(
            label="OFFSHORE_SUSPECT",
            confidence=0.0
        ),
        reasoning_short_ru="Ошибка при обработке LLM. Требуется ручная проверка.",
        sources=[],
        llm_error=error_msg
    )
