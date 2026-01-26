"""
Data normalization and metadata enrichment.
Handles currency conversion, amount cleaning, and transaction metadata.
"""
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

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
    Does NOT modify the original DataFrame with new columns.
    
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
    
    # Calculate normalized amounts temporarily
    amounts = df["Сумма в тенге"].apply(clean_amount_kzt)
    
    # Count before filtering
    before_count = len(df)
    
    # Filter by threshold using boolean indexing
    # mask is True where amount is valid AND >= threshold
    mask = amounts.notna() & (amounts >= threshold)
    
    df_filtered = df[mask].copy()
    after_count = len(df_filtered)
    filtered_out = before_count - after_count
    
    logger.info(
        f"Filtered transactions: {before_count} -> {after_count} "
        f"(removed {filtered_out} below {threshold:,.0f} KZT)"
    )
    
    return df_filtered


def safe_get_value(row: pd.Series, key: str, default: Any = None) -> Any:
    """Safely get value from pandas Series."""
    value = row.get(key, default)
    if pd.isna(value):
        return default
    return value


def safe_get_string(row: pd.Series, key: str, default: str = "") -> str:
    """Safely convert value to string."""
    value = safe_get_value(row, key, default)
    if value is None or value == "":
        return default
    return str(value)


def normalize_transaction(row: pd.Series, direction: str) -> Dict[str, Any]:
    """
    Normalize a single transaction row to a standard dictionary format.
    Re-calculates normalized amount to avoid adding columns to the source DF.
    
    Args:
        row: pandas Series representing a transaction
        direction: Transaction direction ("incoming" or "outgoing")
    
    Returns:
        Normalized transaction dictionary
    """
    # Re-calculate amount for the dict (cheap operation)
    amount_kzt = clean_amount_kzt(row.get("Сумма в тенге")) or 0.0
    
    # Common fields
    normalized = {
        "id": safe_get_string(row, "№ п/п" if direction == "outgoing" else "№п/п", "unknown"),
        "direction": direction,
        "amount_kzt": amount_kzt,
        "amount": safe_get_value(row, "Сумма"),
        "currency": safe_get_string(row, "Валюта платежа"),
        "value_date": safe_get_string(row, "Дата валютирования"),
        "acceptance_date": safe_get_string(row, "Дата документа" if direction == "incoming" else "Дата приема"),
        "country_residence": safe_get_string(row, "Страна резидентства бенефициара" if direction == "incoming" else "Страна резидентства плательщика"),
        "citizenship": safe_get_string(row, "Гражданство"),
        "city": safe_get_string(row, "Город банка плательщика" if direction == "incoming" else "Город банка"),
        "country_code": safe_get_string(row, "Код страны банка плательщика" if direction == "incoming" else "Код страны получателя"),
        "status": safe_get_string(row, "Состояние" if direction == "incoming" else "Состояние платежа"),
    }
    
    # Direction-specific fields
    if direction == "incoming":
        normalized.update({
            "beneficiary_name": safe_get_string(row, "Наименование бенефициара (наш клиент)"),
            "beneficiary_account": safe_get_string(row, "Номер счета бенефициара"),
            "beneficiary_address": safe_get_string(row, "Адрес бенефициара"),
            "beneficiary_bank_swift": safe_get_string(row, "SWIFT код Банка бенефициара"),
            "beneficiary_correspondent_swift": safe_get_string(row, "SWIFT код кор.банка бенефициара (Отправитель сообщения)"),
            "payer": safe_get_string(row, "Плательщик (Наименование)"),
            "payer_address": safe_get_string(row, "Адрес плательщика"),
            "payer_country": safe_get_string(row, "Страна резиденства плательщика"),
            "payer_bank": safe_get_string(row, "Наименование Банка плательщика"),
            "payer_bank_swift": safe_get_string(row, "SWIFT код Банка плательщика"),
            "payer_bank_address": safe_get_string(row, "Адрес банка плательщика"),
            "bank_country": safe_get_string(row, "Страна банка плательщика"),
            "payer_correspondent_swift": safe_get_string(row, "SWIFT код Корреспондента Банка Плательщика(отправителя)"),
            "payer_correspondent_name": safe_get_string(row, "Наименование Корреспондента Банка Плательщика(отправителя)"),
            "payer_correspondent_address": safe_get_string(row, "Адрес Корреспондента Банка Плательщика(отправителя)"),
            "intermediary_bank_1": safe_get_string(row, "Банк-посредник отправителя 1"),
            "intermediary_bank_2": safe_get_string(row, "Банк-посредник отправителя 2"),
            "intermediary_bank_3": safe_get_string(row, "Банк-посредник отправителя 3"),
            "payment_details": safe_get_string(row, "Назначение платежа"),
            "client_category": safe_get_string(row, "Категория клиента"),
            # Actual payer/recipient address fields (beneficial owners)
            "actual_payer_address": safe_get_string(row, "Адрес фактического плательщика"),
            "actual_payer_residence_country": safe_get_string(row, "Страна резиденства фактического плательщика"),
            "actual_recipient_address": safe_get_string(row, "Адрес фактического получателя"),
        })
        normalized["swift_code"] = safe_get_string(row, "SWIFT код Банка плательщика")
    else:  # outgoing
        normalized.update({
            "payer_name": safe_get_string(row, "Наименование плательщика (наш клиент)"),
            "payer_account": safe_get_string(row, "Номер счета плательщика"),
            "recipient": safe_get_string(row, "Получатель"),
            "recipient_address": safe_get_string(row, "Адрес получателя"),
            "recipient_bank": safe_get_string(row, "Наименование Банка получателя"),
            "recipient_bank_swift": safe_get_string(row, "SWIFT Банка получателя"),
            "recipient_bank_address": safe_get_string(row, "Адрес банка получателя"),
            "bank_country": safe_get_string(row, "Страна банка"),
            "payment_details": safe_get_string(row, "Назначение платежа"),
            "client_category": safe_get_string(row, "Категория клиента"),
            "recipient_country": safe_get_string(row, "Страна получателя")
        })
        normalized["swift_code"] = safe_get_string(row, "SWIFT Банка получателя")
    
    return normalized
