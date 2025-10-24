"""
Simple fuzzy matching for country names, codes, and cities.
Uses substring and Levenshtein similarity for short tokens.
"""
import os
from typing import Optional, List, Dict, Any
import Levenshtein
from core.logger import setup_logger
from core.swift import OFFSHORE_COUNTRY_CODES, COUNTRY_CODE_TO_NAME

logger = setup_logger(__name__)

# Fuzzy match threshold from env or default
FUZZY_THRESHOLD = float(os.getenv("FUZZY_MATCH_THRESHOLD", "0.80"))


def normalize_string(text: Optional[str]) -> str:
    """
    Normalize string for matching: lowercase, trim, remove extra spaces.
    
    Args:
        text: Input string
    
    Returns:
        Normalized string
    """
    if not text or not isinstance(text, str):
        return ""
    
    return " ".join(text.lower().strip().split())


def calculate_similarity(s1: str, s2: str) -> float:
    """
    Calculate Levenshtein similarity ratio between two strings.
    
    Args:
        s1: First string
        s2: Second string
    
    Returns:
        Similarity score (0.0 to 1.0)
    """
    if not s1 or not s2:
        return 0.0
    
    # Normalize both strings
    s1_norm = normalize_string(s1)
    s2_norm = normalize_string(s2)
    
    if not s1_norm or not s2_norm:
        return 0.0
    
    # Use Levenshtein ratio
    return Levenshtein.ratio(s1_norm, s2_norm)


def fuzzy_match_country_code(
    code: Optional[str],
    threshold: float = FUZZY_THRESHOLD
) -> Dict[str, Any]:
    """
    Check if country code matches offshore list.
    
    Args:
        code: ISO 2-letter country code
        threshold: Minimum similarity threshold (not used for exact code match)
    
    Returns:
        Match result with value and score
    """
    result = {
        "value": None,
        "score": None,
        "is_offshore": False
    }
    
    if not code or not isinstance(code, str):
        return result
    
    code_clean = code.strip().upper()
    
    # Exact match check
    if code_clean in OFFSHORE_COUNTRY_CODES:
        result["value"] = code_clean
        result["score"] = 1.0
        result["is_offshore"] = True
        logger.debug(f"Country code '{code}' is offshore (exact match)")
    
    return result


def fuzzy_match_country_name(
    name: Optional[str],
    threshold: float = FUZZY_THRESHOLD
) -> Dict[str, Any]:
    """
    Fuzzy match country name against offshore list.
    
    Args:
        name: Country name to match
        threshold: Minimum similarity threshold
    
    Returns:
        Match result with best match value and score
    """
    result = {
        "value": None,
        "score": None,
        "is_offshore": False,
        "matches": []  # Top 3 matches
    }
    
    if not name or not isinstance(name, str):
        return result
    
    name_norm = normalize_string(name)
    if not name_norm or len(name_norm) < 3:
        return result
    
    # Build list of offshore country names
    offshore_names = []
    for code in OFFSHORE_COUNTRY_CODES:
        country_name = COUNTRY_CODE_TO_NAME.get(code, "")
        if country_name:
            offshore_names.append((code, country_name))
    
    # Calculate similarities
    matches = []
    for code, offshore_name in offshore_names:
        # Check substring match first (case insensitive)
        offshore_norm = normalize_string(offshore_name)
        
        if name_norm in offshore_norm or offshore_norm in name_norm:
            similarity = 1.0  # Exact substring match
        else:
            # Use fuzzy matching only for short strings (< 20 chars)
            if len(name_norm) < 20:
                similarity = calculate_similarity(name_norm, offshore_norm)
            else:
                similarity = 0.0
        
        if similarity >= threshold:
            matches.append({
                "code": code,
                "name": offshore_name,
                "score": similarity
            })
    
    # Sort by score descending and take top 3
    matches.sort(key=lambda x: x["score"], reverse=True)
    result["matches"] = matches[:3]
    
    if matches:
        best = matches[0]
        result["value"] = f"{best['name']} ({best['code']})"
        result["score"] = best["score"]
        result["is_offshore"] = True
        logger.debug(f"Country name '{name}' matched offshore: {best['name']} (score={best['score']:.2f})")
    
    return result


def fuzzy_match_city(
    city: Optional[str],
    threshold: float = FUZZY_THRESHOLD
) -> Dict[str, Any]:
    """
    Simple city name matching.
    Note: This is a placeholder for basic city matching.
    In production, this would match against a known list of offshore cities.
    
    Args:
        city: City name to check
        threshold: Minimum similarity threshold
    
    Returns:
        Match result
    """
    result = {
        "value": None,
        "score": None,
        "is_suspicious": False
    }
    
    if not city or not isinstance(city, str):
        return result
    
    city_norm = normalize_string(city)
    if not city_norm or len(city_norm) < 3:
        return result
    
    # Known offshore financial centers (partial list)
    offshore_cities = [
        "george town", "road town", "bridgetown", "nassau", "hamilton",
        "panama city", "manama", "douglas", "port louis", "victoria",
        "gibraltar", "andorra la vella", "monaco", "vaduz", "san marino",
        "hong kong", "singapore", "dubai", "macao"
    ]
    
    # Check for matches
    for offshore_city in offshore_cities:
        if city_norm in offshore_city or offshore_city in city_norm:
            result["value"] = offshore_city.title()
            result["score"] = 1.0
            result["is_suspicious"] = True
            logger.debug(f"City '{city}' matched offshore city: {offshore_city}")
            return result
        
        # Fuzzy match only for short city names
        if len(city_norm) < 20:
            similarity = calculate_similarity(city_norm, offshore_city)
            if similarity >= threshold:
                result["value"] = offshore_city.title()
                result["score"] = similarity
                result["is_suspicious"] = True
                logger.debug(f"City '{city}' fuzzy matched offshore city: {offshore_city} (score={similarity:.2f})")
                return result
    
    return result


def aggregate_matching_signals(
    swift_country: Dict[str, Any],
    country_code_match: Dict[str, Any],
    country_name_match: Dict[str, Any],
    city_match: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Aggregate all matching signals into a summary.
    
    Args:
        swift_country: SWIFT country extraction result
        country_code_match: Country code match result
        country_name_match: Country name match result
        city_match: City match result
    
    Returns:
        Aggregated signals dictionary
    """
    signals = {
        "swift_country_code": swift_country.get("country_code"),
        "swift_country_name": swift_country.get("country_name"),
        "is_offshore_by_swift": False,
        "country_code_match": {
            "value": country_code_match.get("value"),
            "score": country_code_match.get("score")
        },
        "country_name_match": {
            "value": country_name_match.get("value"),
            "score": country_name_match.get("score")
        },
        "city_match": {
            "value": city_match.get("value"),
            "score": city_match.get("score")
        },
        "any_offshore_signal": False
    }
    
    # Check if SWIFT country is offshore
    if swift_country.get("country_code"):
        signals["is_offshore_by_swift"] = swift_country["country_code"] in OFFSHORE_COUNTRY_CODES
    
    # Check if any signal indicates offshore
    signals["any_offshore_signal"] = (
        signals["is_offshore_by_swift"] or
        country_code_match.get("is_offshore", False) or
        country_name_match.get("is_offshore", False) or
        city_match.get("is_suspicious", False)
    )
    
    return signals
