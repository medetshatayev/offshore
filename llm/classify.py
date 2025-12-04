"""
Transaction classification using LLM with structured output.
Handles batch transaction LLM calls with error handling.
"""
import json
from typing import Any, Dict, List

from pydantic import ValidationError

from core.config import get_settings
from core.exceptions import LLMError
from core.logger import setup_logger
from core.schema import BatchOffshoreRiskResponse, OffshoreRiskResponse, Classification
from llm.client import get_client, create_response_schema
from llm.prompts import build_system_prompt, build_user_message

logger = setup_logger(__name__)
settings = get_settings()


def _check_consistency(results: List[OffshoreRiskResponse]) -> List[str]:
    """
    Check for consistency between classification label and reasoning.
    
    Detects contradictions like:
    - Classification is OFFSHORE_YES but reasoning says "set to OFFSHORE_NO"
    - Classification is OFFSHORE_NO but reasoning says "is offshore" or "in the list"
    
    Args:
        results: List of classification results
    
    Returns:
        List of error messages for inconsistent results (empty if all consistent)
    """
    errors = []
    
    for i, result in enumerate(results):
        label = result.classification.label
        reasoning = result.reasoning_short_ru.lower()
        llm_error = (result.llm_error or "").lower()
        
        # Check for explicit contradiction patterns
        contradictions = []
        
        # Case 1: Label is OFFSHORE_YES but error/reasoning mentions "set to OFFSHORE_NO"
        if label == "OFFSHORE_YES":
            if "set to offshore_no" in llm_error or "классификатор — не офшор" in reasoning:
                contradictions.append(f"Label is OFFSHORE_YES but reasoning/error indicates it should be OFFSHORE_NO")
        
        # Case 2: Label is OFFSHORE_NO but error/reasoning mentions "set to OFFSHORE_YES"
        if label == "OFFSHORE_NO":
            if "set to offshore_yes" in llm_error or "в списке офшоров" in reasoning:
                contradictions.append(f"Label is OFFSHORE_NO but reasoning indicates it is in offshore list")
        
        # Case 3: Check for general misclassification warnings in llm_error
        if "potential misclassification" in llm_error or "controversial" in llm_error:
            contradictions.append(f"LLM flagged potential misclassification")
        
        if contradictions:
            txn_id = result.transaction_id or f"index-{i}"
            error_msg = f"Transaction {txn_id}: {'; '.join(contradictions)}"
            errors.append(error_msg)
            logger.debug(f"Consistency check failed for {txn_id}: {contradictions}")
    
    return errors


def _classify_batch_internal(
    transactions: List[Dict[str, Any]],
    temperature: float = 0.1,
    enhanced_prompt: str = None
) -> List[OffshoreRiskResponse]:
    """
    Internal function to classify a batch of transactions for offshore risk using LLM.
    
    Args:
        transactions: List of normalized transaction dictionaries
        temperature: LLM temperature (0.0-1.0)
        enhanced_prompt: Additional prompt instructions for retries
    
    Returns:
        List of OffshoreRiskResponse objects
    """
    if not transactions:
        return []
        
    logger.info(f"Classifying batch of {len(transactions)} transactions")
    
    try:
        # Build prompts
        system_prompt = build_system_prompt()
        
        # Add enhanced prompt if this is a retry
        if enhanced_prompt:
            system_prompt = f"{system_prompt}\n\n{enhanced_prompt}"
        
        user_message = build_user_message(transactions)
        
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
        batch_result = BatchOffshoreRiskResponse(**llm_response)
        
        # Check for consistency issues (contradictory reasoning)
        consistency_errors = _check_consistency(batch_result.results)
        if consistency_errors:
            # If there are consistency errors, raise ValidationError to trigger retry
            error_details = "; ".join(consistency_errors)
            logger.warning(f"Consistency check failed: {error_details}")
            raise ValidationError.from_exception_data(
                "consistency_error",
                [{"type": "consistency_error", "loc": (), "msg": error_details, "input": None}]
            )
        
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
        logger.error(f"LLM batch response validation failed: {e}")
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


def classify_batch(
    transactions: List[Dict[str, Any]],
    temperature: float = 0.1
) -> List[OffshoreRiskResponse]:
    """
    Classify a batch of transactions with retry logic for validation errors.
    
    Args:
        transactions: List of normalized transaction dictionaries
        temperature: LLM temperature (0.0-1.0)
    
    Returns:
        List of OffshoreRiskResponse objects
    """
    if not transactions:
        return []
    
    max_retries = settings.llm_max_retries
    retry_temperature = settings.llm_retry_temperature
    last_validation_error = None
    
    for attempt in range(max_retries):
        try:
            # Use slightly higher temperature for retries
            current_temp = temperature if attempt == 0 else retry_temperature
            
            # Build enhanced prompt for retries
            enhanced_prompt = None
            if attempt > 0:
                enhanced_prompt = (
                    f"**RETRY ATTEMPT {attempt}/{max_retries - 1}**\n\n"
                    "The previous response had validation errors. Please pay special attention to:\n"
                    "1. The 'sources' field MUST be an empty array [] if no web sources were used, NEVER null or missing\n"
                    "2. ALL required fields must be present for each transaction\n"
                    "3. Ensure your classification label matches your reasoning explanation\n"
                    "4. Do NOT put contradiction warnings in llm_error field\n"
                    "5. If entity name contains offshore keywords but address is non-offshore, classify as OFFSHORE_NO\n"
                    "6. Follow the exact JSON schema structure provided"
                )
                
                # Add specific error details if available
                if last_validation_error:
                    enhanced_prompt += f"\n\nPrevious error details: {last_validation_error}"
            
            # Try classification
            logger.info(f"Classification attempt {attempt + 1}/{max_retries}")
            results = _classify_batch_internal(
                transactions=transactions,
                temperature=current_temp,
                enhanced_prompt=enhanced_prompt
            )
            
            logger.info(f"Successfully classified batch on attempt {attempt + 1}")
            return results
            
        except ValidationError as e:
            logger.warning(f"Validation error on attempt {attempt + 1}/{max_retries}: {e}")
            last_validation_error = str(e)
            
            # If this was the last attempt, return error responses
            if attempt == max_retries - 1:
                logger.error(f"All {max_retries} retry attempts failed with validation errors")
                error_msg = f"Validation error after {max_retries} attempts: {str(e)}"
                return [create_error_response(t, error_msg) for t in transactions]
            
            # Otherwise, log and continue to next retry
            logger.info(f"Retrying with enhanced prompt (attempt {attempt + 2}/{max_retries})")
            
        except LLMError as e:
            # Don't retry on LLM connection errors
            logger.error(f"LLM error (not retrying): {e}")
            return [create_error_response(t, f"LLM error: {e.message}") for t in transactions]
            
        except Exception as e:
            # Don't retry on unexpected errors
            logger.error(f"Unexpected error (not retrying): {e}")
            return [create_error_response(t, f"Unexpected error: {str(e)}") for t in transactions]
    
    # Fallback (should never reach here)
    logger.error("Retry loop completed without returning results")
    return [create_error_response(t, "Retry loop exhausted") for t in transactions]
