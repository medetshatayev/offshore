"""
System and user prompts for LLM offshore risk classification.
Loads offshore jurisdictions table and builds prompts dynamically.
"""
from pathlib import Path
from typing import Any, Dict

from core.logger import setup_logger

logger = setup_logger(__name__)


def load_offshore_table() -> str:
    """
    Load offshore countries table from data file.
    
    Returns:
        Formatted table as string for system prompt
    """
    try:
        data_file = Path(__file__).parent.parent / "data" / "offshore_countries.md"
        
        if not data_file.exists():
            error_msg = f"Offshore countries file not found: {data_file}"
            logger.error(error_msg)
            # Return a minimal table so the system doesn't completely fail
            return "| Название | Код | English Name |\n|---|---|---|\n| ERROR | XX | Data file not found |"
        
        with open(data_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Extract just the table portion (lines with |)
        lines = content.split("\n")
        table_lines = [line for line in lines if "|" in line and line.strip()]
        
        if not table_lines:
            logger.error("No table content found in offshore countries file")
            return "| Название | Код | English Name |\n|---|---|---|\n| ERROR | XX | No data found |"
        
        logger.info(f"Loaded offshore table with {len(table_lines)} lines")
        return "\n".join(table_lines)
    
    except Exception as e:
        logger.error(f"Failed to load offshore table: {e}", exc_info=True)
        return "| Название | Код | English Name |\n|---|---|---|\n| ERROR | XX | Failed to load data |"


def build_system_prompt() -> str:
    """
    Build the system prompt with embedded offshore jurisdictions table.
    
    Returns:
        Complete system prompt string
    """
    offshore_table = load_offshore_table()
    
    prompt = f"""You are an expert financial compliance analyst for a Kazakhstani bank.

Your task is to analyze banking transactions and determine if they involve offshore jurisdictions or present offshore-related risks.

**OFFSHORE JURISDICTIONS LIST:**
Any transaction involving these countries should be flagged as offshore:

{offshore_table}

**ANALYSIS RULES:**

1. **Bank Address is Critical**: The bank address is the most reliable indicator of the actual physical location of the bank. When the address clearly shows a specific city and country (e.g., "BEIJING, CHINA" or "NEW YORK, USA"), this should be your primary reference point.

2. **SWIFT Country Code**: The country extracted from the SWIFT/BIC code is a strong indicator. Cross-reference it with the offshore list and the bank address for consistency.

3. **City and Country Fields**: Use these in combination with the bank address to confirm the jurisdiction. If there's a mismatch between the SWIFT country and location data, prioritize the bank address details.

4. **Special Cases - Sub-jurisdictions and Islands**: Some offshore jurisdictions are special administrative regions or territories within larger countries. These have their own SWIFT country codes and must be distinguished from their parent countries:
   - **China (CN)** is NOT offshore, but **Macao (MO)** and **Hong Kong (HK)** ARE offshore - they have separate SWIFT codes
   - **Spain (ES)** is NOT offshore, but **Canary Islands (ES-CN)** IS offshore (includes: Tenerife, Gran Canaria, Fuerteventura, Lanzarote, etc.)
   - **USA (US)** is NOT offshore, but **Wyoming (US-WY)** IS offshore for certain purposes
   - **Malaysia (MY)** is NOT offshore, but **Labuan (MY-15)** IS offshore
   - **Portugal (PT)** is NOT offshore, but **Madeira (PT-30)** IS offshore
   - **Morocco (MA)** is NOT offshore, but **Tangier (MA-TNG)** IS offshore
   - **Netherlands (NL)** for Antilles islands (Aruba, Bonaire, Curaçao, Saba, Sint Maarten, Sint Eustatius) IS offshore
   - **United Kingdom (GB)** for certain islands like **Jersey, Guernsey, Isle of Man** ARE offshore with their own codes
   
   **Important**: Some islands or territories may officially belong to countries from the offshore list but are not explicitly mentioned. When encountering such cases, use web_search to verify the jurisdiction and determine if they should be classified as offshore.
   
   **How to classify**: Check the bank address carefully. If it shows a mainland city (e.g., Beijing, Shanghai, Madrid, New York), classify as NOT offshore even if there are name ambiguities. The physical location in the address is the key indicator.

5. **Classification Labels**:
   - **OFFSHORE_YES**: Bank is clearly located in an offshore jurisdiction from the list (confirmed by SWIFT code and/or address)
   - **OFFSHORE_SUSPECT**: Some indicators suggest possible offshore involvement but evidence is ambiguous or incomplete
   - **OFFSHORE_NO**: Bank is clearly NOT in an offshore jurisdiction (confirmed by address and SWIFT code)

6. **Conservative Approach**: When uncertain due to incomplete or contradictory data, use OFFSHORE_SUSPECT. Provide clear reasoning about what is known and what is ambiguous.

7. **Web Search Tool - WHEN TO USE**: You SHOULD use the `web_search` tool in these situations:
   - **Ambiguous cases**: When signals are unclear or contradictory
   - **Unknown banks**: To verify the actual country of domicile for the bank
   - **Company verification**: To check if the counterparty company has offshore connections
   - **Address verification**: To verify if the bank address or city suggests offshore activity
   - **Suspicious patterns**: When company names, addresses, or bank names suggest possible offshore involvement but data is insufficient
   - **SWIFT verification**: When SWIFT code indicates one country but other data suggests another
   - **Edge cases**: Any situation where more context would help determine offshore risk
   
   If you use web_search, you MUST cite the sources in the `sources` array. Only include canonical, authoritative URLs.
   
   **DO NOT include** "Нет источников" in your response - leave sources as empty array [] if not used.

8. **Output Format**: You MUST return valid JSON that conforms to the schema provided. The response must include:
   - transaction_id, direction
   - signals (swift country, matches)
   - classification (label and confidence 0.0-1.0)
   - reasoning_short_ru (1-2 sentences in Russian explaining the decision)
   - sources (array of URLs if web_search was used, empty array [] otherwise - NEVER include text "Нет источников")

**IMPORTANT**: 
- Keep reasoning concise (1-2 sentences in Russian)
- Confidence should reflect the strength of evidence (1.0 = definitive, 0.5 = uncertain)
- Always provide valid JSON output
- Use web_search proactively for ambiguous/suspicious cases to provide thorough analysis
"""
    
    return prompt


def build_user_message(transaction_data: Dict[str, Any]) -> str:
    """
    Build user message with transaction details for LLM.
    Sends only essential fields: counterparty (non-physical only), bank details,
    location info, and payment details (outgoing only).
    
    Args:
        transaction_data: Normalized transaction dictionary
    
    Returns:
        Formatted user message string with only specified fields
    """
    direction = transaction_data.get("direction", "unknown")
    client_category = transaction_data.get("client_category", "")
    
    # Conditionally include counterparty (only for non-physical clients)
    include_counterparty = (client_category != "Физ")
    
    # Extract direction-specific fields
    if direction == "incoming":
        counterparty = transaction_data.get("payer", "")
        bank = transaction_data.get("payer_bank", "")
        swift = transaction_data.get("payer_bank_swift", "")
        bank_address = transaction_data.get("payer_bank_address", "")
        country = transaction_data.get("payer_country", "")
    else:  # outgoing
        counterparty = transaction_data.get("recipient", "")
        bank = transaction_data.get("recipient_bank", "")
        swift = transaction_data.get("recipient_bank_swift", "")
        bank_address = transaction_data.get("recipient_bank_address", "")
        country = transaction_data.get("recipient_country", "")
    
    # Extract common fields
    city = transaction_data.get("city", "")
    country_code = transaction_data.get("country_code", "")
    
    # Build message parts
    message_parts = []
    
    # Add counterparty only for non-physical clients
    if include_counterparty and counterparty:
        label = "Плательщик" if direction == "incoming" else "Получатель"
        message_parts.append(f"{label}: {counterparty}")
    
    # Add required fields
    message_parts.extend([
        f"SWIFT банка: {swift}",
        f"Город: {city}",
        f"Банк: {bank}",
        f"Адрес банка: {bank_address}",
        f"Код страны: {country_code}",
        f"Страна: {country}"
    ])
    
    # Add payment details for outgoing transactions only
    if direction == "outgoing":
        payment_details = transaction_data.get("payment_details", "")
        message_parts.append(f"Детали платежа: {payment_details}")
    
    return "\n".join(message_parts)
