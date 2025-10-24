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
    if pd.isna(value):
        return None
    
    # Convert to string and clean
    amount_str = str(value).strip()
    
    # Remove spaces and common thousands separators
    amount_str = amount_str.replace(" ", "").replace(",", "").replace("\xa0", "")
    
    # Try to convert to float
    try:
        return float(amount_str)
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
    # Common fields
    normalized = {
        "id": row.get("№п/п"),
        "direction": direction,
        "amount_kzt": row.get("amount_kzt_normalized"),
        "amount": row.get("Сумма"),
        "currency": row.get("Валюта платежа"),
        "value_date": str(row.get("Дата валютирования", "")),
        "acceptance_date": str(row.get("Дата приема", "")),
        "country_residence": row.get("Страна резидентства"),
        "citizenship": row.get("Гражданство"),
        "city": row.get("Город"),
        "country_code": row.get("Код страны"),
        "recipient_country": row.get("Страна получателя"),
        "status": row.get("Состояние"),
        "processed_at": row.get("processed_at")
    }
    
    # Direction-specific fields
    if direction == "incoming":
        normalized.update({
            "beneficiary_name": row.get("Наименование бенефициара"),
            "beneficiary_account": row.get("Номер счета бенефициара"),
            "payer": row.get("Плательщик"),
            "payer_bank": row.get("Банк плательщика"),
            "payer_bank_swift": row.get("SWIFT Банка плательщика"),
            "payer_bank_address": row.get("Адрес банка плательщика"),
            "client_category": row.get("Категория клиента")
        })
        normalized["swift_code"] = row.get("SWIFT Банка плательщика")
    else:  # outgoing
        normalized.update({
            "payer_name": row.get("Наименование плательщика"),
            "payer_account": row.get("Номер счета плательщика"),
            "recipient": row.get("Получатель"),
            "recipient_bank": row.get("Банк получателя"),
            "recipient_bank_swift": row.get("SWIFT Банка получателя"),
            "recipient_bank_address": row.get("Адрес банка получателя"),
            "payment_details": row.get("Детали платежа"),
            "client_category": row.get("Категория клиента")
        })
        normalized["swift_code"] = row.get("SWIFT Банка получателя")
    
    return normalized
