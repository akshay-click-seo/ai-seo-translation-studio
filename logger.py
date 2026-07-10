"""
logger.py — Logging infrastructure for AI SEO Translation Studio.

Provides:
  - setup_logger()        : Standard Python logger with file + console handlers
  - TranslationLogger     : Structured per-translation audit log (JSON Lines)
"""

import logging
import json
import os
from datetime import datetime
from typing import Optional

from config import LOGS_DIR


# ══════════════════════════════════════════════════════════════════════════════
# STANDARD LOGGER
# ══════════════════════════════════════════════════════════════════════════════

def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Create (or retrieve) a named logger with rotating file + console handlers.

    Args:
        name:  Logger name — typically the module name (__name__).
        level: Logging level (default INFO).

    Returns:
        Configured logging.Logger instance.
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        # Already configured — return as-is to avoid duplicate handlers
        return logger

    logger.setLevel(level)

    # ── Formatter ─────────────────────────────────────────────────────────────
    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ── Console handler ───────────────────────────────────────────────────────
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(fmt)
    logger.addHandler(console_handler)

    # ── File handler ──────────────────────────────────────────────────────────
    log_file = os.path.join(
        LOGS_DIR,
        f"app_{datetime.now().strftime('%Y%m%d')}.log",
    )
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    return logger


# ══════════════════════════════════════════════════════════════════════════════
# STRUCTURED TRANSLATION AUDIT LOGGER
# ══════════════════════════════════════════════════════════════════════════════

class TranslationLogger:
    """
    Writes one JSON line per translation event to a daily audit log.

    Each record contains:
        timestamp, mode, source_lang, target_lang,
        word_count, char_count, processing_time_ms,
        tm_hit (bool), error (optional)
    """

    def __init__(self) -> None:
        self._log_path = os.path.join(
            LOGS_DIR,
            f"translations_{datetime.now().strftime('%Y%m%d')}.jsonl",
        )
        self._logger = setup_logger(__name__)

    # ── Public API ─────────────────────────────────────────────────────────────

    def log_translation(
        self,
        *,
        mode: str,
        source_lang: str,
        target_lang: str,
        source_text: str,
        translated_text: str,
        processing_time_ms: float,
        tm_hit: bool = False,
        error: Optional[str] = None,
    ) -> None:
        """
        Append one translation event to the daily JSONL audit file.

        Args:
            mode:               Translation mode (Standard / SEO / HTML / Technical).
            source_lang:        Source language label.
            target_lang:        Target language code.
            source_text:        Original text.
            translated_text:    Result text.
            processing_time_ms: Wall-clock milliseconds for the API call.
            tm_hit:             True if result came from Translation Memory cache.
            error:              Error message if the translation failed.
        """
        record: dict = {
            "timestamp":          datetime.utcnow().isoformat() + "Z",
            "mode":               mode,
            "source_lang":        source_lang,
            "target_lang":        target_lang,
            "word_count":         len(source_text.split()),
            "char_count":         len(source_text),
            "translated_words":   len(translated_text.split()) if translated_text else 0,
            "processing_time_ms": round(processing_time_ms, 2),
            "tm_hit":             tm_hit,
            "error":              error,
        }

        try:
            with open(self._log_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as exc:
            self._logger.error("Failed to write translation log: %s", exc)

        # Mirror to standard logger
        if error:
            self._logger.error(
                "Translation FAILED | mode=%s target=%s error=%s",
                mode, target_lang, error,
            )
        else:
            self._logger.info(
                "Translated | mode=%s target=%s words=%d tm_hit=%s time=%.0fms",
                mode, target_lang, record["word_count"], tm_hit, processing_time_ms,
            )

    def log_file_translation(
        self,
        *,
        file_name: str,
        file_type: str,
        mode: str,
        target_lang: str,
        segments: int,
        processing_time_ms: float,
        error: Optional[str] = None,
    ) -> None:
        """Log a batch / file-level translation event."""
        record: dict = {
            "timestamp":          datetime.utcnow().isoformat() + "Z",
            "event":              "file_translation",
            "file_name":          file_name,
            "file_type":          file_type,
            "mode":               mode,
            "target_lang":        target_lang,
            "segments":           segments,
            "processing_time_ms": round(processing_time_ms, 2),
            "error":              error,
        }
        try:
            with open(self._log_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as exc:
            self._logger.error("Failed to write file log: %s", exc)

        level = logging.ERROR if error else logging.INFO
        self._logger.log(
            level,
            "File | %s | %s | segments=%d | %.0fms | %s",
            file_name, target_lang, segments, processing_time_ms,
            error or "OK",
        )

    def read_logs(self, limit: int = 100) -> list[dict]:
        """
        Read the most recent translation log entries.

        Args:
            limit: Maximum number of records to return (most recent first).

        Returns:
            List of log record dicts.
        """
        if not os.path.exists(self._log_path):
            return []
        try:
            with open(self._log_path, "r", encoding="utf-8") as fh:
                lines = fh.readlines()
            records = [json.loads(ln) for ln in lines if ln.strip()]
            return list(reversed(records))[:limit]
        except (OSError, json.JSONDecodeError) as exc:
            self._logger.error("Failed to read logs: %s", exc)
            return []


# ── Module-level singleton ─────────────────────────────────────────────────────
translation_logger = TranslationLogger()
