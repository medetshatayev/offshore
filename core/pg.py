"""
PostgreSQL connection pool manager using asyncpg.

Provides a singleton connection pool for transaction logging
to the compliance database.
"""
from typing import Optional

import asyncpg

from core.config import get_settings
from core.logger import setup_logger

logger = setup_logger(__name__)

_pool: Optional[asyncpg.Pool] = None


async def init_pg_pool() -> asyncpg.Pool:
    """
    Initialize the PostgreSQL connection pool singleton.

    Uses settings from core.config for connection parameters.

    Returns:
        asyncpg.Pool instance

    Raises:
        Exception: If connection to PostgreSQL fails
    """
    global _pool
    if _pool is not None:
        return _pool

    settings = get_settings()
    logger.info(
        f"Connecting to PostgreSQL at "
        f"{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    )

    _pool = await asyncpg.create_pool(
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password,
        min_size=settings.postgres_min_pool,
        max_size=settings.postgres_max_pool,
    )

    logger.info("PostgreSQL connection pool created successfully")
    return _pool


def get_pg_pool() -> Optional[asyncpg.Pool]:
    """
    Get the current PostgreSQL connection pool.

    Returns:
        asyncpg.Pool if initialized, None otherwise
    """
    return _pool


async def close_pg_pool() -> None:
    """Close the PostgreSQL connection pool gracefully."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("PostgreSQL connection pool closed")


async def init_transaction_logs_table() -> None:
    """
    Create the transaction_logs table and indexes if they don't exist.

    Safe to call repeatedly (uses IF NOT EXISTS).
    """
    pool = get_pg_pool()
    if pool is None:
        logger.warning("PostgreSQL pool not initialized, skipping table creation")
        return

    create_table_sql = """
    CREATE TABLE IF NOT EXISTS transaction_logs (
        id              BIGSERIAL       PRIMARY KEY,
        job_id          UUID            NOT NULL,
        direction       VARCHAR(10)     NOT NULL,
        transaction_id  TEXT,
        amount_kzt      NUMERIC(18,2),
        currency        VARCHAR(10),
        classification  VARCHAR(30)     NOT NULL,
        confidence      REAL,
        reasoning_ru    TEXT,
        sources         JSONB           DEFAULT '[]'::jsonb,
        llm_error       TEXT,
        raw_transaction JSONB           NOT NULL,
        result_text     TEXT,
        original_filename TEXT,
        created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
    );
    """

    create_indexes_sql = [
        "CREATE INDEX IF NOT EXISTS idx_txlog_job_id ON transaction_logs (job_id);",
        "CREATE INDEX IF NOT EXISTS idx_txlog_classification ON transaction_logs (classification);",
        "CREATE INDEX IF NOT EXISTS idx_txlog_created_at ON transaction_logs (created_at);",
    ]

    async with pool.acquire() as conn:
        await conn.execute(create_table_sql)
        for idx_sql in create_indexes_sql:
            await conn.execute(idx_sql)

    logger.info("transaction_logs table and indexes verified/created")
