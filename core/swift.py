"""
SWIFT/BIC code handling and country extraction.
Format: BANKCODE(4) + COUNTRYCODE(2) + LOCATIONCODE(2) + [BRANCHCODE(3)]

All offshore country data loaded from data/offshore_countries.md as single source of truth.
Supports extended country codes (ES-CN, US-WY, etc.) by extracting base 2-letter codes.
"""
from pathlib import Path
from typing import Any, Dict, Optional, Set

from core.logger import setup_logger

logger = setup_logger(__name__)

def extract_country_from_swift(swift_code: Optional[str]) -> Dict[str, Optional[str]]:
    """
    Extract country code from SWIFT/BIC code.
    
    SWIFT format: XXXXYYZZZ where:
    - XXXX = Bank code (4 chars)
    - YY = Country code (2 chars, positions 4-5 in 0-indexed)
    - ZZ = Location code (2 chars)
    - ZZZ = Branch code (3 chars, optional)
    
    Args:
        swift_code: SWIFT/BIC code string
    
    Returns:
        Dictionary with country_code and country_name (or None if invalid)
    """
    result = {
        "country_code": None,
        "country_name": None,
        "is_valid_swift": False
    }
    
    if not swift_code or not isinstance(swift_code, str):
        return result
    
    # Clean and uppercase
    swift_clean = swift_code.strip().upper().replace(" ", "").replace("-", "")
    
    # Handle empty string after cleaning
    if not swift_clean:
        return result
    
    # SWIFT must be 8 or 11 characters and alphanumeric
    if len(swift_clean) not in [8, 11]:
        logger.debug(f"Invalid SWIFT length: {swift_code} (len={len(swift_clean)})")
        return result
    
    # Validate first 4 chars are letters (bank code)
    if not swift_clean[:4].isalpha():
        logger.debug(f"Invalid SWIFT format - first 4 chars must be letters: {swift_code}")
        return result
    
    # Extract country code (positions 4-5, 0-indexed = slice [4:6])
    country_code = swift_clean[4:6]
    
    # Validate country code is letters
    if not country_code.isalpha():
        logger.debug(f"Invalid SWIFT format - country code must be letters: {swift_code}")
        return result
    
    # Accept any valid 2-letter country code
    # For country name, use loaded offshore names if available, otherwise use code
    result["country_code"] = country_code
    result["country_name"] = OFFSHORE_COUNTRY_NAMES_EN.get(country_code, country_code)
    result["is_valid_swift"] = True
    
    logger.debug(f"Extracted from SWIFT {swift_code}: {country_code} -> {result['country_name']}")
    
    return result


def extract_base_country_code(code: str) -> Optional[str]:
    """
    Extract base 2-letter country code from extended codes.
    Examples: ES-CN → ES, US-WY → US, HK → HK
    """
    if not code:
        return None
    
    code_clean = code.strip().upper()
    
    # Split on hyphen and take first part
    if "-" in code_clean:
        base_code = code_clean.split("-")[0]
    else:
        base_code = code_clean
    
    # Validate 2 letters, not Russian text
    if len(base_code) == 2 and base_code.isalpha() and base_code not in ["КОД", "КО"]:
        return base_code
    
    return None


def is_valid_country_code(code: str) -> bool:
    """
    Validate if a string is a valid 2-letter country code.
    
    Args:
        code: String to validate
    
    Returns:
        True if valid country code format, False otherwise
    """
    return (
        len(code) == 2 and 
        code.isalpha() and 
        code.upper() not in ["КОД", "КО"]  # Exclude Russian header text
    )


def parse_offshore_table_line(line: str) -> Optional[tuple]:
    """
    Parse a single line from the offshore countries markdown table.
    
    Args:
        line: Line from markdown file
    
    Returns:
        Tuple of (base_code, russian_name, english_name) if valid, None otherwise
    """
    # Skip separator lines and non-table lines
    if not line or "|" not in line or line.startswith("|:-"):
        return None
    
    # Split by pipe and extract columns
    # Format: | RUSNAME | CODE | ENGNAME |
    parts = [p.strip() for p in line.split("|")]
    
    # Need at least 4 parts for proper table format: | RUSNAME | CODE | ENGNAME |
    if len(parts) < 4:
        return None
    
    # Extract columns
    russian_name = parts[1].strip()
    code_raw = parts[2].strip()
    english_name = parts[3].strip()
    
    # Extract base country code (handles extended codes like ES-CN)
    base_code = extract_base_country_code(code_raw)
    
    if base_code and russian_name and english_name:
        return (base_code, russian_name, english_name)
    
    return None


def load_offshore_codes() -> tuple:
    """
    Load offshore country codes and names from data file.
    
    Returns:
        Tuple of (Set[str], Dict[str, str], Dict[str, str]):
        - Set of base 2-letter country codes
        - Dict mapping code to Russian name
        - Dict mapping code to English name
    """
    data_file = Path(__file__).parent.parent / "data" / "offshore_countries.md"
    
    if not data_file.exists():
        logger.warning(f"Offshore countries file not found: {data_file}")
        logger.warning("System will operate without offshore jurisdiction list")
        return (set(), {}, {})
    
    try:
        with open(data_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        if not lines:
            logger.warning("Offshore countries file is empty")
            return (set(), {}, {})
        
        # Parse each line and collect valid codes and names
        offshore_codes = set()
        offshore_names_ru = {}
        offshore_names_en = {}
        
        for line in lines:
            parsed = parse_offshore_table_line(line)
            if parsed is not None:
                code, rus_name, eng_name = parsed
                offshore_codes.add(code)
                offshore_names_ru[code] = rus_name
                offshore_names_en[code] = eng_name
        
        if offshore_codes:
            logger.info(f"Loaded {len(offshore_codes)} offshore country codes with bilingual names")
        else:
            logger.warning("No offshore country codes loaded from file")
        
        return (offshore_codes, offshore_names_ru, offshore_names_en)
    
    except PermissionError as e:
        logger.error(f"Permission denied reading offshore countries file: {e}")
        return (set(), {}, {})
    except Exception as e:
        logger.error(f"Failed to load offshore codes: {e}", exc_info=True)
        return (set(), {}, {})


# Load offshore data from markdown file - single source of truth
OFFSHORE_COUNTRY_CODES, OFFSHORE_COUNTRY_NAMES_RU, OFFSHORE_COUNTRY_NAMES_EN = load_offshore_codes()


def is_offshore_country(country_code: Optional[str]) -> bool:
    """
    Check if country code is in offshore list.
    
    Args:
        country_code: ISO 2-letter country code
    
    Returns:
        True if offshore, False otherwise
    """
    if not country_code:
        return False
    
    return country_code.upper() in OFFSHORE_COUNTRY_CODES
