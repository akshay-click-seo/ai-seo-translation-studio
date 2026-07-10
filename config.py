"""
config.py — Central configuration for AI SEO Translation Studio.

All constants, environment variables, paths, and settings live here.
Import from this module instead of scattering os.getenv() calls.
"""

import os
from dotenv import load_dotenv

# ── Load .env file if present ──────────────────────────────────────────────────
load_dotenv()


# ══════════════════════════════════════════════════════════════════════════════
# API CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

NVIDIA_API_KEY: str = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_BASE_URL: str = "https://integrate.api.nvidia.com/v1"
NVIDIA_MODEL: str = "nvidia/riva-translate-4b-instruct-v1.1"

# ── Aliases (backward compatibility) ──────────────────────────────────────────
API_KEY   = NVIDIA_API_KEY
BASE_URL  = NVIDIA_BASE_URL
MODEL     = NVIDIA_MODEL

# Request settings
MAX_TOKENS: int = 4096
TEMPERATURE: float = 0.1          # Low temperature = more deterministic translations
REQUEST_TIMEOUT: int = 60         # seconds


# ══════════════════════════════════════════════════════════════════════════════
# APPLICATION METADATA
# ══════════════════════════════════════════════════════════════════════════════

APP_NAME: str = "AI SEO Translation Studio"
APP_VERSION: str = "1.0.0"
APP_ICON: str = "🌐"


# ══════════════════════════════════════════════════════════════════════════════
# DIRECTORY PATHS
# ══════════════════════════════════════════════════════════════════════════════

BASE_DIR: str = os.path.dirname(os.path.abspath(__file__))
UPLOADS_DIR: str = os.path.join(BASE_DIR, "uploads")
OUTPUTS_DIR: str = os.path.join(BASE_DIR, "outputs")
LOGS_DIR: str = os.path.join(BASE_DIR, "logs")
TEMP_DIR: str = os.path.join(BASE_DIR, "temp")
ASSETS_DIR: str = os.path.join(BASE_DIR, "assets")
DB_PATH: str = os.path.join(BASE_DIR, "translation_memory.db")

# Auto-create required directories
for _dir in (UPLOADS_DIR, OUTPUTS_DIR, LOGS_DIR, TEMP_DIR):
    os.makedirs(_dir, exist_ok=True)


# ══════════════════════════════════════════════════════════════════════════════
# LANGUAGE CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

# Supported target languages: code → display name
LANGUAGES: dict[str, str] = {
    "es-la": "Spanish (LATAM)",
    "pt":    "Portuguese (Brazil)",
    "fr":    "French",
    "de":    "German",
    "it":    "Italian",
}

# Default source / target
DEFAULT_SOURCE_LANG: str = "English"
DEFAULT_TARGET_LANG: str = "es-la"

# Language code → full name mapping used in prompts
LANG_FULL_NAMES: dict[str, str] = {
    "es-la": "Latin American Spanish",
    "pt":    "Brazilian Portuguese",
    "fr":    "French",
    "de":    "German",
    "it":    "Italian",
}


# ══════════════════════════════════════════════════════════════════════════════
# TRANSLATION MODES
# ══════════════════════════════════════════════════════════════════════════════

TRANSLATION_MODES: list[str] = [
    "Standard",    # General-purpose translation
    "SEO",         # Preserve SEO intent + keyword density
    "HTML",        # Translate only visible text, preserve all tags
    "Technical",   # Market research domain — consistent terminology
]

MODE_DESCRIPTIONS: dict[str, str] = {
    "Standard":  "General-purpose translation with natural flow.",
    "SEO":       "Preserve SEO intent, keyword density, and search relevance.",
    "HTML":      "Translate only visible text nodes; preserve all HTML structure.",
    "Technical": "Market research terminology — consistent, domain-accurate translation.",
}


# ══════════════════════════════════════════════════════════════════════════════
# FILE HANDLING
# ══════════════════════════════════════════════════════════════════════════════

SUPPORTED_EXTENSIONS: list[str] = [
    ".txt", ".html", ".htm", ".docx", ".pptx", ".xlsx", ".xls", ".md", ".json",
]

MAX_FILE_SIZE_MB: int = 50
MAX_BATCH_FILES: int = 20


# ══════════════════════════════════════════════════════════════════════════════
# UI SETTINGS
# ══════════════════════════════════════════════════════════════════════════════

SIDEBAR_WIDTH: int = 320
DEFAULT_TEXT_HEIGHT: int = 300
HISTORY_LIMIT: int = 50           # Max entries in session history
