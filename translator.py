"""
translator.py — Core translation engine for AI SEO Translation Studio.

Wraps the NVIDIA Riva API (OpenAI-compatible) with:
  - Translation Memory cache (SQLite)
  - Glossary token protection / restoration
  - Chunked translation for long texts
  - Structured error handling and logging
  - Batch translation support
"""

import time
from typing import Optional, Callable

from openai import OpenAI, APIError, RateLimitError, APITimeoutError

from config import (
    NVIDIA_BASE_URL, NVIDIA_MODEL,
    MAX_TOKENS, TEMPERATURE, REQUEST_TIMEOUT,
    LANG_FULL_NAMES,
)
from prompt import get_system_prompt, get_cell_system_prompt, build_messages
from glossary import GlossaryManager, glossary_manager as _default_gm
from services.translation_memory import TranslationMemory, translation_memory as _default_tm
from utils import chunk_text, is_translatable, compute_hash
from logger import setup_logger, translation_logger

logger = setup_logger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# EXCEPTIONS
# ══════════════════════════════════════════════════════════════════════════════

class TranslationError(Exception):
    """Raised when a translation cannot be completed."""


class APIKeyError(TranslationError):
    """Raised when the API key is missing or invalid."""


class RateLimitExceededError(TranslationError):
    """Raised when the API rate limit is hit."""


# ══════════════════════════════════════════════════════════════════════════════
# TRANSLATOR
# ══════════════════════════════════════════════════════════════════════════════

class Translator:
    """
    High-level translation interface.

    All translation calls go through here; the class handles:
      1. Translation Memory look-up (skip API if cached)
      2. Glossary protection before the call
      3. API request with retry on transient errors
      4. Glossary restoration after the call
      5. Result storage in Translation Memory
      6. Structured audit logging

    Args:
        api_key:   NVIDIA API key.
        tm:        TranslationMemory instance (defaults to module singleton).
        gm:        GlossaryManager instance (defaults to module singleton).
        model:     Model identifier (defaults to config.NVIDIA_MODEL).
        base_url:  API base URL (defaults to config.NVIDIA_BASE_URL).
    """

    def __init__(
        self,
        api_key: str,
        tm: Optional[TranslationMemory] = None,
        gm: Optional[GlossaryManager] = None,
        model: str = NVIDIA_MODEL,
        base_url: str = NVIDIA_BASE_URL,
    ) -> None:
        if not api_key or not api_key.strip():
            raise APIKeyError("NVIDIA API key is required.")

        self._client = OpenAI(api_key=api_key.strip(), base_url=base_url)
        self._model = model
        self._tm = tm or _default_tm
        self._gm = gm or _default_gm

    # ── Public: single translation ─────────────────────────────────────────────

    def translate(
        self,
        text: str,
        target_lang: str = "es-la",
        mode: str = "Standard",
        use_tm: bool = True,
        use_glossary: bool = True,
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> dict:
        """
        Translate *text* into *target_lang* using *mode*.

        Args:
            text:         Source text (may be multi-paragraph).
            target_lang:  Target language code (e.g. "es-la").
            mode:         Translation mode ("Standard" / "SEO" / "HTML" / "Technical").
            use_tm:       Whether to check / write Translation Memory.
            use_glossary: Whether to apply glossary protection.
            on_progress:  Optional callback(current_chunk, total_chunks).

        Returns:
            Dict with keys:
              translation (str), tm_hit (bool),
              words (int), chars (int), time_ms (float)

        Raises:
            TranslationError: On unrecoverable API failure.
        """
        if not text or not text.strip():
            return self._empty_result()

        text = text.strip()
        t0 = time.perf_counter()

        # ── 1. Translation Memory look-up ──────────────────────────────────────
        if use_tm:
            cached = self._tm.get(text, target_lang, mode)
            if cached:
                elapsed = (time.perf_counter() - t0) * 1000
                translation_logger.log_translation(
                    mode=mode, source_lang="English", target_lang=target_lang,
                    source_text=text, translated_text=cached,
                    processing_time_ms=elapsed, tm_hit=True,
                )
                return {
                    "translation": cached,
                    "tm_hit":      True,
                    "words":       len(text.split()),
                    "chars":       len(text),
                    "time_ms":     elapsed,
                }

        # ── 2. Chunk if needed ─────────────────────────────────────────────────
        chunks = chunk_text(text, max_chars=6000)
        translated_chunks: list[str] = []

        for idx, chunk in enumerate(chunks):
            if on_progress:
                on_progress(idx, len(chunks))

            translated_chunk = self._translate_chunk(
                chunk, target_lang, mode, use_glossary
            )
            translated_chunks.append(translated_chunk)

        translation = "\n\n".join(translated_chunks) if len(chunks) > 1 else translated_chunks[0]

        # ── 3. Store in Translation Memory ────────────────────────────────────
        if use_tm:
            self._tm.store(text, translation, target_lang, mode)

        elapsed = (time.perf_counter() - t0) * 1000
        translation_logger.log_translation(
            mode=mode, source_lang="English", target_lang=target_lang,
            source_text=text, translated_text=translation,
            processing_time_ms=elapsed, tm_hit=False,
        )

        return {
            "translation": translation,
            "tm_hit":      False,
            "words":       len(text.split()),
            "chars":       len(text),
            "time_ms":     elapsed,
        }

    # ── Public: batch translation ──────────────────────────────────────────────

    def translate_batch(
        self,
        texts: list[str],
        target_lang: str = "es-la",
        mode: str = "Standard",
        use_tm: bool = True,
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> list[str]:
        """
        Translate a list of text segments.

        Args:
            texts:       List of source strings.
            target_lang: Target language code.
            mode:        Translation mode.
            use_tm:      Whether to use Translation Memory.
            on_progress: Optional callback(current_idx, total).

        Returns:
            List of translated strings (same order as input).
        """
        results: list[str] = []
        for i, text in enumerate(texts):
            if on_progress:
                on_progress(i, len(texts))
            if not text or not is_translatable(text):
                results.append(text)
                continue
            result = self.translate(text, target_lang, mode, use_tm)
            results.append(result["translation"])
        return results

    def translate_cell(
        self,
        value: str,
        target_lang: str = "es-la",
        use_tm: bool = True,
    ) -> str:
        """
        Translate a single Excel/table cell value.
        Uses a minimal system prompt optimised for short strings.

        Args:
            value:       Cell text value.
            target_lang: Target language code.
            use_tm:      Whether to use Translation Memory.

        Returns:
            Translated string.
        """
        if not value or not is_translatable(str(value)):
            return str(value)

        value = str(value).strip()

        if use_tm:
            cached = self._tm.get(value, target_lang, "cell")
            if cached:
                return cached

        system = get_cell_system_prompt(target_lang)
        translation = self._call_api(system, value, target_lang_code=target_lang)

        if use_tm:
            self._tm.store(value, translation, target_lang, "cell")

        return translation

    # ── Private: single chunk ─────────────────────────────────────────────────

    def _translate_chunk(
        self,
        chunk: str,
        target_lang: str,
        mode: str,
        use_glossary: bool,
    ) -> str:
        """
        Translate a single text chunk with optional glossary protection.

        Args:
            chunk:        Text to translate.
            target_lang:  Target language code.
            mode:         Translation mode.
            use_glossary: Apply glossary tokenisation.

        Returns:
            Translated string with glossary terms restored.
        """
        token_map: dict[str, str] = {}

        if use_glossary:
            chunk, token_map = self._gm.protect(chunk)

        system = get_system_prompt(mode, target_lang)
        translation = self._call_api(system, chunk, target_lang_code=target_lang)

        if use_glossary and token_map:
            translation = self._gm.restore(translation, token_map)

        return translation

    # ── Private: API call with retry ─────────────────────────────────────────

    def _call_api(
        self,
        system_prompt: str,
        user_text: str,
        retries: int = 3,
        backoff: float = 2.0,
        target_lang_code: str = "es-la",
    ) -> str:
        """
        Make a chat completion request with exponential back-off retry.

        Args:
            system_prompt: System instruction.
            user_text:     Text to translate.
            retries:       Number of retry attempts on transient errors.
            backoff:       Base seconds for exponential back-off.

        Returns:
            Model response string.

        Raises:
            TranslationError: After all retries exhausted or on fatal error.
        """
        messages = build_messages(system_prompt, user_text, target_lang_code=target_lang_code)
        last_error: Optional[Exception] = None

        for attempt in range(1, retries + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,  # type: ignore[arg-type]
                    max_tokens=MAX_TOKENS,
                    temperature=TEMPERATURE,
                    timeout=REQUEST_TIMEOUT,
                )
                content = response.choices[0].message.content or ""
                return content.strip()

            except RateLimitError as exc:
                wait = backoff ** attempt
                logger.warning("Rate limit hit (attempt %d/%d). Waiting %.1fs.", attempt, retries, wait)
                last_error = exc
                time.sleep(wait)

            except APITimeoutError as exc:
                wait = backoff ** attempt
                logger.warning("API timeout (attempt %d/%d). Waiting %.1fs.", attempt, retries, wait)
                last_error = exc
                time.sleep(wait)

            except APIError as exc:
                # 401 Unauthorized — no point retrying
                if hasattr(exc, "status_code") and exc.status_code == 401:
                    raise APIKeyError(
                        "Invalid or expired NVIDIA API key. Please check your key."
                    ) from exc
                wait = backoff ** attempt
                logger.warning("API error (attempt %d/%d): %s. Waiting %.1fs.", attempt, retries, exc, wait)
                last_error = exc
                time.sleep(wait)

            except Exception as exc:
                logger.error("Unexpected error during API call: %s", exc)
                raise TranslationError(f"Unexpected error: {exc}") from exc

        raise TranslationError(
            f"Translation failed after {retries} attempts. Last error: {last_error}"
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _empty_result() -> dict:
        return {
            "translation": "",
            "tm_hit":      False,
            "words":       0,
            "chars":       0,
            "time_ms":     0.0,
        }

    def validate_api_key(self) -> bool:
        """
        Make a minimal test call to verify the API key is valid.

        Returns:
            True if the key is valid, False otherwise.
        """
        try:
            self._call_api("You are a test assistant.", "Hello", retries=1)
            return True
        except (APIKeyError, TranslationError):
            return False
