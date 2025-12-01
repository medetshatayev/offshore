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

**ANALYSIS RULES:**

1. **Database is Truth**: The list above is the ONLY source of truth. If a country/territory is in this list, it is offshore.

2. **Bank Address & SWIFT**: 
   - Check the bank address and SWIFT code country.
   - If the bank is located in a listed jurisdiction, it is OFFSHORE_YES.
   - Use the address as the primary location indicator.

3. **Counterparty (Payer/Recipient) Checks**:
   - CRITICAL: You MUST check the Payer/Recipient name and address field for offshore jurisdictions.
   - Look for country names or codes (e.g., "HK", "Hong Kong", "BVI", "Virgin Islands") within the address text.
   - **Example**: If the address contains "Hong Kong" or "HK", but the country is listed as "China", it IS offshore (if Hong Kong is in the list). Treat specific regions like Hong Kong or Macau as distinct from their parent countries.

4. **Special Cases**:
   - Some territories (e.g., Wyoming US, Labuan Malaysia, Canary Islands Spain) are offshore even if their parent country is not.
   - If the list contains specific regions (e.g. "Вайоминг (США)", "Малайзия (Лабуан)"), check for these specific locations.

5. **Classification Labels**:
   - **OFFSHORE_YES**: Bank/Entity is clearly located in a listed offshore jurisdiction.
   - **OFFSHORE_SUSPECT**: Indicators suggest possible offshore involvement but evidence is ambiguous.
   - **OFFSHORE_NO**: Bank/Entity is clearly NOT in a listed offshore jurisdiction.

6. **Web Search**:
   - Use `web_search` for ambiguous cases, unknown banks, or to verify specific locations.
   - Cite sources in the `sources` array.

7. **Output Format**:
   - You must return a JSON object with a `results` array.
   - Each item in `results` must correspond to one transaction in the input.
   - Maintain the same `transaction_id` for each result.

**IMPORTANT**:
- Process ALL transactions in the batch.
- Provide concise Russian reasoning (1-2 sentences) for each.
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
            bank = txn.get("payer_bank", "")
            swift = txn.get("payer_bank_swift", "")
            bank_address = txn.get("payer_bank_address", "")
            country = txn.get("payer_country", "")
        else:  # outgoing
            counterparty = txn.get("recipient", "")
            bank = txn.get("recipient_bank", "")
            swift = txn.get("recipient_bank_swift", "")
            bank_address = txn.get("recipient_bank_address", "")
            country = txn.get("recipient_country", "")
        
        city = txn.get("city", "")
        country_code = txn.get("country_code", "")
        
        # Build transaction block
        txn_block = [f"Transaction #{i} (ID: {txn_id}, Direction: {direction}):"]
        
        if client_category != "Физ" and counterparty:
            label = "Payer" if direction == "incoming" else "Recipient"
            txn_block.append(f"- {label}: {counterparty}")
        
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
