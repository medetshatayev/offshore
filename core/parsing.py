"""
Excel file parsing with Cyrillic header support.
Handles both incoming and outgoing transaction formats.
"""
from pathlib import Path
from typing import Any, Dict, Literal, Set

import pandas as pd

from core.exceptions import DataNotFoundError, ParsingError
from core.logger import setup_logger

logger = setup_logger(__name__)

# Expected columns for incoming transactions (Cyrillic headers)
INCOMING_COLUMNS: Set[str] = {
    "№п/п",
    "Наименование бенефициара (наш клиент)",
    "Категория клиента",
    "Страна резидентства",
    "Гражданство",
    "Номер счета бенефициара",
    "Дата валютирования",
    "Дата приема",
    "Сумма",
    "Сумма в тенге",
    "Валюта платежа",
    "Плательщик",
    "SWIFT Банка плательщика",
    "Город",
    "Банк плательщика",
    "Адрес банка плательщика",
    "Состояние",
    "Код страны",
    "Страна отправителя",
}

# Expected columns for outgoing transactions (Cyrillic headers)
OUTGOING_COLUMNS: Set[str] = {
    "№п/п",
    "Наименование плательщика (наш клиент)",
    "Категория клиента",
    "Страна резидентства",
    "Гражданство",
    "Номер счета плательщика",
    "Дата валютирования",
    "Дата приема",
    "Сумма",
    "Сумма в тенге",
    "Валюта платежа",
    "Получатель",
    "SWIFT Банка получателя",
    "Город",
    "Банк получателя",
    "Адрес банка получателя",
    "Детали платежа",
    "Состояние",
    "Код страны",
    "Страна получателя",
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
        DataNotFoundError: If file doesn't exist
        ParsingError: If file format is invalid
    """
    path = Path(file_path)
    if not path.exists():
        raise DataNotFoundError(
            f"File not found: {file_path}",
            details={"file_path": file_path}
        )
    
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
            raise ParsingError(
                "File contains no data after removing empty rows",
                details={"file_path": file_path, "direction": direction}
            )
        
        logger.info(f"Successfully parsed {len(df)} rows from {path.name}")
        
        # Validate expected columns exist
        expected_columns = INCOMING_COLUMNS if direction == "incoming" else OUTGOING_COLUMNS
        missing_cols = expected_columns - set(df.columns)
        
        if missing_cols:
            logger.warning(f"Missing expected columns: {missing_cols}")
            # Log available columns for debugging
            logger.debug(f"Available columns: {list(df.columns)}")
        
        return df
    
    except ParsingError:
        raise
    except Exception as e:
        logger.error(f"Failed to parse {file_path}: {str(e)}")
        raise ParsingError(
            f"Invalid Excel format for {direction} transactions",
            details={"file_path": file_path, "direction": direction, "error": str(e)}
        )


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
    df_columns = set(df.columns)
    
    stats = {
        "total_rows": len(df),
        "columns_found": len(df.columns),
        "columns_expected": len(expected_columns),
        "missing_columns": sorted(expected_columns - df_columns),
        "extra_columns": sorted(df_columns - expected_columns),
        "empty_amount_kzt": int(df["Сумма в тенге"].isna().sum()) if "Сумма в тенге" in df.columns else 0,
    }
    
    logger.info(f"Validation stats for {direction}: {stats}")
    
    return stats
