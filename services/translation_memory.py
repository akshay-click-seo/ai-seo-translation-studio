"""
services/translation_memory.py — SQLite-backed Translation Memory (TM).

Behaviour:
  - Before calling the API, look up the source text hash in the DB.
  - If found (cache hit), return the stored translation immediately.
  - If not found (cache miss), call the API and store the result.

Schema (table: translations):
  id           INTEGER PRIMARY KEY AUTOINCREMENT
  source_hash  TEXT    NOT NULL          — SHA-256 of source text
  source_text  TEXT    NOT NULL
  translation  TEXT    NOT NULL
  target_lang  TEXT    NOT NULL
  mode         TEXT    NOT NULL
  created_at   TEXT    NOT NULL          — ISO-8601 UTC
  hit_count    INTEGER DEFAULT 0         — how many times this entry was reused
"""

import sqlite3
import os
from datetime import datetime
from typing import Optional
from contextlib import contextmanager

from config import DB_PATH
from utils import compute_hash
from logger import setup_logger

logger = setup_logger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# TRANSLATION MEMORY
# ══════════════════════════════════════════════════════════════════════════════

class TranslationMemory:
    """
    Persistent translation cache using SQLite.

    Thread-safety note: Each public method opens and closes its own
    connection, which is safe for Streamlit's threading model.
    """

    _DDL = """
    CREATE TABLE IF NOT EXISTS translations (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        source_hash  TEXT    NOT NULL,
        source_text  TEXT    NOT NULL,
        translation  TEXT    NOT NULL,
        target_lang  TEXT    NOT NULL,
        mode         TEXT    NOT NULL,
        created_at   TEXT    NOT NULL,
        hit_count    INTEGER NOT NULL DEFAULT 0,
        UNIQUE(source_hash, target_lang, mode)
    );
    CREATE INDEX IF NOT EXISTS idx_tm_lookup
        ON translations(source_hash, target_lang, mode);
    """

    def __init__(self, db_path: str = DB_PATH) -> None:
        self._db_path = db_path
        self._init_db()

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        """Create the database schema if it does not already exist."""
        with self._connect() as conn:
            conn.executescript(self._DDL)
        logger.info("Translation Memory initialised: %s", self._db_path)

    @contextmanager
    def _connect(self):
        """Context manager that yields a SQLite connection and commits/closes it."""
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except sqlite3.Error as exc:
            conn.rollback()
            logger.error("SQLite error: %s", exc)
            raise
        finally:
            conn.close()

    # ── Public API ─────────────────────────────────────────────────────────────

    def get(
        self,
        source_text: str,
        target_lang: str,
        mode: str,
    ) -> Optional[str]:
        """
        Look up a cached translation.

        Args:
            source_text: Original source string.
            target_lang: Target language code (e.g. "es-la").
            mode:        Translation mode.

        Returns:
            Cached translation string, or None if not found.
        """
        key = compute_hash(source_text.strip())
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT translation, id
                FROM   translations
                WHERE  source_hash = ? AND target_lang = ? AND mode = ?
                LIMIT  1
                """,
                (key, target_lang, mode),
            ).fetchone()

            if row:
                # Increment hit counter
                conn.execute(
                    "UPDATE translations SET hit_count = hit_count + 1 WHERE id = ?",
                    (row["id"],),
                )
                logger.debug("TM hit: hash=%s lang=%s mode=%s", key[:8], target_lang, mode)
                return row["translation"]

        return None

    def store(
        self,
        source_text: str,
        translation: str,
        target_lang: str,
        mode: str,
    ) -> None:
        """
        Store a new translation in the memory.

        If an entry with the same (hash, lang, mode) exists, it is
        replaced with the new translation.

        Args:
            source_text: Original source string.
            translation: Translated string.
            target_lang: Target language code.
            mode:        Translation mode.
        """
        if not source_text.strip() or not translation.strip():
            return

        key = compute_hash(source_text.strip())
        now = datetime.utcnow().isoformat() + "Z"

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO translations
                    (source_hash, source_text, translation, target_lang, mode, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_hash, target_lang, mode)
                DO UPDATE SET
                    translation = excluded.translation,
                    created_at  = excluded.created_at
                """,
                (key, source_text.strip(), translation.strip(), target_lang, mode, now),
            )
        logger.debug("TM store: hash=%s lang=%s mode=%s", key[:8], target_lang, mode)

    def delete(self, source_text: str, target_lang: str, mode: str) -> int:
        """
        Delete a specific entry from the memory.

        Returns:
            Number of rows deleted (0 or 1).
        """
        key = compute_hash(source_text.strip())
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM translations WHERE source_hash=? AND target_lang=? AND mode=?",
                (key, target_lang, mode),
            )
            return cur.rowcount

    def clear(self) -> int:
        """Delete ALL entries from the translation memory. Returns row count."""
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM translations")
            count = cur.rowcount
        logger.warning("Translation Memory cleared: %d entries removed", count)
        return count

    # ── Statistics ─────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """
        Return aggregate statistics about the translation memory.

        Returns:
            Dict with keys: total_entries, total_hits, unique_languages,
            unique_modes, db_size_bytes.
        """
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*)        AS total_entries,
                    SUM(hit_count)  AS total_hits,
                    COUNT(DISTINCT target_lang) AS unique_languages,
                    COUNT(DISTINCT mode)        AS unique_modes
                FROM translations
                """
            ).fetchone()

        db_size = os.path.getsize(self._db_path) if os.path.exists(self._db_path) else 0

        return {
            "total_entries":    row["total_entries"] or 0,
            "total_hits":       row["total_hits"] or 0,
            "unique_languages": row["unique_languages"] or 0,
            "unique_modes":     row["unique_modes"] or 0,
            "db_size_bytes":    db_size,
        }

    def search(
        self,
        query: str,
        limit: int = 50,
    ) -> list[dict]:
        """
        Search entries by partial source text match.

        Args:
            query: Search term (case-insensitive substring match).
            limit: Maximum results to return.

        Returns:
            List of dicts with keys: source_text, translation,
            target_lang, mode, created_at, hit_count.
        """
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT source_text, translation, target_lang, mode,
                       created_at, hit_count
                FROM   translations
                WHERE  source_text LIKE ?
                ORDER  BY hit_count DESC
                LIMIT  ?
                """,
                (f"%{query}%", limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def recent(self, limit: int = 20) -> list[dict]:
        """Return the most recently added entries."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT source_text, translation, target_lang, mode,
                       created_at, hit_count
                FROM   translations
                ORDER  BY created_at DESC
                LIMIT  ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]


# ── Module-level singleton ─────────────────────────────────────────────────────
translation_memory = TranslationMemory()
