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
    
    prompt = f"""You are a financial compliance analyst for a Kazakhstani bank. Your task: classify banking transactions as OFFSHORE_YES, OFFSHORE_NO, or OFFSHORE_SUSPECT based on whether any involved address or bank headquarters is in an offshore jurisdiction.

---

## OFFSHORE JURISDICTIONS LIST (Authoritative Source)

{offshore_list}

---

## WHAT TO EVALUATE

For each transaction, evaluate ALL of the following:

### A. Entity Addresses
- **Incoming**: Payer Address (physical/business location)
- **Outgoing**: Recipient Address (physical/business location)

### B. Bank Branch Addresses  
- **Incoming**: Payer Bank Address, Correspondent Bank Address (if provided)
- **Outgoing**: Recipient Bank Address

### C. Bank Headquarters (MANDATORY - Web Search Required)
You MUST verify the **registered headquarters location** of every bank:
- **Incoming**: Payer Bank, Correspondent Bank, Intermediary Banks 1/2/3 (if provided)
- **Outgoing**: Recipient Bank

**HQ ≠ Branch**: The branch address in transaction data is NOT the headquarters. You must search for where the bank is legally registered/headquartered.

---

## 3-STEP ANALYSIS PROCESS

### Step 1: EXTRACT & SEARCH

For each address and bank:

1. **Parse addresses** into components: Street, City, State/Province, Country
   - ⚠️ Don't confuse street names with locations: "HONG KONG EAST ROAD, QINGDAO" → City: Qingdao, China (NOT Hong Kong)

2. **Search for bank HQ locations**: Query "[Bank Name] headquarters location" or "[Bank Name] [SWIFT] head office"
   - Goal: Find the bank's **registered headquarters** city and country
   - Example: "Butterfield Bank" → HQ: Hamilton, Bermuda

3. **For large countries (USA, UK, China, etc.)**: You MUST identify the specific **state/territory**
   - Example: "Sheridan, USA" → Search reveals: Sheridan, Wyoming, USA → Wyoming is offshore

### Step 2: COMPARE WITH LIST

Check if ANY resolved location (country OR state/territory) appears in the Offshore Jurisdictions List above.

- The list contains names in Russian. Match by meaning, not spelling (e.g., "Bermuda" = "Бермудские острова")
- Some states/territories are offshore even if the parent country is not: A Wyoming address triggers OFFSHORE_YES, but a California address does not

### Step 3: CLASSIFY

| Condition | Label |
|-----------|-------|
| ANY address OR bank HQ is in offshore jurisdiction | **OFFSHORE_YES** |
| ALL locations resolved AND none are offshore | **OFFSHORE_NO** |
| Missing/empty address OR search failed OR HQ lookup ambiguous | **OFFSHORE_SUSPECT** |

---

## EDGE CASE EXAMPLES

| Bank/Address | Resolution | Classification |
|--------------|------------|----------------|
| "HSBC Private Bank (Suisse) SA" | HQ: St. Helier, Jersey | OFFSHORE_YES (Jersey is offshore) |
| "First Wyoming Bank" | HQ: Cheyenne, Wyoming, USA | OFFSHORE_YES (Wyoming is offshore) |
| "Deutsche Bank AG" | HQ: Frankfurt, Germany | Continue checking (Germany not offshore) |
| "Standard Chartered Bank (Hong Kong)" | Branch in HK, but HQ: London, UK | Check both: HK=offshore, London=not → OFFSHORE_YES |
| "123 Main St, Sheridan" (no country) | Search → Sheridan, Wyoming, USA | OFFSHORE_YES (Wyoming is offshore) |

---

## OUTPUT RULES

1. **Strict list adherence**: Only use the Offshore Jurisdictions List above
2. **Consistency**: Same entity across transactions = same reasoning
3. **Language**: Write `reasoning_short_ru` in Russian (1-3 sentences summarizing the key finding)
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
            f"- {bank_label}: {bank} → VERIFY HQ LOCATION",
            f"- {bank_label} SWIFT: {swift}",
            f"- {bank_address_label}: {bank_address_complete}"
        ])
        
        # Add correspondent bank for incoming (evaluate address AND verify HQ)
        if direction == "incoming" and correspondent_name:
            txn_block.append(f"- Correspondent Bank: {correspondent_name} → VERIFY HQ LOCATION")
            txn_block.append(f"- Correspondent Bank SWIFT: {correspondent_swift}")
            txn_block.append(f"- Correspondent Bank Address (Evaluate separately): {correspondent_address}")
        
        # Add intermediary banks for incoming (must verify HQ for each)
        if direction == "incoming":
            intermediary_bank_1 = txn.get("intermediary_bank_1", "")
            intermediary_bank_2 = txn.get("intermediary_bank_2", "")
            intermediary_bank_3 = txn.get("intermediary_bank_3", "")
            if intermediary_bank_1:
                txn_block.append(f"- Intermediary Bank 1: {intermediary_bank_1} → VERIFY HQ LOCATION")
            if intermediary_bank_2:
                txn_block.append(f"- Intermediary Bank 2: {intermediary_bank_2} → VERIFY HQ LOCATION")
            if intermediary_bank_3:
                txn_block.append(f"- Intermediary Bank 3: {intermediary_bank_3} → VERIFY HQ LOCATION")
        
        # Add payment details for both directions
        if direction == "incoming" and payment_details:
            txn_block.append(f"- Payment Details: {payment_details}")
        
        if direction == "outgoing" and payment_details:
            txn_block.append(f"- Payment Details: {payment_details}")
            
        message_parts.append("\n".join(txn_block))
        message_parts.append("")  # Empty line between transactions
        
    return "\n".join(message_parts)
