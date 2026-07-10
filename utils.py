"""
utils.py — Shared utility helpers for AI SEO Translation Studio.

Covers: text stats, file I/O helpers, sanitisation, chunking,
        format detection, and Streamlit UI conveniences.
"""

import os
import re
import json
import hashlib
import tempfile
from pathlib import Path
from typing import Optional, Generator

from config import (
    UPLOADS_DIR, OUTPUTS_DIR, TEMP_DIR,
    MAX_FILE_SIZE_MB, SUPPORTED_EXTENSIONS,
)
from logger import setup_logger

logger = setup_logger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# TEXT STATISTICS
# ══════════════════════════════════════════════════════════════════════════════

def count_words(text: str) -> int:
    """Return the word count of *text*."""
    return len(text.split()) if text.strip() else 0


def count_chars(text: str) -> int:
    """Return the character count of *text* (including spaces)."""
    return len(text)


def count_sentences(text: str) -> int:
    """Rough sentence count based on terminal punctuation."""
    return len(re.findall(r"[.!?]+", text))


def text_stats(text: str) -> dict[str, int]:
    """
    Return a stats dictionary for the given text.

    Returns:
        {"words": int, "chars": int, "sentences": int, "paragraphs": int}
    """
    return {
        "words":      count_words(text),
        "chars":      count_chars(text),
        "sentences":  count_sentences(text),
        "paragraphs": len([p for p in text.split("\n\n") if p.strip()]),
    }


def compute_hash(text: str) -> str:
    """
    Compute a stable SHA-256 hex digest for *text*.
    Used as a cache key in Translation Memory.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ══════════════════════════════════════════════════════════════════════════════
# TEXT CHUNKING
# ══════════════════════════════════════════════════════════════════════════════

def chunk_text(
    text: str,
    max_chars: int = 3000,
    overlap: int = 0,
) -> list[str]:
    """
    Split *text* into chunks of at most *max_chars* characters,
    breaking only at paragraph boundaries (double newline).

    Args:
        text:      Input text.
        max_chars: Maximum characters per chunk.
        overlap:   Not currently used (reserved for future sliding-window).

    Returns:
        List of text chunks.
    """
    if len(text) <= max_chars:
        return [text]

    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        candidate = (current + "\n\n" + para).strip() if current else para
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            # If a single paragraph exceeds max_chars, split by sentence
            if len(para) > max_chars:
                chunks.extend(_split_by_sentence(para, max_chars))
                current = ""
            else:
                current = para

    if current:
        chunks.append(current)

    return chunks


def _split_by_sentence(text: str, max_chars: int) -> list[str]:
    """Split oversized text at sentence boundaries."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    current = ""

    for sent in sentences:
        candidate = (current + " " + sent).strip() if current else sent
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = sent

    if current:
        chunks.append(current)
    return chunks


# ══════════════════════════════════════════════════════════════════════════════
# FILE UTILITIES
# ══════════════════════════════════════════════════════════════════════════════

def save_upload(file_bytes: bytes, filename: str) -> str:
    """
    Save uploaded file bytes to the uploads directory.

    Args:
        file_bytes: Raw bytes from Streamlit's uploaded file.
        filename:   Original filename (used to preserve extension).

    Returns:
        Absolute path to the saved file.
    """
    safe_name = sanitise_filename(filename)
    path = os.path.join(UPLOADS_DIR, safe_name)
    with open(path, "wb") as fh:
        fh.write(file_bytes)
    logger.info("Saved upload: %s (%d bytes)", path, len(file_bytes))
    return path


def save_output(content: bytes | str, filename: str) -> str:
    """
    Save translated output to the outputs directory.

    Args:
        content:  File content (bytes or str).
        filename: Desired output filename.

    Returns:
        Absolute path to the saved file.
    """
    safe_name = sanitise_filename(filename)
    path = os.path.join(OUTPUTS_DIR, safe_name)
    mode = "wb" if isinstance(content, bytes) else "w"
    enc = None if isinstance(content, bytes) else "utf-8"
    with open(path, mode, encoding=enc) as fh:
        fh.write(content)
    logger.info("Saved output: %s", path)
    return path


def read_text_file(path: str) -> str:
    """Read a plain-text file, auto-detecting encoding."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except UnicodeDecodeError:
        with open(path, "r", encoding="latin-1") as fh:
            return fh.read()


def get_file_extension(filename: str) -> str:
    """Return lowercase file extension including the dot, e.g. '.docx'."""
    return Path(filename).suffix.lower()


def is_supported_file(filename: str) -> bool:
    """Return True if the file extension is in SUPPORTED_EXTENSIONS."""
    return get_file_extension(filename) in SUPPORTED_EXTENSIONS


def validate_file_size(file_bytes: bytes) -> bool:
    """Return True if file size is within the allowed limit."""
    return len(file_bytes) <= MAX_FILE_SIZE_MB * 1024 * 1024


def sanitise_filename(name: str) -> str:
    """Remove characters unsafe for file system paths."""
    name = re.sub(r"[^\w.\- ]", "_", name)
    name = re.sub(r"\s+", "_", name.strip())
    return name


def output_filename(original: str, suffix: str = "_translated") -> str:
    """
    Generate an output filename from the original input filename.

    Example:
        "report.docx" → "report_translated.docx"
    """
    p = Path(original)
    return f"{p.stem}{suffix}{p.suffix}"


def make_temp_file(suffix: str = ".tmp") -> str:
    """Create a named temporary file in TEMP_DIR and return its path."""
    fd, path = tempfile.mkstemp(suffix=suffix, dir=TEMP_DIR)
    os.close(fd)
    return path


# ══════════════════════════════════════════════════════════════════════════════
# TEXT SANITISATION
# ══════════════════════════════════════════════════════════════════════════════

def strip_zero_width(text: str) -> str:
    """Remove zero-width and invisible Unicode characters."""
    return re.sub(r"[​‌‍﻿­]", "", text)


def normalise_whitespace(text: str) -> str:
    """Collapse multiple spaces to one; normalise line endings."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def is_translatable(text: str) -> bool:
    """
    Return True if *text* contains at least one alphabetic character
    (i.e., worth sending to the translation API).
    """
    return bool(re.search(r"[a-zA-ZÀ-ɏ]", text))


# ══════════════════════════════════════════════════════════════════════════════
# FORMAT DETECTION
# ══════════════════════════════════════════════════════════════════════════════

def detect_content_type(text: str) -> str:
    """
    Heuristically detect whether *text* is HTML, JSON, Markdown, or plain.

    Returns:
        One of: "html", "json", "markdown", "plain"
    """
    stripped = text.strip()
    if stripped.startswith("<") and re.search(r"</\w+>", stripped):
        return "html"
    try:
        json.loads(stripped)
        return "json"
    except (ValueError, TypeError):
        pass
    if re.search(r"^#{1,6}\s", stripped, re.MULTILINE):
        return "markdown"
    return "plain"


# ══════════════════════════════════════════════════════════════════════════════
# STREAMLIT HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def format_bytes(n: int) -> str:
    """Human-readable file size."""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024  # type: ignore[assignment]
    return f"{n:.1f} TB"


def format_ms(ms: float) -> str:
    """Format milliseconds as a readable duration string."""
    if ms < 1000:
        return f"{ms:.0f} ms"
    return f"{ms / 1000:.2f} s"


def truncate(text: str, max_len: int = 120, ellipsis: str = "…") -> str:
    """Truncate *text* to *max_len* characters for display."""
    return text if len(text) <= max_len else text[:max_len - 1] + ellipsis
