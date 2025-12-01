"""
System and user prompts for LLM offshore risk classification.
Loads offshore jurisdictions from SQLite database and builds batch prompts.
"""
from typing import Any, Dict, List

from core.db import get_db
from core.logger import setup_logger

logger = setup_logger(__name__)


def load_offshore_list() -> str:
    """
    Load offshore countries list from SQLite database.
    
    Returns:
        Formatted list as string for system prompt
    """
    try:
        db = get_db()
        countries = db.get_all_countries()
        
        if not countries:
            logger.warning("No countries found in database")
            return "No offshore countries loaded."
        
        logger.info(f"Loaded {len(countries)} offshore countries from DB")
        return "\n".join([f"- {country}" for country in countries])
    
    except Exception as e:
        logger.error(f"Failed to load offshore list: {e}", exc_info=True)
        return "Error loading offshore list."


def build_system_prompt() -> str:
    """
    Build the system prompt with embedded offshore jurisdictions list.
    
    Returns:
        Complete system prompt string
    """
    offshore_list = load_offshore_list()
    
    prompt = f"""You are an expert financial compliance analyst for a Kazakhstani bank.

Your task is to analyze a BATCH of banking transactions and determine if they involve offshore jurisdictions or present offshore-related risks.

**OFFSHORE JURISDICTIONS LIST (Government of Kazakhstan):**
Any transaction involving these countries/territories should be flagged as offshore:

{offshore_list}

**MANDATORY ANALYSIS PROCESS (Chain of Thought):**

For EACH transaction, you MUST follow these steps sequentially:

1. **EXTRACT ADDRESSES**: Identify the Payer/Recipient address and Bank address.

2. **WEB SEARCH (MANDATORY)**: 
   - You **MUST** perform a `web_search` for the specific City/Region/Address of the Payer/Recipient.
   - **Goal**: Determine the specific Administrative Division (State, Province, Territory) and its offshore status.
   - **Queries**: Use queries like "Is [City, Address] in an offshore jurisdiction?", "What state is [City] in?", "Is [Bank Name] an offshore bank?".
   - **Hidden Offshore Check**: Specifically check if the location is a known offshore haven within a larger country (e.g., Wyoming/Delaware in USA, Labuan in Malaysia, Canary Islands in Spain).

3. **COMPARE**: Compare the verified location (City, State, Country) against the **OFFSHORE JURISDICTIONS LIST**.

4. **CLASSIFY**: Assign the final label based on the verified location.

**ANALYSIS RULES:**

1. **Database is Truth**: The list above is the ONLY source of truth. If a verified location is in this list, it is OFFSHORE_YES.

2. **Trust but Verify**: 
   - Do NOT rely solely on the provided country code (e.g., "CN" might contain "HK" address, "US" might contain "Wyoming").
   - **Example**: If address is "Sheridan, United States", your web search must confirm it is in "Wyoming". Since Wyoming is offshore (if listed), classify as OFFSHORE_YES.

3. **Bank Address & SWIFT**: 
   - Check the bank address and SWIFT code country.
   - If the bank is located in a listed jurisdiction, it is OFFSHORE_YES.

4. **Classification Labels**:
   - **OFFSHORE_YES**: Bank/Entity is clearly located in a listed offshore jurisdiction (address verified by search).
   - **OFFSHORE_SUSPECT**: Search is inconclusive, but indicators suggest possible offshore involvement.
   - **OFFSHORE_NO**: Bank/Entity is clearly NOT in a listed offshore jurisdiction.

5. **Output Format**:
   - Return a JSON object with a `results` array.
   - Each item must correspond to one transaction.
   - Maintain the same `transaction_id`.

**IMPORTANT**:
- Process ALL transactions.
- Your `reasoning_short_ru` MUST mention the web search result (e.g., "Web search confirmed address is in Wyoming...").
"""
    return prompt


def build_user_message(transactions: List[Dict[str, Any]]) -> str:
    """
    Build user message with a batch of transactions.
    
    Args:
        transactions: List of normalized transaction dictionaries
    
    Returns:
        Formatted user message string
    """
    message_parts = ["Here is a batch of transactions to classify:\n"]
    
    for i, txn in enumerate(transactions, 1):
        txn_id = txn.get("id", "unknown")
        direction = txn.get("direction", "unknown")
        client_category = txn.get("client_category", "")
        
        # Extract fields
        if direction == "incoming":
            counterparty = txn.get("payer", "")
            client_name = txn.get("beneficiary_name", "")
            bank = txn.get("payer_bank", "")
            swift = txn.get("payer_bank_swift", "")
            bank_address = txn.get("payer_bank_address", "")
            country = txn.get("payer_country", "")
        else:  # outgoing
            counterparty = txn.get("recipient", "")
            client_name = txn.get("payer_name", "")
            bank = txn.get("recipient_bank", "")
            swift = txn.get("recipient_bank_swift", "")
            bank_address = txn.get("recipient_bank_address", "")
            country = txn.get("recipient_country", "")
        
        city = txn.get("city", "")
        country_code = txn.get("country_code", "")
        
        # Build transaction block
        txn_block = [f"Transaction #{i} (ID: {txn_id}, Direction: {direction}):"]
        
        if counterparty:
            label = "Payer" if direction == "incoming" else "Recipient"
            txn_block.append(f"- {label}: {counterparty}")

        if client_category != "Физ" and client_name:
            label = "Beneficiary (Our Client)" if direction == "incoming" else "Payer (Our Client)"
            txn_block.append(f"- {label}: {client_name}")
        
        txn_block.extend([
            f"- Bank: {bank}",
            f"- SWIFT: {swift}",
            f"- Address: {bank_address}",
            f"- City: {city}",
            f"- Country: {country} ({country_code})"
        ])
        
        if direction == "outgoing":
            details = txn.get("payment_details", "")
            txn_block.append(f"- Details: {details}")
            
        message_parts.append("\n".join(txn_block))
        message_parts.append("")  # Empty line between transactions
        
    return "\n".join(message_parts)
