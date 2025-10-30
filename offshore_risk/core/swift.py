"""
SWIFT/BIC code handling and country extraction.
Format: BANKCODE(4) + COUNTRYCODE(2) + LOCATIONCODE(2) + [BRANCHCODE(3)]
"""
from pathlib import Path
from typing import Any, Dict, Optional, Set

from core.logger import setup_logger

logger = setup_logger(__name__)

# ISO 3166-1 alpha-2 country codes (subset for validation)
VALID_COUNTRY_CODES = {
    "AD", "AE", "AF", "AG", "AI", "AL", "AM", "AO", "AQ", "AR", "AS", "AT",
    "AU", "AW", "AX", "AZ", "BA", "BB", "BD", "BE", "BF", "BG", "BH", "BI",
    "BJ", "BL", "BM", "BN", "BO", "BQ", "BR", "BS", "BT", "BV", "BW", "BY",
    "BZ", "CA", "CC", "CD", "CF", "CG", "CH", "CI", "CK", "CL", "CM", "CN",
    "CO", "CR", "CU", "CV", "CW", "CX", "CY", "CZ", "DE", "DJ", "DK", "DM",
    "DO", "DZ", "EC", "EE", "EG", "EH", "ER", "ES", "ET", "FI", "FJ", "FK",
    "FM", "FO", "FR", "GA", "GB", "GD", "GE", "GF", "GG", "GH", "GI", "GL",
    "GM", "GN", "GP", "GQ", "GR", "GS", "GT", "GU", "GW", "GY", "HK", "HM",
    "HN", "HR", "HT", "HU", "ID", "IE", "IL", "IM", "IN", "IO", "IQ", "IR",
    "IS", "IT", "JE", "JM", "JO", "JP", "KE", "KG", "KH", "KI", "KM", "KN",
    "KP", "KR", "KW", "KY", "KZ", "LA", "LB", "LC", "LI", "LK", "LR", "LS",
    "LT", "LU", "LV", "LY", "MA", "MC", "MD", "ME", "MF", "MG", "MH", "MK",
    "ML", "MM", "MN", "MO", "MP", "MQ", "MR", "MS", "MT", "MU", "MV", "MW",
    "MX", "MY", "MZ", "NA", "NC", "NE", "NF", "NG", "NI", "NL", "NO", "NP",
    "NR", "NU", "NZ", "OM", "PA", "PE", "PF", "PG", "PH", "PK", "PL", "PM",
    "PN", "PR", "PS", "PT", "PW", "PY", "QA", "RE", "RO", "RS", "RU", "RW",
    "SA", "SB", "SC", "SD", "SE", "SG", "SH", "SI", "SJ", "SK", "SL", "SM",
    "SN", "SO", "SR", "SS", "ST", "SV", "SX", "SY", "SZ", "TC", "TD", "TF",
    "TG", "TH", "TJ", "TK", "TL", "TM", "TN", "TO", "TR", "TT", "TV", "TW",
    "TZ", "UA", "UG", "UM", "US", "UY", "UZ", "VA", "VC", "VE", "VG", "VI",
    "VN", "VU", "WF", "WS", "YE", "YT", "ZA", "ZM", "ZW"
}

# Mapping of ISO codes to country names (English)
COUNTRY_CODE_TO_NAME = {
    "AD": "Andorra", "AE": "United Arab Emirates", "AG": "Antigua and Barbuda",
    "AI": "Anguilla", "AW": "Aruba", "BB": "Barbados", "BH": "Bahrain",
    "BM": "Bermuda", "BN": "Brunei", "BQ": "Bonaire, Sint Eustatius and Saba",
    "BS": "Bahamas", "BZ": "Belize", "CK": "Cook Islands", "CO": "Colombia",
    "CR": "Costa Rica", "DJ": "Djibouti", "DM": "Dominica", "DO": "Dominican Republic",
    "ES": "Spain", "FJ": "Fiji", "FR": "France", "GB": "United Kingdom",
    "GD": "Grenada", "GF": "French Guiana", "GG": "Guernsey", "GI": "Gibraltar",
    "GS": "South Georgia and the South Sandwich Islands", "GT": "Guatemala",
    "GU": "Guam", "GY": "Guyana", "HK": "Hong Kong", "IM": "Isle of Man",
    "IO": "British Indian Ocean Territory", "JE": "Jersey", "JM": "Jamaica",
    "KM": "Comoros", "KN": "Saint Kitts and Nevis", "KY": "Cayman Islands",
    "LB": "Lebanon", "LC": "Saint Lucia", "LK": "Sri Lanka", "LR": "Liberia",
    "MA": "Morocco", "MC": "Monaco", "ME": "Montenegro", "MH": "Marshall Islands",
    "MM": "Myanmar", "MO": "Macao", "MP": "Northern Mariana Islands",
    "MR": "Mauritania", "MS": "Montserrat", "MT": "Malta", "MU": "Mauritius",
    "MV": "Maldives", "MY": "Malaysia", "NG": "Nigeria", "NL": "Netherlands",
    "NR": "Nauru", "NU": "Niue", "NZ": "New Zealand", "PA": "Panama",
    "PF": "French Polynesia", "PH": "Philippines", "PR": "Puerto Rico",
    "PT": "Portugal", "PW": "Palau", "SC": "Seychelles", "SM": "San Marino",
    "SR": "Suriname", "SX": "Sint Maarten", "TC": "Turks and Caicos Islands",
    "TF": "French Southern Territories", "TO": "Tonga", "TT": "Trinidad and Tobago",
    "TZ": "Tanzania", "US": "United States", "VC": "Saint Vincent and the Grenadines",
    "VG": "Virgin Islands (British)", "VI": "Virgin Islands (U.S.)",
    "VU": "Vanuatu", "WS": "Samoa", "KZ": "Kazakhstan", "RU": "Russia"
}


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
    
    # Validate country code exists in our list
    if country_code not in VALID_COUNTRY_CODES:
        logger.debug(f"Unknown country code in SWIFT: {swift_code} -> {country_code}")
        # Still mark as potentially valid format, just unknown country
        result["country_code"] = country_code
        result["country_name"] = country_code  # Use code as name if unknown
        result["is_valid_swift"] = True
        return result
    
    result["country_code"] = country_code
    result["country_name"] = COUNTRY_CODE_TO_NAME.get(country_code, country_code)
    result["is_valid_swift"] = True
    
    logger.debug(f"Extracted from SWIFT {swift_code}: {country_code} -> {result['country_name']}")
    
    return result


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


def parse_offshore_table_line(line: str) -> Optional[str]:
    """
    Parse a single line from the offshore countries markdown table.
    
    Args:
        line: Line from markdown file
    
    Returns:
        Country code if valid, None otherwise
    """
    # Skip separator lines and non-table lines
    if not line or "|" not in line or line.startswith("|:-"):
        return None
    
    # Split by pipe and extract columns
    parts = [p.strip() for p in line.split("|")]
    
    # Need at least 4 parts for proper table format: | Name | Code | English |
    if len(parts) < 4:
        return None
    
    # Third column (index 2) contains the country code
    code = parts[2].strip()
    
    if code and is_valid_country_code(code):
        return code.upper()
    
    return None


def load_offshore_codes() -> Set[str]:
    """
    Load offshore country codes from data file.
    
    Returns:
        Set of ISO 2-letter country codes
    """
    data_file = Path(__file__).parent.parent / "data" / "offshore_countries.md"
    
    if not data_file.exists():
        logger.warning(f"Offshore countries file not found: {data_file}")
        logger.warning("System will operate without offshore jurisdiction list")
        return set()
    
    try:
        with open(data_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        if not lines:
            logger.warning("Offshore countries file is empty")
            return set()
        
        # Parse each line and collect valid codes
        offshore_codes = {
            code for line in lines 
            if (code := parse_offshore_table_line(line)) is not None
        }
        
        if offshore_codes:
            logger.info(f"Loaded {len(offshore_codes)} offshore country codes")
        else:
            logger.warning("No offshore country codes loaded from file")
        
        return offshore_codes
    
    except PermissionError as e:
        logger.error(f"Permission denied reading offshore countries file: {e}")
        return set()
    except Exception as e:
        logger.error(f"Failed to load offshore codes: {e}", exc_info=True)
        return set()


# Load offshore codes at module import
OFFSHORE_COUNTRY_CODES = load_offshore_codes()


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
