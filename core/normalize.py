"""
Data normalization and metadata enrichment.
Handles currency conversion, amount cleaning, and transaction metadata.
"""
from datetime import datetime
from typing import Any, Dict, Optional

import pandas as pd

from core.config import get_settings
from core.exceptions import ValidationError
from core.logger import setup_logger

logger = setup_logger(__name__)
settings = get_settings()


def clean_amount_kzt(value: Any) -> Optional[float]:
    """
    Clean and normalize KZT amount.
    Removes spaces, thousands separators, and converts to float.
    
    Args:
        value: Raw amount value (string or number)
    
    Returns:
        Normalized float value or None if invalid
    """
    if pd.isna(value) or value is None:
        return None
    
    # Convert to string and clean
    amount_str = str(value).strip()
    
    # Handle empty strings
    if not amount_str:
        return None
    
    # Remove spaces and common thousands separators
    amount_str = amount_str.replace(" ", "").replace(",", "").replace("\xa0", "")
    
    # Remove any non-numeric characters except decimal point and minus sign
    # This handles cases like "5000000.00 KZT" or similar
    cleaned = ""
    for char in amount_str:
        if char.isdigit() or char in [".", "-"]:
            cleaned += char
    
    if not cleaned:
        logger.warning(f"Failed to parse amount: '{value}' - no numeric content")
        return None
    
    # Try to convert to float
    try:
        result = float(cleaned)
        # Validate reasonable range
        if result < 0:
            logger.warning(f"Negative amount detected: {result}, using absolute value")
            return abs(result)
        return result
    except (ValueError, TypeError) as e:
        logger.warning(f"Failed to parse amount: '{value}' -> {e}")
        return None


def filter_by_threshold(df: pd.DataFrame, threshold: Optional[float] = None) -> pd.DataFrame:
    """
    Filter transactions by KZT amount threshold.
    
    Args:
        df: DataFrame with 'Сумма в тенге' column
        threshold: Optional custom threshold (defaults to configured value)
    
    Returns:
        Filtered DataFrame with only transactions >= threshold
    
    Raises:
        ValidationError: If required column is missing
    """
    if "Сумма в тенге" not in df.columns:
        raise ValidationError(
            "Missing required column 'Сумма в тенге' in DataFrame",
            details={"available_columns": list(df.columns)}
        )
    
    threshold = threshold or settings.amount_threshold_kzt
    
    # Create normalized amount column
    df["amount_kzt_normalized"] = df["Сумма в тенге"].apply(clean_amount_kzt)
    
    # Count before filtering
    before_count = len(df)
    
    # Filter by threshold
    df_filtered = df[
        df["amount_kzt_normalized"].notna() & 
        (df["amount_kzt_normalized"] >= threshold)
    ].copy()
    
    after_count = len(df_filtered)
    filtered_out = before_count - after_count
    
    logger.info(
        f"Filtered transactions: {before_count} -> {after_count} "
        f"(removed {filtered_out} below {threshold:,.0f} KZT)"
    )
    
    return df_filtered


def add_metadata(df: pd.DataFrame, direction: str) -> pd.DataFrame:
    """
    Add metadata columns to DataFrame.
    
    Args:
        df: DataFrame to enrich
        direction: Transaction direction ("incoming" or "outgoing")
    
    Returns:
        DataFrame with added metadata columns
    """
    df = df.copy()
    
    # Add direction
    df["direction"] = direction
    
    # Add processing timestamp
    df["processed_at"] = datetime.utcnow().isoformat() + "Z"
    
    logger.debug(f"Added metadata: direction={direction}")
    
    return df


def safe_get_value(row: pd.Series, key: str, default: Any = None) -> Any:
    """
    Safely get value from pandas Series, handling NaN and None.
    
    Args:
        row: pandas Series
        key: Column key
        default: Default value if missing or NaN
    
    Returns:
        Value or default
    """
    value = row.get(key, default)
    if pd.isna(value):
        return default
    return value


def safe_get_string(row: pd.Series, key: str, default: str = "") -> str:
    """
    Safely convert value to string, returning default if empty or None.
    
    Args:
        row: pandas Series
        key: Column key
        default: Default string value
    
    Returns:
        String value or default
    """
    value = safe_get_value(row, key, default)
    if value is None or value == "":
        return default
    return str(value)


def normalize_transaction(row: pd.Series, direction: str) -> Dict[str, Any]:
    """
    Normalize a single transaction row to a standard dictionary format.
    
    Args:
        row: pandas Series representing a transaction
        direction: Transaction direction ("incoming" or "outgoing")
    
    Returns:
        Normalized transaction dictionary
    """
    # Common fields
    normalized = {
        "id": safe_get_string(row, "№п/п", "unknown"),
        "direction": direction,
        "amount_kzt": safe_get_value(row, "amount_kzt_normalized", 0.0),
        "amount": safe_get_value(row, "Сумма"),
        "currency": safe_get_string(row, "Валюта платежа"),
        "value_date": safe_get_string(row, "Дата валютирования"),
        "acceptance_date": safe_get_string(row, "Дата приема"),
        "country_residence": safe_get_string(row, "Страна резидентства"),
        "citizenship": safe_get_string(row, "Гражданство"),
        "city": safe_get_string(row, "Город"),
        "country_code": safe_get_string(row, "Код страны"),
        "status": safe_get_string(row, "Состояние"),
        "processed_at": safe_get_string(row, "processed_at")
    }
    
    # Direction-specific fields
    if direction == "incoming":
        normalized.update({
            "beneficiary_name": safe_get_string(row, "Наименование бенефициара (наш клиент)"),
            "beneficiary_account": safe_get_string(row, "Номер счета бенефициара"),
            "payer": safe_get_string(row, "Плательщик"),
            "payer_bank": safe_get_string(row, "Банк плательщика"),
            "payer_bank_swift": safe_get_string(row, "SWIFT Банка плательщика"),
            "payer_bank_address": safe_get_string(row, "Адрес банка плательщика"),
            "client_category": safe_get_string(row, "Категория клиента"),
            "payer_country": safe_get_string(row, "Страна отправителя")
        })
        normalized["swift_code"] = safe_get_string(row, "SWIFT Банка плательщика")
    else:  # outgoing
        normalized.update({
            "payer_name": safe_get_string(row, "Наименование плательщика (наш клиент)"),
            "payer_account": safe_get_string(row, "Номер счета плательщика"),
            "recipient": safe_get_string(row, "Получатель"),
            "recipient_bank": safe_get_string(row, "Банк получателя"),
            "recipient_bank_swift": safe_get_string(row, "SWIFT Банка получателя"),
            "recipient_bank_address": safe_get_string(row, "Адрес банка получателя"),
            "payment_details": safe_get_string(row, "Детали платежа"),
            "client_category": safe_get_string(row, "Категория клиента"),
            "recipient_country": safe_get_string(row, "Страна получателя")
        })
        normalized["swift_code"] = safe_get_string(row, "SWIFT Банка получателя")
    
    return normalized
