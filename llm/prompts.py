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

Your task is to analyze a BATCH of banking transactions and determine if they involve offshore jurisdictions.

**OFFSHORE JURISDICTIONS LIST (Government of Kazakhstan):**
The following list is the **ONLY** source of truth for offshore classification.
{offshore_list}

**MANDATORY ANALYSIS PROCESS (Chain of Thought):**

For EACH transaction, you MUST follow these steps sequentially:

1. **DECONSTRUCT & EXTRACT**: 
   - Break down the Payer/Recipient Address field into components: Street Name, City, State/Province/Region, Country.
   - **CRITICAL**: Pay attention to *every* part of the address string. 
     - *Example 1*: "123 Main St, Sheridan" -> City: Sheridan, State: Wyoming (WY), Country: USA.
     - *Example 2*: "NO. 109, HONG KONG EAST ROAD, QINGDAO" -> Street: Hong Kong East Rd, City: Qingdao, Country: China. (Do NOT confuse street names with countries).

2. **RESOLVE LOCATION (Web Search)**: 
   - **Goal**: Determine the specific **Administrative Division** (State/Province) and Country for the address.
   - **MANDATORY**: If the country is large (e.g., USA, UK, China, Malaysia, Spain, France), you **MUST** identify the specific State/Province/Territory.
   - **Query**: Ask "What state is [City] in?" or "Is [City] in an offshore jurisdiction?".
   - **Hidden Offshore Check**: Be vigilant for cities in offshore states (e.g., Sheridan/Cheyenne -> Wyoming (USA), Douglas -> Isle of Man).

3. **COMPARE WITH LIST**: 
   - Check if the *resolved* Country OR the *resolved* State/Province appears in the **OFFSHORE JURISDICTIONS LIST**.
   - The comparison must be exact or linguistically equivalent.
   - **Logic**: If the State/Province is on the list (e.g., "Wyoming (USA)"), it is a MATCH, even if the Country (USA) is not.

4. **CLASSIFY**: Assign the final label based ONLY on the comparison in Step 3.

**CLASSIFICATION LOGIC:**

1. **OFFSHORE_YES** (Confidence: 100%):
   - The resolved **Country** OR **State/Province** matches an entry in the Offshore List.
   - OR the **Bank** is located in a listed jurisdiction.
   - **Reasoning**: "Address resolved to [City, State], which is in the offshore list."

2. **OFFSHORE_NO** (Confidence: 100%):
   - The resolved location (City, State, Country) is **DEFINITELY NOT** in the Offshore List.
   - **Reasoning**: "Address resolved to [City, State, Country], which is NOT in the offshore list."

3. **OFFSHORE_SUSPECT**:
   - Address is MISSING or EMPTY.
   - OR Web Search failed to resolve the location confidently.
   - **Reasoning**: "Address is missing" or "Could not determine location of [City]."

**IMPORTANT RULES:**

1. **STRICT LIST ADHERENCE**: Use ONLY the provided list.
2. **CONSISTENCY**: Reuse reasoning for identical entities.
3. **NO LINKS**: Do NOT include URLs.
4. **LANGUAGE**: Match English search results to Russian list names.

**Output Format**:
- Return a JSON object with a `results` array.
- Each item must correspond to one transaction.
- Maintain the same `transaction_id`.
- `reasoning_short_ru` must be in Russian.
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
