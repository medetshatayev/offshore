"""
SWIFT/BIC code handling and country extraction.
Format: BANKCODE(4) + COUNTRYCODE(2) + LOCATIONCODE(2) + [BRANCHCODE(3)]
"""
import os
from typing import Optional, Dict, Any, Set
from pathlib import Path
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
    swift_clean = swift_code.strip().upper().replace(" ", "")
    
    # SWIFT must be 8 or 11 characters
    if len(swift_clean) not in [8, 11]:
        logger.debug(f"Invalid SWIFT length: {swift_code} (len={len(swift_clean)})")
        return result
    
    # Extract country code (positions 4-5, 0-indexed = slice [4:6])
    country_code = swift_clean[4:6]
    
    # Validate country code
    if country_code not in VALID_COUNTRY_CODES:
        logger.debug(f"Invalid country code in SWIFT: {swift_code} -> {country_code}")
        return result
    
    result["country_code"] = country_code
    result["country_name"] = COUNTRY_CODE_TO_NAME.get(country_code, country_code)
    result["is_valid_swift"] = True
    
    logger.debug(f"Extracted from SWIFT {swift_code}: {country_code} -> {result['country_name']}")
    
    return result


def load_offshore_codes() -> Set[str]:
    """
    Load offshore country codes from data file.
    
    Returns:
        Set of ISO 2-letter country codes
    """
    try:
        data_file = Path(__file__).parent.parent / "data" / "offshore_countries.md"
        
        if not data_file.exists():
            logger.warning(f"Offshore countries file not found: {data_file}")
            return set()
        
        offshore_codes = set()
        
        with open(data_file, "r", encoding="utf-8") as f:
            for line in f:
                # Parse markdown table lines
                if "|" in line and not line.startswith("|:-"):
                    parts = [p.strip() for p in line.split("|")]
                    if len(parts) >= 3:
                        # Second column (index 2) is the CODE
                        code = parts[2].strip()
                        # Validate it's a 2-letter code
                        if code and len(code) == 2 and code.isalpha():
                            offshore_codes.add(code.upper())
        
        logger.info(f"Loaded {len(offshore_codes)} offshore country codes")
        return offshore_codes
    
    except Exception as e:
        logger.error(f"Failed to load offshore codes: {e}")
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
