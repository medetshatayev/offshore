"""
Data normalization and metadata enrichment.
Handles currency conversion, amount cleaning, and transaction metadata.
"""
import os
import re
from datetime import datetime
from typing import Optional, Dict, Any
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
    def safe_get(key: str, default: Any = None) -> Any:
        """Safely get value from row, handling NaN and None."""
        value = row.get(key, default)
        if pd.isna(value):
            return default
        return value
    
    def safe_str(key: str, default: str = "") -> str:
        """Safely convert value to string."""
        value = safe_get(key, default)
        if value is None or value == "":
            return default
        return str(value)
    
    # Common fields
    normalized = {
        "id": safe_str("№п/п", "unknown"),
        "direction": direction,
        "amount_kzt": safe_get("amount_kzt_normalized", 0.0),
        "amount": safe_get("Сумма"),
        "currency": safe_str("Валюта платежа"),
        "value_date": safe_str("Дата валютирования"),
        "acceptance_date": safe_str("Дата приема"),
        "country_residence": safe_str("Страна резидентства"),
        "citizenship": safe_str("Гражданство"),
        "city": safe_str("Город"),
        "country_code": safe_str("Код страны"),
        "status": safe_str("Состояние"),
        "processed_at": safe_str("processed_at")
    }
    
    # Direction-specific fields
    if direction == "incoming":
        normalized.update({
            "beneficiary_name": safe_str("Наименование бенефициара (наш клиент)"),
            "beneficiary_account": safe_str("Номер счета бенефициара"),
            "payer": safe_str("Плательщик"),
            "payer_bank": safe_str("Банк плательщика"),
            "payer_bank_swift": safe_str("SWIFT Банка плательщика"),
            "payer_bank_address": safe_str("Адрес банка плательщика"),
            "client_category": safe_str("Категория клиента"),
            "payer_country": safe_str("Страна отправителя")
        })
        normalized["swift_code"] = safe_str("SWIFT Банка плательщика")
    else:  # outgoing
        normalized.update({
            "payer_name": safe_str("Наименование плательщика (наш клиент)"),
            "payer_account": safe_str("Номер счета плательщика"),
            "recipient": safe_str("Получатель"),
            "recipient_bank": safe_str("Банк получателя"),
            "recipient_bank_swift": safe_str("SWIFT Банка получателя"),
            "recipient_bank_address": safe_str("Адрес банка получателя"),
            "payment_details": safe_str("Детали платежа"),
            "client_category": safe_str("Категория клиента"),
            "recipient_country": safe_str("Страна получателя")
        })
        normalized["swift_code"] = safe_str("SWIFT Банка получателя")
    
    return normalized
