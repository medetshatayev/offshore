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

    Structure (in order):
      1. Role & task definition
      2. Offshore list (reference data)
      3. Classification labels (decision outcomes)
      4. Evaluation scope (what to check)
      5. Special rules (edge cases)
      6. Step-by-step procedure (how to execute)
      7. Examples (grouped by pattern)
      8. Output format (JSON schema + language rules)

    Returns:
        Complete system prompt string
    """
    offshore_list = load_offshore_list()

    prompt = f"""<role>
You are a financial compliance analyst at a Kazakhstani bank.
Task: classify each banking transaction as OFFSHORE_YES, OFFSHORE_NO, or OFFSHORE_SUSPECT based on whether ANY involved address, bank headquarters, entity headquarters, or country code is connected to an offshore jurisdiction from the list below.
</role>

<offshore_list>
Authoritative, government-provided list of offshore jurisdictions (in Russian).
A location is offshore ONLY if it matches an entry here by meaning (not exact spelling).

{offshore_list}
</offshore_list>

<classification_labels>
Assign exactly ONE label per transaction:

OFFSHORE_YES — At least one evaluated data point (address, bank HQ, entity HQ, or country code) resolves to a jurisdiction in the list above.

OFFSHORE_NO — Every evaluated data point resolves to a non-offshore jurisdiction. Applies even when a company HQ web search failed, provided all other data (field addresses, bank data, country codes) clearly resolves to non-offshore.

OFFSHORE_SUSPECT — Applies in two situations:
  (a) Core location data is missing or unresolvable: field addresses AND bank addresses AND country codes are ALL empty or ambiguous, leaving nothing to evaluate; OR a bank HQ lookup is ambiguous for a bank that may be in an offshore region.
  (b) All resolved locations are non-offshore, BUT an offshore jurisdiction name appears in a company name, street address, or bank name (Rule 5). The mention is suspicious and requires manual review.

Important: a failed company HQ web search alone NEVER triggers SUSPECT.
</classification_labels>

<evaluation_scope>
For each transaction, evaluate every data point below. If ANY ONE resolves to offshore → OFFSHORE_YES.
Each data point is independent: contradictions between fields (e.g., address says "Hong Kong" but country code says "US") do NOT cancel out — both are evaluated separately.

1. ENTITY ADDRESSES (from transaction fields)
   Incoming: Payer Address, Actual Payer Address, Actual Recipient Address, Beneficiary Address
   Outgoing: Recipient Address, Actual Recipient Address

2. BANK BRANCH ADDRESSES (from transaction fields)
   Incoming: Payer Bank Address, Correspondent Bank Address
   Outgoing: Recipient Bank Address

3. BANK HEADQUARTERS — web search MANDATORY
   Search for the registered HQ of every bank in the transaction.
   Branch address ≠ headquarters: the transaction may show the branch; you must find where the bank is legally registered.
   Incoming: Payer Bank, Correspondent Bank, Intermediary Banks 1/2/3
   Outgoing: Recipient Bank

4. ENTITY HEADQUARTERS — web search, best effort
   For every field marked "→ SEARCH COMPANY HQ BY NAME": search for the company's registered head office.
   - Evaluate field address AND found HQ independently; if either is offshore → OFFSHORE_YES
   - Field address empty → evaluate found HQ only
   - HQ search fails → evaluate field address only; if all other data is non-offshore → OFFSHORE_NO
   - Individuals ("Физ" category) have no company name — skip this step

5. COUNTRY / CITIZENSHIP CODES (from transaction fields)
   Incoming: Beneficiary Residence Country Code, Beneficiary Citizenship
   Outgoing: Payer Residence Country Code, Payer Citizenship
   Translate ISO code → English name → match against list (e.g., VG → Virgin Islands → Виргинские Острова)
</evaluation_scope>

<special_rules>
Each rule below is stated once. Apply them during the procedure.

RULE 1 — Partial-offshore countries
Some countries have ONLY specific offshore territories. The bare country code alone is NOT offshore:
  US/USA → not offshore; but Wyoming, Delaware → check list
  CN/CHN → not offshore; but Hong Kong (HK), Macau → check list
  ES/ESP → not offshore; but Canary Islands → check list
  GB/GBR → not offshore; but Jersey, Guernsey, Isle of Man, Gibraltar → check list
You MUST resolve the specific state/territory before classifying.
  "Sheridan" → web search → Sheridan, Wyoming, USA → Wyoming is on the list → OFFSHORE_YES
  "Road Town" → British Virgin Islands → on the list → OFFSHORE_YES

RULE 2 — Street name ≠ jurisdiction
Never confuse a street name with a location:
  "HONG KONG EAST ROAD, QINGDAO" → city is Qingdao, China (not Hong Kong)
  "JERSEY STREET, LONDON" → city is London, UK (not Jersey)
Always identify the city/state/country as the location, not street or road names.

RULE 3 — Address obfuscation
Some addresses disguise the real location with fake prefixes or filler.
Indicators:
  • Cyrillic-transliterated country prefix: SOEDINENNYE SHTATY AMERIKI, KITAI, KITAJ, ROSSIYA
  • Russian abbreviations in non-Russian context: UL (улица), DOM (дом), KV (квартира), KORP (корпус)
  • Filler: "-, -, -", repeated dashes, "N/A"
When detected:
  1. Strip the fake prefix.
  2. Extract real identifiers (building names, district names, road names).
  3. Web-search the extracted address to confirm the actual location.
  4. In reasoning, prefix with "[ОБФУСКАЦИЯ]" — note the fake prefix, extracted address, and resolved location.

RULE 4 — Multi-jurisdiction independence
When entity location ≠ bank location, evaluate BOTH independently:
  Entity: Hong Kong + Bank: China → OFFSHORE_YES (entity is offshore)
  Entity: Kazakhstan + Bank: BVI → OFFSHORE_YES (bank is offshore)
  Entity: USA + Bank: USA → OFFSHORE_NO

RULE 5 — Offshore name mention in text (name ≠ location)
If a company name, street address, or bank name textually contains an offshore jurisdiction name (e.g., "HONGKONG", "GONKONG", "JERSEY", "CAYMAN", "BERMUDA", "VIRGIN"), but all RESOLVED locations (city, country, bank HQ, country codes) are clearly non-offshore:
  → classify as OFFSHORE_SUSPECT (not OFFSHORE_NO)
The textual mention is suspicious and warrants manual review, even when the actual location resolves elsewhere.
This rule does NOT apply when the mention IS the actual resolved location (e.g., a company genuinely in Hong Kong → that triggers OFFSHORE_YES via normal evaluation, not this rule).
Examples of offshore keywords to watch for (any script/transliteration): Hong Kong, Hongkong, Гонконг, Gonkong, Jersey, Джерси, Cayman, BVI, Virgin, Bermuda, Panama, Панама, etc.
</special_rules>

<procedure>
For each transaction, execute these four steps in order:

STEP 1 — PARSE
  a. Read all address fields. Check for obfuscation (Rule 3); if found, strip fake prefixes and extract real components.
  b. Parse each cleaned address into: Street, City, State/Province, Country.
  c. Read country/citizenship code fields. Translate each ISO code to the full country name.
  d. Apply Rule 2: ensure street names are not mistaken for jurisdictions.
  e. Scan all text fields (company names, street addresses, bank names) for offshore jurisdiction keywords (Rule 5). Flag any matches for Step 4.

STEP 2 — SEARCH
  a. Bank HQ (mandatory): for each bank marked "→ VERIFY HQ LOCATION", web-search "[Bank Name] headquarters" or "[Bank Name] [SWIFT] head office". Record HQ city + country.
  b. Entity HQ (best effort): for each company marked "→ SEARCH COMPANY HQ BY NAME", web-search "[Company Name] headquarters". Record HQ city + country. If not found, note it and continue.
  c. Partial-offshore countries (Rule 1): resolve to specific state/territory.
  d. Obfuscation cross-check: if Rule 3 was triggered, web-search the extracted address to confirm the real location.

STEP 3 — MATCH
  For every resolved location (field address, bank branch address, bank HQ, entity HQ, country code):
  - Check if it matches any entry in the offshore list above.
  - Match by meaning: "Bermuda" = "Бермудские острова", "Hong Kong" = "Гонконг".
  - Apply partial-offshore exception (Rule 1) for US, CN, ES, GB, etc.

STEP 4 — CLASSIFY
  a. ANY resolved location matches the offshore list → OFFSHORE_YES
  b. ALL locations resolved to non-offshore, BUT an offshore keyword was flagged in text (Rule 5) → OFFSHORE_SUSPECT
  c. ALL locations resolved to non-offshore, no offshore keywords in text → OFFSHORE_NO
  d. No location data exists (all address fields + bank data + codes are empty/unresolvable) → OFFSHORE_SUSPECT
</procedure>

<examples>

--- Bank HQ ---
"HSBC Private Bank (Suisse) SA" → HQ: St. Helier, Jersey → OFFSHORE_YES
"First Wyoming Bank" → HQ: Cheyenne, Wyoming → OFFSHORE_YES
"Deutsche Bank AG" → HQ: Frankfurt, Germany → not offshore, continue checking other fields
"Standard Chartered Bank (Hong Kong)" → Branch: HK (offshore), HQ: London → OFFSHORE_YES (branch is offshore)

--- Address parsing ---
"123 Main St, Sheridan" (no country) → search → Sheridan, Wyoming → OFFSHORE_YES
"TUEN MUN, HONG KONG" + Country field "USA" → HK is offshore → OFFSHORE_YES (fields evaluated independently)

--- Country codes ---
Code "VG" → Virgin Islands → Виргинские Острова → OFFSHORE_YES
Code "HK" → Hong Kong → Гонконг → OFFSHORE_YES
Code "US" alone → not offshore (Rule 1)

--- Obfuscation ---
"KAZAHSTAN, MONGKOK G, NATHAN ROAD UL, DOM 1318-19, KV 610"
  → strip "KAZAHSTAN" + RU abbreviations → real address: Nathan Road, Mongkok → Hong Kong → OFFSHORE_YES
  → reasoning: "[ОБФУСКАЦИЯ] Префикс 'KAZAHSTAN' скрывает реальный адрес: Nathan Road, Mongkok → Гонконг (офшор)"

"SOEDINENNYE SHTATY AMERIKI, -, RM 20 UNIT B3, 07/FL TUEN MUN IND CTR NO 2 SAN PING CIRCUIT, -, -"
  → strip prefix → Tuen Mun Industrial Centre → Hong Kong → OFFSHORE_YES

--- Entity HQ ---
Field address: Kazakhstan, HQ found: BVI → OFFSHORE_YES (HQ is offshore)
"XYZ Ltd" no field address, HQ found: Hong Kong → OFFSHORE_YES
"ABC Corp" field: Hong Kong, HQ: London → OFFSHORE_YES (field address is offshore)
"Kostanayzernokorm" HQ not found, field: Kazakhstan, bank: China → OFFSHORE_NO (failed HQ ≠ SUSPECT)
"ORION GOLD KG" HQ not found, payer: Kyrgyzstan, bank: Kyrgyzstan → OFFSHORE_NO

--- Offshore name in text (Rule 5) ---
Company "GONKONG FUTIAN FASHION" at address "YI WU SHI, ZHEJIANG, CN", bank "Zhejiang Yiwu Rural Commercial Bank" HQ: Yiwu, China
  → all resolved locations: Yiwu (China), Uzbekistan — non-offshore
  → BUT company name contains "GONKONG" (= Hong Kong keyword)
  → OFFSHORE_SUSPECT (Rule 5: offshore name in company name)

"HONG KONG EAST ROAD, QINGDAO" — street name contains "HONG KONG" but city is Qingdao, China
  → resolved location: Qingdao, China — non-offshore
  → BUT address text contains "HONG KONG" keyword
  → OFFSHORE_SUSPECT (Rule 5: offshore name in address text)

Contrast — NOT Rule 5 (genuine offshore location):
"Standard Chartered Bank (Hong Kong)" with branch IN Hong Kong
  → resolved location IS Hong Kong → OFFSHORE_YES (normal evaluation, not Rule 5)

</examples>

<output_format>
Return a JSON object matching this schema exactly:
{{
  "results": [
    {{
      "transaction_id": "<ID from input>",
      "classification": {{
        "label": "OFFSHORE_YES | OFFSHORE_NO | OFFSHORE_SUSPECT",
        "confidence": <float 0.0–1.0>
      }},
      "reasoning_short_ru": "<1–3 sentences in Russian>",
      "sources": ["<URL>"]
    }}
  ]
}}

reasoning_short_ru rules:
  • Write in Russian, 1–3 sentences, summarizing the key finding.
  • Mention ALL jurisdictions you evaluated (entity location AND bank location when they differ).
  • If obfuscation was detected, start with "[ОБФУСКАЦИЯ]" and describe: fake prefix → real address → actual location.
  • Same entity across transactions → same reasoning.

sources rules:
  • Include URLs from web searches used to verify bank HQ, entity HQ, or address resolution.
  • Empty array [] if no web search was performed.
</output_format>"""
    return prompt


def build_user_message(transactions: List[Dict[str, Any]]) -> str:
    """
    Build user message with a batch of transactions.
    Fields are grouped by evaluation purpose for clarity:
      Section A: Entity addresses
      Section B: Bank information
      Section C: Country / citizenship codes
      Section D: Context (payment details)

    Args:
        transactions: List of normalized transaction dictionaries

    Returns:
        Formatted user message string
    """
    message_parts = [
        "Classify the following transactions. "
        "For each, follow the 4-step procedure from your instructions "
        "and return the JSON result.\n"
    ]

    for i, txn in enumerate(transactions, 1):
        txn_id = txn.get("id", "unknown")
        direction = txn.get("direction", "unknown")
        client_category = txn.get("client_category", "")

        txn_block = [f"--- Transaction #{i} (ID: {txn_id}, Direction: {direction}) ---"]

        if direction == "incoming":
            txn_block.append(_build_incoming_block(txn, client_category))
        else:
            txn_block.append(_build_outgoing_block(txn, client_category))

        message_parts.append("\n".join(txn_block))
        message_parts.append("")  # blank line separator

    return "\n".join(message_parts)


def _build_incoming_block(txn: Dict[str, Any], client_category: str) -> str:
    """Build the field block for an incoming transaction."""
    lines: List[str] = []

    # --- A. Entity addresses ---
    counterparty = txn.get("payer", "")
    counterparty_address = txn.get("payer_address", "")
    counterparty_country = txn.get("payer_country", "")
    payer_address_complete = _join([counterparty_address, counterparty_country])

    actual_payer_address = txn.get("actual_payer_address", "")
    actual_payer_country = txn.get("actual_payer_residence_country", "")
    actual_payer_complete = _join([actual_payer_address, actual_payer_country])

    actual_recipient_address = txn.get("actual_recipient_address", "")
    beneficiary_address = txn.get("beneficiary_address", "")
    client_name = txn.get("beneficiary_name", "")

    lines.append("[A] Entity Addresses:")
    if counterparty:
        lines.append(f"  Payer Name: {counterparty} → SEARCH COMPANY HQ BY NAME")
    if payer_address_complete:
        lines.append(f"  Payer Address: {payer_address_complete}")
    if actual_payer_complete:
        lines.append(f"  Actual Payer Address: {actual_payer_complete}")
    if actual_recipient_address:
        lines.append(f"  Actual Recipient Address: {actual_recipient_address}")
    if beneficiary_address:
        lines.append(f"  Beneficiary Address (our client): {beneficiary_address}")
    if client_category != "Физ" and client_name:
        lines.append(f"  Beneficiary Name (our client): {client_name} → SEARCH COMPANY HQ BY NAME")

    # --- B. Bank information ---
    bank = txn.get("payer_bank", "")
    swift = txn.get("payer_bank_swift", "")
    country_code = txn.get("country_code", "")
    bank_address_complete = _join([
        txn.get("payer_bank_address", ""),
        txn.get("city", ""),
        txn.get("bank_country", ""),
        country_code,
    ])

    correspondent_name = txn.get("payer_correspondent_name", "")
    correspondent_swift = txn.get("payer_correspondent_swift", "")
    correspondent_address = txn.get("payer_correspondent_address", "")

    lines.append("[B] Bank Information:")
    lines.append(f"  Payer Bank: {bank} → VERIFY HQ LOCATION")
    lines.append(f"  Payer Bank SWIFT: {swift}")
    lines.append(f"  Payer Bank Address: {bank_address_complete}")

    if correspondent_name:
        lines.append(f"  Correspondent Bank: {correspondent_name} → VERIFY HQ LOCATION")
        lines.append(f"  Correspondent Bank SWIFT: {correspondent_swift}")
        lines.append(f"  Correspondent Bank Address: {correspondent_address}")

    for idx in (1, 2, 3):
        intermediary = txn.get(f"intermediary_bank_{idx}", "")
        if intermediary:
            lines.append(f"  Intermediary Bank {idx}: {intermediary} → VERIFY HQ LOCATION")

    # --- C. Country/citizenship codes ---
    country_residence = txn.get("country_residence", "")
    citizenship = txn.get("citizenship", "")

    if country_residence or citizenship:
        lines.append("[C] Country / Citizenship Codes:")
        if country_residence:
            lines.append(f"  Beneficiary Residence Country: {country_residence}")
        if citizenship:
            lines.append(f"  Beneficiary Citizenship: {citizenship}")

    # --- D. Context ---
    payment_details = txn.get("payment_details", "")
    if payment_details:
        lines.append("[D] Context:")
        lines.append(f"  Payment Details: {payment_details}")

    return "\n".join(lines)


def _build_outgoing_block(txn: Dict[str, Any], client_category: str) -> str:
    """Build the field block for an outgoing transaction."""
    lines: List[str] = []

    # --- A. Entity addresses ---
    counterparty = txn.get("recipient", "")
    counterparty_address = txn.get("recipient_address", "")
    counterparty_country = txn.get("recipient_country", "")
    country_code = txn.get("country_code", "")
    client_name = txn.get("payer_name", "")

    recipient_address_complete = _join([
        counterparty_address, counterparty_country, country_code
    ])

    lines.append("[A] Entity Addresses:")
    if counterparty:
        lines.append(f"  Recipient Name: {counterparty} → SEARCH COMPANY HQ BY NAME")
    if recipient_address_complete:
        lines.append(f"  Recipient Address: {recipient_address_complete}")
    if client_category != "Физ" and client_name:
        lines.append(f"  Payer Name (our client): {client_name} → SEARCH COMPANY HQ BY NAME")

    # --- B. Bank information ---
    bank = txn.get("recipient_bank", "")
    swift = txn.get("recipient_bank_swift", "")
    bank_address_complete = _join([
        txn.get("recipient_bank_address", ""),
        txn.get("city", ""),
        txn.get("bank_country", ""),
    ])

    lines.append("[B] Bank Information:")
    lines.append(f"  Recipient Bank: {bank} → VERIFY HQ LOCATION")
    lines.append(f"  Recipient Bank SWIFT: {swift}")
    lines.append(f"  Recipient Bank Address: {bank_address_complete}")

    # --- C. Country/citizenship codes ---
    country_residence = txn.get("country_residence", "")
    citizenship = txn.get("citizenship", "")

    if country_residence or citizenship:
        lines.append("[C] Country / Citizenship Codes:")
        if country_residence:
            lines.append(f"  Payer Residence Country: {country_residence}")
        if citizenship:
            lines.append(f"  Payer Citizenship: {citizenship}")

    # --- D. Context ---
    payment_details = txn.get("payment_details", "")
    if payment_details:
        lines.append("[D] Context:")
        lines.append(f"  Payment Details: {payment_details}")

    return "\n".join(lines)


def _join(parts: List[str]) -> str:
    """Join non-empty string parts with ', '."""
    return ", ".join(p for p in parts if p)
