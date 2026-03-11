"""
PostgreSQL transaction logger.

Logs every processed transaction (with LLM results) to the
transaction_logs table in the compliance database.

Failures are caught and logged — they never break the processing pipeline.
"""
import json
from typing import Any, Dict, List, Optional

import asyncpg

from core.exporters import format_result_column
from core.logger import setup_logger
from core.schema import OffshoreRiskResponse

logger = setup_logger(__name__)


def _serialize_transaction(txn: Dict[str, Any]) -> str:
    """
    Serialize a normalized transaction dict to JSON string for JSONB storage.

    Handles non-serializable types (e.g. Timestamp, NaN) gracefully.
    """
    def _default(obj):
        # pandas Timestamps, dates, etc.
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        # numpy/pandas NaN → None
        try:
            import math
            if isinstance(obj, float) and math.isnan(obj):
                return None
        except (TypeError, ValueError):
            pass
        return str(obj)

    return json.dumps(txn, default=_default, ensure_ascii=False)


async def log_batch(
    pool: asyncpg.Pool,
    job_id: str,
    direction: str,
    original_filename: Optional[str],
    transactions: List[Dict[str, Any]],
    responses: List[OffshoreRiskResponse],
) -> None:
    """
    Log a batch of processed transactions to PostgreSQL.

    Each transaction + its LLM response becomes one row in transaction_logs.
    On failure, logs a warning but does NOT raise — the processing pipeline
    must not be interrupted by database issues.

    Args:
        pool: asyncpg connection pool
        job_id: UUID of the processing job
        direction: "incoming" or "outgoing"
        original_filename: Source Excel filename (for traceability)
        transactions: List of normalized transaction dicts (from normalize_transaction)
        responses: Corresponding LLM classification responses (same length)
    """
    if pool is None:
        logger.warning("PostgreSQL pool is None — skipping transaction log for batch")
        return

    try:
        # Build rows for bulk insert
        rows = []
        for i, txn in enumerate(transactions):
            # Match response by index; fall back to error placeholder
            if i < len(responses):
                resp = responses[i]
            else:
                resp = OffshoreRiskResponse(
                    transaction_id=txn.get("id"),
                    direction=direction,
                    classification={"label": "OFFSHORE_SUSPECT", "confidence": 0.0},
                    reasoning_short_ru="Ответ LLM отсутствует для данной транзакции",
                    llm_error="No LLM response mapped to this transaction",
                )

            result_text = format_result_column(resp)

            rows.append((
                job_id,                                          # job_id (UUID text)
                direction,                                       # direction
                txn.get("id"),                                   # transaction_id
                txn.get("amount_kzt"),                           # amount_kzt
                txn.get("currency"),                             # currency
                resp.classification.label,                       # classification
                resp.classification.confidence,                  # confidence
                resp.reasoning_short_ru,                         # reasoning_ru
                json.dumps(resp.sources, ensure_ascii=False),    # sources (JSONB)
                resp.llm_error,                                  # llm_error
                _serialize_transaction(txn),                     # raw_transaction (JSONB)
                result_text,                                     # result_text
                original_filename,                               # original_filename
            ))

        # Bulk insert using executemany for efficiency
        insert_sql = """
            INSERT INTO transaction_logs (
                job_id, direction, transaction_id,
                amount_kzt, currency,
                classification, confidence, reasoning_ru,
                sources, llm_error,
                raw_transaction, result_text, original_filename
            ) VALUES (
                $1::uuid, $2, $3,
                $4, $5,
                $6, $7, $8,
                $9::jsonb, $10,
                $11::jsonb, $12, $13
            )
        """

        async with pool.acquire() as conn:
            await conn.executemany(insert_sql, rows)

        logger.debug(
            f"Logged {len(rows)} transactions to PostgreSQL "
            f"(job={job_id}, direction={direction})"
        )

    except Exception as e:
        logger.error(
            f"Failed to log batch to PostgreSQL: {e} "
            f"(job={job_id}, direction={direction}, count={len(transactions)})",
            exc_info=True,
        )
        # Intentionally swallowed — DB failure must not break the pipeline
