"""
Excel exporters that preserve original columns and add Результат column.
Handles both incoming and outgoing transaction outputs.
"""
from datetime import datetime
from pathlib import Path
from typing import Any, List

import pandas as pd

from core.config import get_settings
from core.exceptions import ExportError
from core.logger import setup_logger
from core.schema import OffshoreRiskResponse, LABEL_TRANSLATIONS

logger = setup_logger(__name__)
settings = get_settings()


def format_result_column(response: OffshoreRiskResponse) -> str:
    """
    Format the Результат column content from LLM response.
    
    Format: Итог: {label_ru} | Уверенность: {conf}% | Объяснение: {reasoning} | 
            Источники: {sources}
    
    Args:
        response: LLM classification response
    
    Returns:
        Formatted result string
    """
    try:
        # Translate label
        label_ru = LABEL_TRANSLATIONS.get(response.classification.label, response.classification.label)
        
        # Format confidence as percentage (with bounds checking)
        confidence_pct = int(max(0, min(1, response.classification.confidence)) * 100)
        
        # Build final result string
        result = (
            f"Итог: {label_ru} | "
            f"Уверенность: {confidence_pct}% | "
            f"Объяснение: {response.reasoning_short_ru}"
        )
        
        # Only add sources if they exist
        if response.sources and len(response.sources) > 0:
            sources_list = response.sources[:3]
            sources_str = "; ".join(sources_list)
            if len(response.sources) > 3:
                sources_str += f" (+{len(response.sources) - 3} more)"
            result += f" | Источники: {sources_str}"
        
        # Add error if present
        if response.llm_error:
            result += f" | ОШИБКА: {response.llm_error}"
        
        return result
    
    except Exception as e:
        logger.error(f"Error formatting result column: {e}")
        return f"ОШИБКА ФОРМАТИРОВАНИЯ: {str(e)}"


def export_to_excel(
    original_df: pd.DataFrame,
    responses: List[OffshoreRiskResponse],
    output_path: str,
    sheet_name: str
) -> str:
    """
    Export processed transactions to Excel with Результат column.
    Removes internal processing columns before export.
    
    Args:
        original_df: Original DataFrame (filtered, with all original columns)
        responses: List of LLM responses (same length as df)
        output_path: Output file path
        sheet_name: Sheet name (e.g., "Входящие операции")
    
    Returns:
        Path to created file
    
    Raises:
        ExportError: If export fails or data validation fails
    """
    if len(original_df) != len(responses):
        raise ExportError(
            f"DataFrame length ({len(original_df)}) doesn't match responses length ({len(responses)})",
            details={"df_length": len(original_df), "responses_length": len(responses)}
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
    
    except ExportError:
        raise
    except Exception as e:
        logger.error(f"Failed to export Excel: {e}")
        raise ExportError(
            f"Failed to export to Excel",
            details={"output_path": output_path, "error": str(e)}
        )


def create_output_filename(direction: str, base_path: str = None) -> str:
    """
    Create timestamped output filename.
    
    Args:
        direction: "incoming" or "outgoing"
        base_path: Base directory path (defaults to configured temp storage)
    
    Returns:
        Full output file path
    """
    if base_path is None:
        base_path = settings.temp_storage_path
    
    # Create directory if needed
    Path(base_path).mkdir(parents=True, exist_ok=True)
    
    # Generate timestamp
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    
    # Build filename
    filename = f"{direction}_transactions_processed_{timestamp}.xlsx"
    
    return str(Path(base_path) / filename)
