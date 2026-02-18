"""
Database module for offshore jurisdiction data storage.
Provides SQLite-based persistence for country lists.
"""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Generator, List, Optional

from core.config import get_settings
from core.logger import setup_logger

logger = setup_logger(__name__)


class Database:
    """SQLite database wrapper for offshore jurisdiction data."""
    
    def __init__(self) -> None:
        """Initialize database with settings."""
        self.settings = get_settings()
        self.db_path = self.settings.database_path

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """
        Context manager for database connections.
        
        Yields:
            Database connection with Row factory enabled.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def init_db(self) -> None:
        """Initialize database tables."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS countries (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
                logger.info("Database initialized successfully")
            except sqlite3.Error as e:
                logger.error(f"Database initialization failed: {e}")
                raise

    def add_country(self, name: str) -> None:
        """
        Add a country to the database.
        
        Args:
            name: Country name to add.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                now = datetime.now(timezone.utc)
                cursor.execute(
                    "INSERT OR IGNORE INTO countries (name, updated_at) VALUES (?, ?)",
                    (name, now)
                )
                conn.commit()
            except sqlite3.Error as e:
                logger.error(f"Failed to add country {name}: {e}")
                raise

    def get_all_countries(self) -> List[str]:
        """
        Get all country names from database.
        
        Returns:
            List of country names sorted alphabetically.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT name FROM countries ORDER BY name")
                rows = cursor.fetchall()
                return [row["name"] for row in rows]
            except sqlite3.Error as e:
                logger.error(f"Failed to get countries: {e}")
                return []


# Singleton database instance
_db: Optional[Database] = None


def get_db() -> Database:
    """
    Get or create database singleton instance.
    
    Returns:
        Database instance.
    """
    global _db
    if _db is None:
        _db = Database()
    return _db

