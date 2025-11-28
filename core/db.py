import sqlite3
from pathlib import Path
from typing import List, Optional, Tuple
from datetime import datetime

from core.config import get_settings
from core.logger import setup_logger

logger = setup_logger(__name__)

class Database:
    def __init__(self):
        self.settings = get_settings()
        self.db_path = self.settings.database_path

    def get_connection(self) -> sqlite3.Connection:
        """Create a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        """Initialize database tables."""
        conn = self.get_connection()
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
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise
        finally:
            conn.close()

    def add_country(self, name: str) -> None:
        """Add a country to the database."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            now = datetime.utcnow()
            cursor.execute(
                "INSERT OR IGNORE INTO countries (name, updated_at) VALUES (?, ?)",
                (name, now)
            )
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to add country {name}: {e}")
            raise
        finally:
            conn.close()

    def get_all_countries(self) -> List[str]:
        """Get all country names."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT name FROM countries ORDER BY name")
            rows = cursor.fetchall()
            return [row["name"] for row in rows]
        except Exception as e:
            logger.error(f"Failed to get countries: {e}")
            return []
        finally:
            conn.close()

# Global DB instance
_db: Optional[Database] = None

def get_db() -> Database:
    global _db
    if _db is None:
        _db = Database()
    return _db

