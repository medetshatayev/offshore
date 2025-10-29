"""
System and user prompts for LLM offshore risk classification.
Loads offshore jurisdictions table and builds prompts dynamically.
"""
from pathlib import Path
from typing import Dict, Any
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

1. **SWIFT Country Priority**: The country extracted from the SWIFT/BIC code is the most reliable indicator. If the SWIFT country code matches the offshore list, this is a strong signal.

2. **Simple Fuzzy Matching**: Use the provided fuzzy matching signals for:
   - Country code (2-letter ISO code)
   - Country name (full name)
   - City name
   
   These signals are provided in the transaction data with match scores (0.0 to 1.0).

3. **Classification Labels**:
   - **OFFSHORE_YES**: Clear evidence of offshore jurisdiction involvement (SWIFT match, exact country code/name match)
   - **OFFSHORE_SUSPECT**: Partial indicators or circumstantial evidence (fuzzy matches, suspicious city, but not definitive)
   - **OFFSHORE_NO**: No offshore indicators found

4. **Conservative Approach**: When uncertain, use OFFSHORE_SUSPECT rather than making assumptions. Provide clear reasoning.

5. **Web Search Tool - WHEN TO USE**: You SHOULD use the `web_search` tool in these situations:
   - **Ambiguous cases**: When signals are unclear or contradictory
   - **Unknown banks**: To verify the actual country of domicile for the bank
   - **Company verification**: To check if the counterparty company has offshore connections
   - **Address verification**: To verify if the bank address or city suggests offshore activity
   - **Suspicious patterns**: When company names, addresses, or bank names suggest possible offshore involvement but data is insufficient
   - **SWIFT verification**: When SWIFT code indicates one country but other data suggests another
   - **Edge cases**: Any situation where more context would help determine offshore risk
   
   If you use web_search, you MUST cite the sources in the `sources` array. Only include canonical, authoritative URLs.
   
   **DO NOT include** "Нет источников" in your response - leave sources as empty array [] if not used.

6. **Output Format**: You MUST return valid JSON that conforms to the schema provided. The response must include:
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


def build_websearch_system_prompt() -> str:
    """
    Build system prompt specifically for web_search tool usage.
    
    Returns:
        Web search guidance prompt
    """
    return """**WEB SEARCH GUIDANCE:**

Use web_search proactively when:
- You lack sufficient information to make a confident determination
- Bank name, company name, or address suggests possible offshore ties
- SWIFT country conflicts with other data
- You need to verify if a company or bank has offshore operations
- Transaction involves unfamiliar entities that might have offshore connections

Search query examples:
- "Wells Fargo WFBIUS6S bank headquarters location"
- "[Company Name] offshore operations company registration"
- "[Bank Name] [City] offshore banking services"
- "SWIFT code [CODE] bank country verification"

When searching:
- Use specific, focused queries
- Prioritize authoritative sources (SWIFT.com, central banks, regulators, official company sites)
- Cite ALL URLs you reference in the `sources` array
- Never include "Нет источников" - use empty array [] if no search performed

Remember: It's better to search and be thorough than to miss potential offshore involvement."""


def build_user_message(transaction_data: Dict[str, Any]) -> str:
    """
    Build user message with transaction details for LLM.
    
    Args:
        transaction_data: Normalized transaction dictionary
    
    Returns:
        Formatted user message string
    """
    # Extract key fields
    txn_id = transaction_data.get("id", "N/A")
    direction = transaction_data.get("direction", "unknown")
    currency = transaction_data.get("currency", "N/A")
    swift = transaction_data.get("swift_code", "N/A")
    country_res = transaction_data.get("country_residence", "N/A")
    country_code = transaction_data.get("country_code", "N/A")
    recipient_country = transaction_data.get("recipient_country", "N/A")
    payer_country = transaction_data.get("payer_country", "N/A")
    city = transaction_data.get("city", "N/A")
    
    # Extract signals if provided
    signals = transaction_data.get("signals", {})
    swift_country = signals.get("swift_country_code", "N/A")
    swift_country_name = signals.get("swift_country_name", "N/A")
    is_offshore_swift = signals.get("is_offshore_by_swift", False)
    
    country_code_match = signals.get("country_code_match", {})
    country_name_match = signals.get("country_name_match", {})
    city_match = signals.get("city_match", {})
    
    # Build counterparty info
    if direction == "incoming":
        counterparty = transaction_data.get("payer", "N/A")
        bank = transaction_data.get("payer_bank", "N/A")
        country_info = f"Payer Country: {payer_country}"
    else:
        counterparty = transaction_data.get("recipient", "N/A")
        bank = transaction_data.get("recipient_bank", "N/A")
        country_info = f"Recipient Country: {recipient_country}"
    
    message = f"""**TRANSACTION TO ANALYZE:**

Transaction ID: {txn_id}
Direction: {direction}
Currency: {currency}

**COUNTERPARTY INFORMATION:**
Counterparty: {counterparty}
Bank: {bank}
Bank SWIFT Code: {swift}
City: {city}

**COUNTRY INFORMATION:**
Country of Residence: {country_res}
Country Code: {country_code}
{country_info}

**LOCAL MATCHING SIGNALS:**
SWIFT Extracted Country: {swift_country} ({swift_country_name})
Is Offshore by SWIFT: {is_offshore_swift}

Country Code Match: {country_code_match.get('value', 'None')} (score: {country_code_match.get('score', 'N/A')})
Country Name Match: {country_name_match.get('value', 'None')} (score: {country_name_match.get('score', 'N/A')})
City Match: {city_match.get('value', 'None')} (score: {city_match.get('score', 'N/A')})

**YOUR TASK:**
Based on the above information and the offshore jurisdictions list, determine the offshore risk level for this transaction.
Return a JSON response following the exact schema provided.
"""
    
    return message
