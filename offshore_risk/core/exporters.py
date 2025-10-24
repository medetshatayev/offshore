"""
Excel exporters that preserve original columns and add Результат column.
Handles both incoming and outgoing transaction outputs.
"""
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
import pandas as pd
from core.logger import setup_logger
from core.schema import OffshoreRiskResponse, LABEL_TRANSLATIONS

logger = setup_logger(__name__)


def format_result_column(response: OffshoreRiskResponse) -> str:
    """
    Format the Результат column content from LLM response.
    
    Format: Итог: {label_ru} | Уверенность: {conf}% | Объяснение: {reasoning} | 
            Совпадения: {signals} | Источники: {sources}
    
    Args:
        response: LLM classification response
    
    Returns:
        Formatted result string
    """
    # Translate label
    label_ru = LABEL_TRANSLATIONS.get(response.classification.label, response.classification.label)
    
    # Format confidence as percentage
    confidence_pct = int(response.classification.confidence * 100)
    
    # Build signals summary
    signals_parts = []
    
    if response.signals.swift_country_code:
        signals_parts.append(f"SWIFT: {response.signals.swift_country_code}")
    
    if response.signals.country_code_match.value:
        signals_parts.append(
            f"Код страны: {response.signals.country_code_match.value} "
            f"({response.signals.country_code_match.score:.2f})"
        )
    
    if response.signals.country_name_match.value:
        signals_parts.append(
            f"Страна: {response.signals.country_name_match.value} "
            f"({response.signals.country_name_match.score:.2f})"
        )
    
    if response.signals.city_match.value:
        signals_parts.append(
            f"Город: {response.signals.city_match.value} "
            f"({response.signals.city_match.score:.2f})"
        )
    
    signals_str = "; ".join(signals_parts) if signals_parts else "Нет совпадений"
    
    # Format sources
    sources_str = "; ".join(response.sources) if response.sources else "Нет источников"
    
    # Build final result string
    result = (
        f"Итог: {label_ru} | "
        f"Уверенность: {confidence_pct}% | "
        f"Объяснение: {response.reasoning_short_ru} | "
        f"Совпадения: {signals_str} | "
        f"Источники: {sources_str}"
    )
    
    # Add error if present
    if response.llm_error:
        result += f" | ОШИБКА: {response.llm_error}"
    
    return result


def export_to_excel(
    original_df: pd.DataFrame,
    responses: List[OffshoreRiskResponse],
    output_path: str,
    sheet_name: str
) -> str:
    """
    Export processed transactions to Excel with Результат column.
    
    Args:
        original_df: Original DataFrame (filtered, with all original columns)
        responses: List of LLM responses (same length as df)
        output_path: Output file path
        sheet_name: Sheet name (e.g., "Входящие операции")
    
    Returns:
        Path to created file
    
    Raises:
        ValueError: If responses length doesn't match DataFrame
    """
    if len(original_df) != len(responses):
        raise ValueError(
            f"DataFrame length ({len(original_df)}) doesn't match "
            f"responses length ({len(responses)})"
        )
    
    logger.info(f"Exporting {len(original_df)} transactions to {output_path}")
    
    # Create output DataFrame (copy original)
    output_df = original_df.copy()
    
    # Add Результат column
    result_values = [format_result_column(resp) for resp in responses]
    output_df["Результат"] = result_values
    
    # Ensure output directory exists
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Write to Excel
    try:
        with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
            output_df.to_excel(writer, sheet_name=sheet_name, index=False)
            
            # Get workbook and worksheet for formatting
            workbook = writer.book
            worksheet = writer.sheets[sheet_name]
            
            # Format Результат column to wrap text
            wrap_format = workbook.add_format({"text_wrap": True, "valign": "top"})
            result_col_idx = len(output_df.columns) - 1  # Last column
            worksheet.set_column(result_col_idx, result_col_idx, 80, wrap_format)
            
            # Auto-fit other columns (approximate)
            for idx, col in enumerate(output_df.columns[:-1]):  # Exclude last (Результат)
                max_len = max(
                    output_df[col].astype(str).map(len).max(),
                    len(str(col))
                )
                worksheet.set_column(idx, idx, min(max_len + 2, 50))
        
        logger.info(f"Successfully exported to {output_path}")
        return output_path
    
    except Exception as e:
        logger.error(f"Failed to export Excel: {e}")
        raise


def create_output_filename(direction: str, base_path: str = None) -> str:
    """
    Create timestamped output filename.
    
    Args:
        direction: "incoming" or "outgoing"
        base_path: Base directory path (defaults to TEMP_STORAGE_PATH or /tmp)
    
    Returns:
        Full output file path
    """
    if base_path is None:
        base_path = os.getenv("TEMP_STORAGE_PATH", "/tmp/offshore_risk")
    
    # Create directory if needed
    Path(base_path).mkdir(parents=True, exist_ok=True)
    
    # Generate timestamp
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    
    # Build filename
    filename = f"{direction}_transactions_processed_{timestamp}.xlsx"
    
    return str(Path(base_path) / filename)
