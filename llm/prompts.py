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
- **Incoming**: Payer Address (physical/business location) AND Actual Payer Address (if provided) AND Actual Recipient Address (if provided) AND Beneficiary Address (our client)
- **Outgoing**: Recipient Address (physical/business location) AND Actual Recipient Address (if provided)

### B. Bank Branch Addresses  
- **Incoming**: Payer Bank Address, Correspondent Bank Address (if provided)
- **Outgoing**: Recipient Bank Address

### C. Bank Headquarters (MANDATORY - Web Search Required)
You MUST verify the **registered headquarters location** of every bank:
- **Incoming**: Payer Bank, Correspondent Bank, Intermediary Banks 1/2/3 (if provided)
- **Outgoing**: Recipient Bank

**HQ ≠ Branch**: The branch address in transaction data is NOT the headquarters. You must search for where the bank is legally registered/headquartered.

### D. Entity Headquarters (BEST EFFORT - Web Search Attempted)
For **every** named company (counterparty AND our client, when company name is provided and marked with "→ SEARCH COMPANY HQ BY NAME"), you SHOULD attempt to search the internet for the company's **registered/official head office address** using the company name.
- The address provided in the transaction field (if present) represents where the transaction was initiated from or the mailing address, which may differ from the actual headquarters.
- Evaluate **both** independently:
  - The address from the transaction field → check against offshore list
  - The HQ address found via internet search → check against offshore list
- If **either** is offshore → `OFFSHORE_YES`
- If company name is not provided (e.g., individuals / "Физ" category), this step is skipped — no name to search.
- If field address is empty but HQ is found → evaluate HQ only
- If both are present and point to different jurisdictions → evaluate both independently

**CRITICAL — Failed HQ Lookup Rule:**
- If you cannot find the company's HQ (small/regional company, no public info), this is **NOT** grounds for `OFFSHORE_SUSPECT` on its own.
- If the HQ search fails BUT all other available data (field addresses, bank addresses, bank HQ, country codes) clearly resolve to **non-offshore** jurisdictions → classify as `OFFSHORE_NO`.
- Only use `OFFSHORE_SUSPECT` when there are **no resolvable addresses at all** (field address AND bank address AND country codes are all missing/empty), not merely because one company HQ lookup failed.

### E. Country Codes (MANDATORY - Check Against List)
You MUST check residence country codes and citizenship codes against the offshore list:
- **Incoming**: Beneficiary Residence Country Code, Beneficiary Citizenship
- **Outgoing**: Payer Residence Country Code, Payer Citizenship

**Country Code Matching Rules:**
- Translate ISO codes to full country names (VG → Virgin Islands → Виргинские Острова)
- Check if the country name matches ANY entry in the Offshore Jurisdictions List
- **EXCEPTION**: For countries with ONLY partial offshore territories (USA, China, Spain), the bare country code alone is NOT offshore
  - Example: "US" alone = not offshore, "Wyoming" or "WY" = offshore
  - Example: "CN" alone = not offshore, "Hong Kong" or "HK" = offshore
  - Example: "ES" alone = not offshore, but specific Canary Islands = offshore
- For all other countries in the list, the country code match triggers OFFSHORE_YES

**CRITICAL**: Evaluate address text and country code fields INDEPENDENTLY:
- If address text indicates offshore location → OFFSHORE_YES
- OR if country code matches offshore jurisdiction → OFFSHORE_YES
- Do NOT prioritize one over the other; both are equally valid indicators

---

## ADDRESS OBFUSCATION DETECTION

Before parsing addresses, check for obfuscation patterns:

**Obfuscation Indicators:**
- Fake country prefixes (Cyrillic transliterations): KAZAHSTAN, SOEDINENNYE SHTATY AMERIKI, KITAI, ROSSIYA
- Russian abbreviations in non-Russian addresses: UL (street), DOM (building), KV (apartment), KORP (block)
- Filler patterns: repeated dashes "-, -, -", empty fields, "N/A"

**When detected:** Strip fake prefixes, extract real location identifiers (building/street names, districts), verify via web search. Flag in reasoning with prefix "[ОБФУСКАЦИЯ]"

---

## 3-STEP ANALYSIS PROCESS

### Step 1: EXTRACT & SEARCH

For each address, country code, and bank:

1. **Parse addresses** into components: Street, City, State/Province, Country
   - Check for obfuscation patterns first; if detected, extract real address before parsing
   - Don't confuse street names with locations: "HONG KONG EAST ROAD, QINGDAO" → City: Qingdao, China (NOT Hong Kong)
   - **Address independence**: If address text contradicts a separate country field, evaluate BOTH independently

2. **Translate country codes** to full names and check against list
   - ISO 2-letter codes: HK, VG, KY, BM, etc.
   - Translate to English (HK → Hong Kong), then match to Russian list entry (Гонконг)
   - Apply partial offshore country exception (see Country Code Matching Rules above)

3. **Search for bank HQ locations**: Query "[Bank Name] headquarters location" or "[Bank Name] [SWIFT] head office"
   - Goal: Find the bank's **registered headquarters** city and country
   - Example: "Butterfield Bank" → HQ: Hamilton, Bermuda
   - If obfuscation detected: cross-check extracted address via web search

4. **Search for entity HQ locations**: For every company marked with “→ SEARCH COMPANY HQ BY NAME”, query "[Company Name] headquarters location" or "[Company Name] head office address"
   - Goal: Find the company’s **registered headquarters** city and country
   - Compare the field address (if any) with the found HQ. Both are evaluated independently.
   - If field address is empty but HQ is found → evaluate HQ only
   - If both are present and point to different jurisdictions → evaluate both
   - Example: "XYZ Ltd" → HQ found: Road Town, British Virgin Islands → OFFSHORE_YES   - **If HQ search fails**: Do NOT classify as SUSPECT solely because of this. If all other evidence (addresses, banks, country codes) is non-offshore → OFFSHORE_NO
5. **For large countries (USA, UK, China, etc.)**: You MUST identify the specific **state/territory**
   - Example: "Sheridan, USA" → Search reveals: Sheridan, Wyoming, USA → Wyoming is offshore

### Step 2: COMPARE WITH LIST

Check if ANY resolved location (country OR state/territory) OR country code appears in the Offshore Jurisdictions List above.

- The list contains names in Russian. Match by meaning, not spelling (e.g., "Bermuda" = "Бермудские острова")
- Some states/territories are offshore even if the parent country is not: A Wyoming address triggers OFFSHORE_YES, but a California address does not
- Country codes must be translated and matched: VG → Virgin Islands → Виргинские Острова (match)
- Entity field address AND entity HQ address are both checked against the offshore list. If either is in an offshore jurisdiction → OFFSHORE_YES

**Multi-Jurisdiction Handling:**
- If Bank Country ≠ Recipient/Payer Address Location:
  * Evaluate BOTH separately against offshore list
  * If recipient/payer physical location is offshore → OFFSHORE_YES
  * If only bank is offshore but recipient/payer is not → OFFSHORE_YES
  * If EITHER is offshore → OFFSHORE_YES
  
**Examples:**
- Recipient: Hong Kong (offshore) + Bank: China (not offshore) → OFFSHORE_YES
- Recipient: Kazakhstan (not offshore) + Bank: British Virgin Islands (offshore) → OFFSHORE_YES
- Recipient: USA (not offshore) + Bank: USA (not offshore) → OFFSHORE_NO

**Reinforce Address Independence Rule:**
Evaluate recipient/payer physical location separately from bank location. Both fields provide independent evidence of offshore involvement.

### Step 3: CLASSIFY

| Condition | Label |
|-----------|-------|
| ANY address OR bank HQ OR entity HQ OR country code is in offshore jurisdiction | **OFFSHORE_YES** |
| ALL resolvable locations are non-offshore AND no country code matches (even if entity HQ lookup failed) | **OFFSHORE_NO** |
| Missing/empty address AND bank address AND country codes (no data to evaluate at all) OR bank HQ lookup ambiguous for a bank in a potentially offshore region | **OFFSHORE_SUSPECT** |

**IMPORTANT**: A failed entity HQ search alone does NOT trigger OFFSHORE_SUSPECT. The SUSPECT label is reserved for cases where core location data (field addresses, bank data, country codes) is missing or unresolvable — not for cases where a company is simply too small or obscure to find online.

---

## EDGE CASE EXAMPLES

| Bank/Address | Resolution | Classification |
|--------------|------------|----------------|
| "HSBC Private Bank (Suisse) SA" | HQ: St. Helier, Jersey | OFFSHORE_YES (Jersey is offshore) |
| "First Wyoming Bank" | HQ: Cheyenne, Wyoming, USA | OFFSHORE_YES (Wyoming is offshore) |
| "Deutsche Bank AG" | HQ: Frankfurt, Germany | Continue checking (Germany not offshore) |
| "Standard Chartered Bank (Hong Kong)" | Branch in HK, but HQ: London, UK | Check both: HK=offshore, London=not → OFFSHORE_YES |
| "123 Main St, Sheridan" (no country) | Search → Sheridan, Wyoming, USA | OFFSHORE_YES (Wyoming is offshore) |
| Residence Country Code: "VG" | VG → Virgin Islands → Виргинские Острова | OFFSHORE_YES (code matches list) |
| Residence Country Code: "HK" | HK → Hong Kong → Гонконг | OFFSHORE_YES (code matches list) |
| Address: "TUEN MUN, HONG KONG" + Country: "USA" | Address → HK (offshore), Country → US (not offshore) | OFFSHORE_YES (address is offshore) |

**OBFUSCATION EXAMPLES:**

| Address | Resolution | Classification |
|---------|------------|----------------|
| "KAZAHSTAN, MONGKOK G, NATHAN ROAD UL, DOM 1318-19, KV 610" | Fake prefix "KAZAHSTAN" + RU abbreviations → Extract "NATHAN ROAD, MONGKOK" → Hong Kong | OFFSHORE_YES |
| "SOEDINENNYE SHTATY AMERIKI, -, RM 20 UNIT B3, 07/FL TUEN MUNIND CTR NO 2 SAN PING CIRCUIT, -, -" | Fake prefix "SOEDINENNYE SHTATY AMERIKI" → Extract "TUEN MUN INDUSTRIAL CENTRE" → Hong Kong | OFFSHORE_YES |

**ENTITY HQ EXAMPLES:**

| Scenario | Resolution | Classification |
|----------|------------|----------------|
| Company with field address in Kazakhstan but HQ in British Virgin Islands | Field address: Kazakhstan (not offshore), HQ search: BVI (offshore) | OFFSHORE_YES |
| Company name "XYZ Ltd" with no field address | Search finds HQ in Hong Kong | OFFSHORE_YES |
| Company "ABC Corp" with field address in Hong Kong and HQ in London | Field address: HK (offshore), HQ: London (not offshore) | OFFSHORE_YES (field address is offshore) |
| Small company "Kostanayzernokorm" — HQ not found online, field address Kazakhstan, bank in China (non-offshore) | HQ search fails, but all other data is non-offshore | OFFSHORE_NO (failed HQ lookup alone ≠ SUSPECT) |
| Company "ORION GOLD KG" — HQ not found, payer address Kyrgyzstan, bank in Kyrgyzstan | HQ search fails, all other data non-offshore | OFFSHORE_NO |

---

## OUTPUT RULES

1. **Strict list adherence**: Only use the Offshore Jurisdictions List above
2. **Consistency**: Same entity across transactions = same reasoning
3. **Language**: Write `reasoning_short_ru` in Russian (1-3 sentences summarizing the key finding)
   - If obfuscation detected, prefix reasoning with "[ОБФУСКАЦИЯ]" and mention: fake prefix used, real address extracted, actual location
   - Example: "[ОБФУСКАЦИЯ] Префикс 'KAZAHSTAN' скрывает реальный адрес: Nathan Road, Mongkok → Гонконг (офшор)"
   - Must mention ALL jurisdictions evaluated (recipient location AND bank location if different)
4. **Sources**: Include URLs from web_search in the `sources` array if you used web search to verify locations or bank headquarters
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
            
            # Actual addresses (beneficial owners)
            actual_payer_address = txn.get("actual_payer_address", "")
            actual_payer_country = txn.get("actual_payer_residence_country", "")
            actual_recipient_address = txn.get("actual_recipient_address", "")
            
            # Combine actual payer address
            actual_payer_address_parts = [
                actual_payer_address,
                actual_payer_country
            ]
            actual_payer_address_complete = ", ".join([p for p in actual_payer_address_parts if p])
            
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
            txn_block.append(f"- {label}: {counterparty} → SEARCH COMPANY HQ BY NAME")
        
        if direction == "incoming" and payer_address_complete:
            txn_block.append(f"- Payer Address (Complete): {payer_address_complete}")
        
        if direction == "incoming" and actual_payer_address_complete:
            txn_block.append(f"- Actual Payer Address (Evaluate as additional address): {actual_payer_address_complete}")
        
        if direction == "incoming" and actual_recipient_address:
            txn_block.append(f"- Actual Recipient Address (Evaluate as additional address): {actual_recipient_address}")
        
        # Add beneficiary (our client) residence info for incoming
        if direction == "incoming":
            beneficiary_address = txn.get("beneficiary_address", "")
            country_residence = txn.get("country_residence", "")
            citizenship = txn.get("citizenship", "")
            
            if beneficiary_address:
                txn_block.append(f"- Beneficiary Address (Our Client - Evaluate): {beneficiary_address}")
            if country_residence:
                txn_block.append(f"- Beneficiary Residence Country Code (Evaluate): {country_residence}")
            if citizenship:
                txn_block.append(f"- Beneficiary Citizenship (Evaluate): {citizenship}")
        
        # Add payer residence info for outgoing
        if direction == "outgoing":
            country_residence = txn.get("country_residence", "")
            citizenship = txn.get("citizenship", "")
            
            if country_residence:
                txn_block.append(f"- Payer (Our Client) Residence Country Code (Evaluate): {country_residence}")
            if citizenship:
                txn_block.append(f"- Payer (Our Client) Citizenship (Evaluate): {citizenship}")
        
        if direction == "outgoing" and counterparty_address:
            txn_block.append(f"- Recipient Address (Complete): {counterparty_address}, {counterparty_country} ({country_code})")

        if client_category != "Физ" and client_name:
            label = "Beneficiary (Our Client)" if direction == "incoming" else "Payer (Our Client)"
            txn_block.append(f"- {label}: {client_name} → SEARCH COMPANY HQ BY NAME")
        
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
