"""
Transaction processing service.

Encapsulates business logic for processing transactions through
the offshore risk detection pipeline.
"""
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from core.config import get_settings
from core.exceptions import FileProcessingError
from core.exporters import create_output_filename, export_to_excel
from core.logger import setup_logger
from core.normalize import filter_by_threshold, filter_by_payment_status, normalize_transaction
from core.parsing import parse_excel_file, validate_dataframe
from core.pg import get_pg_pool
from core.pg_logger import log_batch
from core.schema import OffshoreRiskResponse
from llm.classify import classify_batch, create_error_response

logger = setup_logger(__name__)


class TransactionService:
    """Service for processing transactions through the offshore risk detection pipeline."""
    
    def __init__(self):
        """Initialize transaction service."""
        self.settings = get_settings()
    
    async def process_transaction_batch(
        self,
        transactions: List[Dict[str, Any]],
        semaphore: asyncio.Semaphore,
        job_id: Optional[str] = None,
        direction: Optional[str] = None,
        original_filename: Optional[str] = None,
        executor: Optional[ThreadPoolExecutor] = None,
    ) -> List[OffshoreRiskResponse]:
        """
        Process all transactions by chunking them into batches.
        Logs each completed batch to PostgreSQL progressively.

        Args:
            transactions: List of normalized transaction dictionaries
            semaphore: Asyncio semaphore for concurrency control
            job_id: UUID of the processing job (for DB logging)
            direction: "incoming" or "outgoing" (for DB logging)
            original_filename: Source Excel filename (for DB logging)
            executor: Optional ThreadPoolExecutor for LLM calls

        Returns:
            List of classification responses
        """
        job_start = time.monotonic()
        total = len(transactions)
        batch_size = self.settings.batch_size
        pg_pool = get_pg_pool()

        # Create chunks
        chunks = [transactions[i:i + batch_size] for i in range(0, total, batch_size)]
        logger.info(f"Split {total} transactions into {len(chunks)} batches (size={batch_size})")

        all_results = []
        completed_batches = [0]

        async def process_chunk(chunk: List[Dict[str, Any]]) -> List[OffshoreRiskResponse]:
            batch_start = time.monotonic()
            async with semaphore:
                loop = asyncio.get_running_loop()
                llm_start = time.monotonic()
                # Run sync LLM call in executor; semaphore released after this block
                results = await loop.run_in_executor(executor, classify_batch, chunk)
                llm_ms = (time.monotonic() - llm_start) * 1000

            # Semaphore released — DB logging outside critical section
            completed_batches[0] += 1
            batch_num = completed_batches[0]
            logger.info(f"Processed batch {batch_num}/{len(chunks)} [llm={llm_ms:.0f}ms]")

            db_ms = 0.0
            if pg_pool is not None and job_id:
                db_start = time.monotonic()
                try:
                    await log_batch(
                        pool=pg_pool,
                        job_id=job_id,
                        direction=direction or "unknown",
                        original_filename=original_filename,
                        transactions=chunk,
                        responses=results,
                    )
                except Exception as db_err:
                    logger.warning(f"Batch DB log failed (non-fatal): {db_err}")
                db_ms = (time.monotonic() - db_start) * 1000

            batch_ms = (time.monotonic() - batch_start) * 1000
            logger.info(
                f"Batch {batch_num} timings: "
                f"llm={llm_ms:.0f}ms db={db_ms:.0f}ms total={batch_ms:.0f}ms"
            )
            return results
        
        # Process chunks concurrently (limited by semaphore)
        tasks = [process_chunk(chunk) for chunk in chunks]
        chunk_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Flatten results and handle errors
        for i, result in enumerate(chunk_results):
            if isinstance(result, Exception):
                logger.error(f"Batch {i} failed completely: {result}")
                chunk_txns = chunks[i]
                error_responses = [
                    create_error_response(txn, f"Batch processing failed: {str(result)}")
                    for txn in chunk_txns
                ]
                all_results.extend(error_responses)

                # Log error responses to PostgreSQL
                if pg_pool is not None and job_id:
                    try:
                        await log_batch(
                            pool=pg_pool,
                            job_id=job_id,
                            direction=direction or "unknown",
                            original_filename=original_filename,
                            transactions=chunk_txns,
                            responses=error_responses,
                        )
                    except Exception as db_err:
                        logger.warning(f"Error batch DB log failed (non-fatal): {db_err}")
            elif isinstance(result, list):
                all_results.extend(result)
            else:
                logger.error(f"Unexpected result type for batch {i}: {type(result)}")

        total_ms = (time.monotonic() - job_start) * 1000
        rows_per_sec = len(all_results) / (total_ms / 1000) if total_ms > 0 else 0
        logger.info(
            f"Job summary [{direction}]: total_rows={len(all_results)} "
            f"total_duration={total_ms:.0f}ms throughput={rows_per_sec:.1f} rows/sec"
        )

        return all_results
    
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
    
    async def process_file(
        self,
        file_path: str,
        direction: str,
        job_id: Optional[str] = None,
        original_filename: Optional[str] = None,
        semaphore: Optional[asyncio.Semaphore] = None,
        executor: Optional[ThreadPoolExecutor] = None,
    ) -> Dict[str, Any]:
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
            
            # 2. Filter by threshold (now returns df without extra columns)
            df_filtered = filter_by_threshold(df)
            logger.info(f"After threshold filter: {len(df_filtered)} transactions")

            # 2b. Filter by payment status (outgoing only)
            if direction == "outgoing":
                df_filtered = filter_by_payment_status(df_filtered)
                logger.info(f"After status filter: {len(df_filtered)} transactions")
            
            if len(df_filtered) == 0:
                logger.warning("No transactions meet the threshold criteria")
                return {
                    "output_path": None,
                    "stats": {**stats, "filtered_count": 0, "processed_count": 0},
                    "error": f"No transactions meet the {self.settings.amount_threshold_kzt:,.0f} KZT threshold"
                }
            
            # 3. Prepare transactions (normalize on the fly)
            transactions = []
            for idx, row in df_filtered.iterrows():
                # normalize_transaction now re-calculates amounts cleanly
                txn = normalize_transaction(row, direction)
                transactions.append(txn)
            
            logger.info(f"Prepared {len(transactions)} transactions for batch processing")
            
            # 4. Classify with LLM (batch processing)
            logger.info("Starting LLM batch classification...")

            if semaphore is None:
                semaphore = asyncio.Semaphore(self.settings.max_concurrent_llm_calls)

            responses = await self.process_transaction_batch(
                transactions, semaphore,
                job_id=job_id,
                direction=direction,
                original_filename=original_filename,
                executor=executor,
            )
            
            logger.info(f"Completed LLM classification for {len(responses)}/{len(transactions)} transactions")
            
            # 5. Export to Excel
            sheet_name = "Входящие операции" if direction == "incoming" else "Исходящие операции"
            output_path = create_output_filename(direction, self.settings.temp_storage_path)
            
            # export_to_excel now receives clean df without internal columns
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

