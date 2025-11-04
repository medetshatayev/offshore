"""
Transaction processing service.
Encapsulates business logic for processing transactions.
"""
import asyncio
from typing import Any, Dict, List, Tuple

import pandas as pd

from core.config import get_settings
from core.exceptions import FileProcessingError, ValidationError
from core.exporters import export_to_excel, create_output_filename
from core.logger import setup_logger
from core.matching import (
    aggregate_matching_signals,
    fuzzy_match_city,
    fuzzy_match_country_code,
    fuzzy_match_country_name,
)
from core.normalize import add_metadata, filter_by_threshold, normalize_transaction
from core.parsing import parse_excel_file, validate_dataframe
from core.schema import OffshoreRiskResponse
from core.swift import extract_country_from_swift
from llm.classify import classify_transaction, create_error_response

logger = setup_logger(__name__)


class TransactionService:
    """Service for processing transactions through the offshore risk detection pipeline."""
    
    def __init__(self):
        """Initialize transaction service."""
        self.settings = get_settings()
    
    def extract_transaction_signals(self, row: pd.Series, direction: str) -> Dict[str, Any]:
        """
        Extract matching signals for a single transaction.
        
        Args:
            row: Transaction row from DataFrame
            direction: Transaction direction ("incoming" or "outgoing")
        
        Returns:
            Transaction dictionary with normalized data and signals
        """
        # Normalize transaction
        txn = normalize_transaction(row, direction)
        
        # Extract SWIFT country
        swift_country = extract_country_from_swift(txn.get("swift_code"))
        
        # Fuzzy matching
        country_code_match = fuzzy_match_country_code(txn.get("country_code"))
        country_name_to_match = txn.get("payer_country") if direction == "incoming" else txn.get("recipient_country")
        country_name_match = fuzzy_match_country_name(country_name_to_match)
        city_match = fuzzy_match_city(txn.get("city"))
        
        # Aggregate signals
        signals = aggregate_matching_signals(
            swift_country,
            country_code_match,
            country_name_match,
            city_match
        )
        
        txn["signals"] = signals
        return txn
    
    async def process_transaction_batch(
        self,
        transactions: List[Dict[str, Any]],
        semaphore: asyncio.Semaphore
    ) -> List[OffshoreRiskResponse]:
        """
        Process a batch of transactions with concurrency control.
        
        Args:
            transactions: List of normalized transaction dictionaries
            semaphore: Asyncio semaphore for concurrency control
        
        Returns:
            List of classification responses
        """
        total = len(transactions)
        completed = [0]  # Use list to allow modification in nested function
        
        async def process_single(txn: Dict[str, Any], idx: int) -> OffshoreRiskResponse:
            async with semaphore:
                # Run LLM classification in thread pool (since it's synchronous)
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, classify_transaction, txn)
                completed[0] += 1
                # Log progress every 10 transactions
                if completed[0] % 10 == 0 or completed[0] == total:
                    logger.info(f"Progress: {completed[0]}/{total} transactions processed")
                return result
        
        tasks = [process_single(txn, i) for i, txn in enumerate(transactions)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Convert exceptions to error responses
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Transaction {i} failed: {result}")
                processed_results.append(
                    create_error_response(transactions[i], str(result))
                )
            else:
                processed_results.append(result)
        
        return processed_results
    
    def build_classification_statistics(self, responses: List[OffshoreRiskResponse]) -> Dict[str, int]:
        """
        Build classification statistics from LLM responses.
        
        Args:
            responses: List of classification responses
        
        Returns:
            Dictionary with counts per classification label
        """
        classification_counts = {}
        for resp in responses:
            label = resp.classification.label
            classification_counts[label] = classification_counts.get(label, 0) + 1
        return classification_counts
    
    async def process_file(self, file_path: str, direction: str) -> Dict[str, Any]:
        """
        Process a single Excel file through the full pipeline.
        
        Args:
            file_path: Path to Excel file
            direction: "incoming" or "outgoing"
        
        Returns:
            Dictionary with output_path and statistics
        
        Raises:
            FileProcessingError: If file processing fails
        """
        try:
            logger.info(f"Processing {direction} file: {file_path}")
            
            # 1. Parse Excel
            df = parse_excel_file(file_path, direction)
            stats = validate_dataframe(df, direction)
            logger.info(f"Parsed {len(df)} transactions")
            
            # 2. Filter by threshold
            df_filtered = filter_by_threshold(df)
            logger.info(f"After filtering: {len(df_filtered)} transactions")
            
            if len(df_filtered) == 0:
                logger.warning("No transactions meet the threshold criteria")
                return {
                    "output_path": None,
                    "stats": {**stats, "filtered_count": 0, "processed_count": 0},
                    "error": f"No transactions meet the {self.settings.amount_threshold_kzt:,.0f} KZT threshold"
                }
            
            # 3. Add metadata
            df_filtered = add_metadata(df_filtered, direction)
            
            # 4. Process each transaction: normalize -> extract signals
            transactions_with_signals = [
                self.extract_transaction_signals(row, direction)
                for idx, row in df_filtered.iterrows()
            ]
            
            logger.info(f"Prepared {len(transactions_with_signals)} transactions with signals")
            
            # 5. Classify with LLM (with concurrency control)
            logger.info("Starting LLM classification (this may take a while)...")
            
            # Create semaphore for concurrency control
            semaphore = asyncio.Semaphore(self.settings.max_concurrent_llm_calls)
            
            # Run async processing with progress logging
            total = len(transactions_with_signals)
            logger.info(f"Starting LLM classification for {total} transactions in {direction} direction...")
            
            responses = await self.process_transaction_batch(transactions_with_signals, semaphore)
            
            logger.info(f"Completed LLM classification for {len(responses)}/{total} transactions in {direction} direction")
            
            # 6. Export to Excel
            sheet_name = "Входящие операции" if direction == "incoming" else "Исходящие операции"
            output_path = create_output_filename(direction, self.settings.temp_storage_path)
            
            export_to_excel(df_filtered, responses, output_path, sheet_name)
            
            # Build statistics
            classification_counts = self.build_classification_statistics(responses)
            
            return {
                "output_path": output_path,
                "stats": {
                    **stats,
                    "filtered_count": len(df_filtered),
                    "processed_count": len(responses),
                    "classifications": classification_counts
                }
            }
        
        except Exception as e:
            logger.error(f"File processing failed for {file_path}: {e}", exc_info=True)
            raise FileProcessingError(
                f"Failed to process {direction} file",
                details={"file_path": file_path, "error": str(e)}
            )
    
    async def process_files(
        self,
        incoming_path: str,
        outgoing_path: str
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Process both incoming and outgoing files.
        
        Args:
            incoming_path: Path to incoming transactions file
            outgoing_path: Path to outgoing transactions file
        
        Returns:
            Tuple of (incoming_result, outgoing_result)
        """
        # Process incoming file
        incoming_result = await self.process_file(incoming_path, "incoming")
        
        # Process outgoing file
        outgoing_result = await self.process_file(outgoing_path, "outgoing")
        
        return incoming_result, outgoing_result
