"""
Excel file parsing with Cyrillic header support.
Handles both incoming and outgoing transaction formats.
"""
from pathlib import Path
from typing import Any, Dict, Literal

import pandas as pd

from core.logger import setup_logger

logger = setup_logger(__name__)

# Column mapping for incoming transactions
INCOMING_COLUMNS = {
    "№п/п": "id",
    "Наименование бенефициара (наш клиент)": "beneficiary_name",
    "Категория клиента": "client_category",
    "Страна резидентства": "country_residence",
    "Гражданство": "citizenship",
    "Номер счета бенефициара": "beneficiary_account",
    "Дата валютирования": "value_date",
    "Дата приема": "acceptance_date",
    "Сумма": "amount",
    "Сумма в тенге": "amount_kzt",
    "Валюта платежа": "currency",
    "Плательщик": "payer",
    "SWIFT Банка плательщика": "payer_bank_swift",
    "Город": "city",
    "Банк плательщика": "payer_bank",
    "Адрес банка плательщика": "payer_bank_address",
    "Состояние": "status",
    "Код страны": "country_code",
    "Страна отправителя": "payer_country"
}

# Column mapping for outgoing transactions
OUTGOING_COLUMNS = {
    "№п/п": "id",
    "Наименование плательщика (наш клиент)": "beneficiary_name",
    "Категория клиента": "client_category",
    "Страна резидентства": "country_residence",
    "Гражданство": "citizenship",
    "Номер счета плательщика": "beneficiary_account",
    "Дата валютирования": "value_date",
    "Дата приема": "acceptance_date",
    "Сумма": "amount",
    "Сумма в тенге": "amount_kzt",
    "Валюта платежа": "currency",
    "Получатель": "recipient",
    "SWIFT Банка получателя": "recipient_bank_swift",
    "Город": "city",
    "Банк получателя": "recipient_bank",
    "Адрес банка получателя": "recipient_bank_address",
    "Детали платежа": "payment_details",
    "Состояние": "status",
    "Код страны": "country_code",
    "Страна получателя": "recipient_country"
}


def parse_excel_file(
    file_path: str,
    direction: Literal["incoming", "outgoing"]
) -> pd.DataFrame:
    """
    Parse Excel file with Cyrillic headers.
    
    Args:
        file_path: Path to Excel file
        direction: Type of transactions ("incoming" or "outgoing")
    
    Returns:
        DataFrame with parsed transactions
    
    Raises:
        ValueError: If file format is invalid
        FileNotFoundError: If file doesn't exist
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    # Determine skiprows and engine based on direction and file extension
    skiprows = 4 if direction == "incoming" else 5
    engine = "xlrd" if path.suffix.lower() == ".xls" else "openpyxl"
    
    logger.info(f"Parsing {direction} transactions from {path.name} (skiprows={skiprows}, engine={engine})")
    
    try:
        # Read with appropriate engine
        df = pd.read_excel(
            file_path,
            skiprows=skiprows,
            engine=engine
        )
        
        # Remove completely empty rows
        df = df.dropna(how="all")
        
        # Check if DataFrame is empty after cleanup
        if len(df) == 0:
            raise ValueError(f"File contains no data after removing empty rows")
        
        logger.info(f"Successfully parsed {len(df)} rows from {path.name}")
        
        # Validate expected columns exist
        expected_columns = INCOMING_COLUMNS if direction == "incoming" else OUTGOING_COLUMNS
        missing_cols = set(expected_columns.keys()) - set(df.columns)
        
        if missing_cols:
            logger.warning(f"Missing expected columns: {missing_cols}")
            # Log available columns for debugging
            logger.debug(f"Available columns: {list(df.columns)}")
        
        return df
    
    except Exception as e:
        logger.error(f"Failed to parse {file_path}: {str(e)}")
        raise ValueError(f"Invalid Excel format for {direction} transactions: {str(e)}")


def validate_dataframe(
    df: pd.DataFrame,
    direction: Literal["incoming", "outgoing"]
) -> Dict[str, Any]:
    """
    Validate DataFrame structure and return statistics.
    
    Args:
        df: DataFrame to validate
        direction: Type of transactions
    
    Returns:
        Dictionary with validation results and statistics
    """
    expected_columns = INCOMING_COLUMNS if direction == "incoming" else OUTGOING_COLUMNS
    
    stats = {
        "total_rows": len(df),
        "columns_found": len(df.columns),
        "columns_expected": len(expected_columns),
        "missing_columns": list(set(expected_columns.keys()) - set(df.columns)),
        "extra_columns": list(set(df.columns) - set(expected_columns.keys())),
        "empty_amount_kzt": int(df["Сумма в тенге"].isna().sum()) if "Сумма в тенге" in df.columns else 0
    }
    
    logger.info(f"Validation stats for {direction}: {stats}")
    
    return stats
