"""
Transaction classification using LLM with structured output.
Handles batch transaction LLM calls with error handling.
"""
from typing import Any, Dict, List

from pydantic import ValidationError

from core.exceptions import LLMError
from core.logger import setup_logger
from core.schema import BatchOffshoreRiskResponse, OffshoreRiskResponse, Classification
from llm.client import get_client, create_response_schema
from llm.prompts import build_system_prompt, build_user_message

logger = setup_logger(__name__)

# Max retries for validation errors (malformed LLM responses)
MAX_VALIDATION_RETRIES = 3


def classify_batch(
    transactions: List[Dict[str, Any]],
    temperature: float = 0.1
) -> List[OffshoreRiskResponse]:
    """
    Classify a batch of transactions for offshore risk using LLM.
    
    Args:
        transactions: List of normalized transaction dictionaries
        temperature: LLM temperature (0.0-1.0)
    
    Returns:
        List of OffshoreRiskResponse objects
    """
    if not transactions:
        return []
        
    logger.info(f"Classifying batch of {len(transactions)} transactions")
    
    try:
        # Build prompts
        system_prompt = build_system_prompt()
        user_message = build_user_message(transactions)
        
        # Get LLM client
        client = get_client()
        
        # Create response schema
        response_schema = create_response_schema()
        
        # Retry loop for validation errors (malformed LLM responses)
        batch_result = None
        last_validation_error = None
        
        for attempt in range(MAX_VALIDATION_RETRIES):
            # Call LLM
            llm_response = client.call_with_structured_output(
                system_prompt=system_prompt,
                user_message=user_message,
                response_schema=response_schema,
                temperature=temperature,
            )
            
            # Validate response with pydantic
            try:
                batch_result = BatchOffshoreRiskResponse(**llm_response)
                break  # Success - exit retry loop
            except ValidationError as e:
                last_validation_error = e
                if attempt < MAX_VALIDATION_RETRIES - 1:
                    logger.warning(
                        f"Validation failed (attempt {attempt + 1}/{MAX_VALIDATION_RETRIES}), retrying: {e}"
                    )
                    continue
                # Final attempt failed - will be handled below
        
        # If all retries failed, raise the last validation error
        if batch_result is None:
            raise last_validation_error
        
        # Map results back to original transactions to ensure order/completeness
        # Create a map of id -> response
        response_map = {res.transaction_id: res for res in batch_result.results if res.transaction_id}
        
        final_results = []
        for txn in transactions:
            txn_id = str(txn.get("id", "unknown"))
            
            if txn_id in response_map:
                # Use the returned result
                result = response_map[txn_id]
                
                # Set amount from local data since we removed it from LLM schema
                result.amount_kzt = txn.get("amount_kzt", 0.0)
                
                # Set direction from local data if LLM didn't return it
                if result.direction is None:
                    result.direction = txn.get("direction", "incoming")
                
                final_results.append(result)
            else:
                logger.warning(f"Transaction {txn_id} missing from LLM response, marking as error")
                # Create error response for missing item
                final_results.append(create_error_response(
                    txn,
                    error_msg="LLM failed to return classification for this transaction"
                ))
        
        logger.info(f"Batch processed: {len(final_results)} results")
        return final_results
    
    except ValidationError as e:
        logger.error(f"LLM batch response validation failed after {MAX_VALIDATION_RETRIES} attempts: {e}")
        return [create_error_response(t, f"Validation error: {str(e)}") for t in transactions]
    
    except LLMError as e:
        logger.error(f"LLM error for batch: {e}")
        return [create_error_response(t, f"LLM error: {e.message}") for t in transactions]
    
    except Exception as e:
        logger.error(f"Unexpected error in batch classification: {e}")
        return [create_error_response(t, f"Unexpected error: {str(e)}") for t in transactions]


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
    return OffshoreRiskResponse(
        transaction_id=str(transaction_data.get("id", "")),
        direction=transaction_data.get("direction", "incoming"),
        amount_kzt=transaction_data.get("amount_kzt", 0.0),
        classification=Classification(
            label="OFFSHORE_SUSPECT",
            confidence=0.0
        ),
        reasoning_short_ru="Ошибка при обработке LLM. Требуется ручная проверка.",
        sources=[],
        llm_error=error_msg
    )
