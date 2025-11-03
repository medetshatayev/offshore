"""
Data normalization and metadata enrichment.
Handles currency conversion, amount cleaning, and transaction metadata.
"""
import os
from datetime import datetime
from typing import Any, Dict, Optional

import pandas as pd

from core.logger import setup_logger

logger = setup_logger(__name__)

# Amount threshold from env or default
AMOUNT_THRESHOLD_KZT = float(os.getenv("AMOUNT_THRESHOLD_KZT", "5000000"))


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


def filter_by_threshold(df: pd.DataFrame) -> pd.DataFrame:
    """
    Filter transactions by KZT amount threshold.
    
    Args:
        df: DataFrame with 'Сумма в тенге' column
    
    Returns:
        Filtered DataFrame with only transactions >= threshold
    """
    if "Сумма в тенге" not in df.columns:
        logger.error("Column 'Сумма в тенге' not found in DataFrame")
        return df
    
    # Create normalized amount column
    df["amount_kzt_normalized"] = df["Сумма в тенге"].apply(clean_amount_kzt)
    
    # Count before filtering
    before_count = len(df)
    
    # Filter by threshold
    df_filtered = df[
        df["amount_kzt_normalized"].notna() & 
        (df["amount_kzt_normalized"] >= AMOUNT_THRESHOLD_KZT)
    ].copy()
    
    after_count = len(df_filtered)
    filtered_out = before_count - after_count
    
    logger.info(
        f"Filtered transactions: {before_count} -> {after_count} "
        f"(removed {filtered_out} below {AMOUNT_THRESHOLD_KZT:,.0f} KZT)"
    )
    
    return df_filtered


def add_metadata(
    df: pd.DataFrame,
    direction: str
) -> pd.DataFrame:
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


def normalize_transaction(
    row: pd.Series,
    direction: str
) -> Dict[str, Any]:
    """
    Normalize a single transaction row to a standard dictionary format.
    
    Args:
        row: pandas Series representing a transaction
        direction: Transaction direction
    
    Returns:
        Normalized transaction dictionary
    """
    def get_value_or_default(key: str, default: Any = None) -> Any:
        """Safely get value from row, handling NaN and None."""
        value = row.get(key, default)
        if pd.isna(value):
            return default
        return value
    
    def get_string_or_default(key: str, default: str = "") -> str:
        """Safely convert value to string, returning default if empty or None."""
        value = get_value_or_default(key, default)
        if value is None or value == "":
            return default
        return str(value)
    
    # Common fields
    normalized = {
        "id": get_string_or_default("№п/п", "unknown"),
        "direction": direction,
        "amount_kzt": get_value_or_default("amount_kzt_normalized", 0.0),
        "amount": get_value_or_default("Сумма"),
        "currency": get_string_or_default("Валюта платежа"),
        "value_date": get_string_or_default("Дата валютирования"),
        "acceptance_date": get_string_or_default("Дата приема"),
        "country_residence": get_string_or_default("Страна резидентства"),
        "citizenship": get_string_or_default("Гражданство"),
        "city": get_string_or_default("Город"),
        "country_code": get_string_or_default("Код страны"),
        "status": get_string_or_default("Состояние"),
        "processed_at": get_string_or_default("processed_at")
    }
    
    # Direction-specific fields
    if direction == "incoming":
        normalized.update({
            "beneficiary_name": get_string_or_default("Наименование бенефициара (наш клиент)"),
            "beneficiary_account": get_string_or_default("Номер счета бенефициара"),
            "payer": get_string_or_default("Плательщик"),
            "payer_bank": get_string_or_default("Банк плательщика"),
            "payer_bank_swift": get_string_or_default("SWIFT Банка плательщика"),
            "payer_bank_address": get_string_or_default("Адрес банка плательщика"),
            "client_category": get_string_or_default("Категория клиента"),
            "payer_country": get_string_or_default("Страна отправителя")
        })
        normalized["swift_code"] = get_string_or_default("SWIFT Банка плательщика")
    else:  # outgoing
        normalized.update({
            "payer_name": get_string_or_default("Наименование плательщика (наш клиент)"),
            "payer_account": get_string_or_default("Номер счета плательщика"),
            "recipient": get_string_or_default("Получатель"),
            "recipient_bank": get_string_or_default("Банк получателя"),
            "recipient_bank_swift": get_string_or_default("SWIFT Банка получателя"),
            "recipient_bank_address": get_string_or_default("Адрес банка получателя"),
            "payment_details": get_string_or_default("Детали платежа"),
            "client_category": get_string_or_default("Категория клиента"),
            "recipient_country": get_string_or_default("Страна получателя")
        })
        normalized["swift_code"] = get_string_or_default("SWIFT Банка получателя")
    
    return normalized
