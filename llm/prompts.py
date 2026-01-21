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

**Address Evaluation Rules:**

**For INCOMING transactions**, you must evaluate UP TO THREE separate addresses:
1. **Payer Address** - The physical/business address of the payer entity
2. **Payer Bank Address** - The complete address of the payer's servicing bank
3. **Correspondent Bank Address** - If present, the address of the correspondent bank (must be evaluated separately)

**For OUTGOING transactions**, you must evaluate TWO separate addresses:
1. **Recipient Address** - The physical/business address of the recipient entity
2. **Recipient Bank Address** - The complete address of the recipient's servicing bank

Apply the MANDATORY ANALYSIS PROCESS below to ALL addresses independently. If ANY address resolves to an offshore jurisdiction from the list, the transaction must be labeled OFFSHORE_YES.

**Important:** Bank addresses are provided as multiple fields that form ONE complete address:
- Bank Address (street/location details) + City + Bank Country + Country Code → combine these into one complete address for analysis
- Example: "452 FIFTH AVENUE" + "NEW YORK,NY" + "СОЕДИНЕННЫЕ ШТАТЫ АМЕРИКИ" + "US" → "452 FIFTH AVENUE, NEW YORK,NY, USA"

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

1. **OFFSHORE_YES**:
   - The resolved **Country** OR **State/Province** matches an entry in the Offshore List.

2. **OFFSHORE_NO**:
   - The resolved location (City, State, Country) is **DEFINITELY NOT** in the Offshore List.

3. **OFFSHORE_SUSPECT**:
   - Address is MISSING or EMPTY.
   - OR Web Search failed to resolve the location confidently.

**IMPORTANT RULES:**

1. **STRICT LIST ADHERENCE**: Use ONLY the provided list.
2. **CONSISTENCY**: Reuse reasoning for identical entities.
3. **LANGUAGE**: Match English search results to Russian list names. Write `reasoning_short_ru` in Russian.
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
            counterparty_address = txn.get("payer_address", "")
            client_name = txn.get("beneficiary_name", "")
            bank = txn.get("payer_bank", "")
            swift = txn.get("payer_bank_swift", "")
            counterparty_country = txn.get("payer_country", "")
            country_code = txn.get("country_code", "")
            
            # Combine payer address
            payer_address_parts = [
                counterparty_address,
                counterparty_country
            ]
            payer_address_complete = ", ".join([p for p in payer_address_parts if p])
            
            # Combine bank address
            bank_address_parts = [
                txn.get("payer_bank_address", ""),
                txn.get("city", ""),
                txn.get("bank_country", ""),
                country_code
            ]
            bank_address_complete = ", ".join([p for p in bank_address_parts if p])
            
            # Correspondent bank info
            correspondent_name = txn.get("payer_correspondent_name", "")
            correspondent_address = txn.get("payer_correspondent_address", "")
            correspondent_swift = txn.get("payer_correspondent_swift", "")
            
            # Intermediary banks (context only)
            intermediary_banks = [
                txn.get("intermediary_bank_1", ""),
                txn.get("intermediary_bank_2", ""),
                txn.get("intermediary_bank_3", "")
            ]
            intermediaries_text = " | ".join([ib for ib in intermediary_banks if ib])
            
            payment_details = txn.get("payment_details", "")
        else:  # outgoing
            counterparty = txn.get("recipient", "")
            counterparty_address = txn.get("recipient_address", "")
            counterparty_country = txn.get("recipient_country", "")
            country_code = txn.get("country_code", "")
            client_name = txn.get("payer_name", "")
            bank = txn.get("recipient_bank", "")
            swift = txn.get("recipient_bank_swift", "")
            bank_address_parts = [
                txn.get("recipient_bank_address", ""),
                txn.get("city", ""),
                txn.get("bank_country", "")
            ]
            bank_address_complete = ", ".join([p for p in bank_address_parts if p])
            payment_details = txn.get("payment_details", "")
        
        # Build transaction block
        txn_block = [f"Transaction #{i} (ID: {txn_id}, Direction: {direction}):"]
        
        if counterparty:
            label = "Payer Name" if direction == "incoming" else "Recipient Name"
            txn_block.append(f"- {label}: {counterparty}")
        
        if direction == "incoming" and payer_address_complete:
            txn_block.append(f"- Payer Address (Complete): {payer_address_complete}")
        
        if direction == "outgoing" and counterparty_address:
            txn_block.append(f"- Recipient Address (Complete): {counterparty_address}, {counterparty_country} ({country_code})")

        if client_category != "Физ" and client_name:
            label = "Beneficiary (Our Client)" if direction == "incoming" else "Payer (Our Client)"
            txn_block.append(f"- {label}: {client_name}")
        
        bank_label = "Payer Bank" if direction == "incoming" else "Recipient Bank"
        bank_address_label = "Payer Bank Address (Complete)" if direction == "incoming" else "Recipient Bank Address (Complete)"
        
        txn_block.extend([
            f"- {bank_label}: {bank}",
            f"- {bank_label} SWIFT: {swift}",
            f"- {bank_address_label}: {bank_address_complete}"
        ])
        
        # Add correspondent bank for incoming (evaluated as third address)
        if direction == "incoming" and correspondent_name:
            txn_block.append(f"- Correspondent Bank: {correspondent_name}")
            txn_block.append(f"- Correspondent Bank SWIFT: {correspondent_swift}")
            txn_block.append(f"- Correspondent Bank Address (Evaluate separately): {correspondent_address}")
        
        # Add intermediary banks for incoming (context only)
        if direction == "incoming" and intermediaries_text:
            txn_block.append(f"- Intermediary Banks (Context): {intermediaries_text}")
        
        # Add payment details for both directions
        if direction == "incoming" and payment_details:
            txn_block.append(f"- Payment Details: {payment_details}")
        
        if direction == "outgoing" and payment_details:
            txn_block.append(f"- Payment Details: {payment_details}")
            
        message_parts.append("\n".join(txn_block))
        message_parts.append("")  # Empty line between transactions
        
    return "\n".join(message_parts)
