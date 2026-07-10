"""
services/html_service.py — HTML-aware translation service.

Strategy:
  1. Parse with BeautifulSoup.
  2. Walk all text nodes (NavigableString) that are visible.
  3. Translate each non-empty text node individually.
  4. Reconstruct the original HTML structure with translated text.

Tags whose text content is NEVER translated:
  <script>, <style>, <code>, <pre>, <kbd>, <var>, <samp>,
  <meta>, <link>, <noscript>

Attributes are always preserved unchanged.
"""

import re
from typing import Optional, Callable

from bs4 import BeautifulSoup, NavigableString, Tag, Comment

from logger import setup_logger
from utils import is_translatable

logger = setup_logger(__name__)

# Tags whose text must NOT be translated
_SKIP_TAGS = frozenset({
    "script", "style", "code", "pre", "kbd", "var",
    "samp", "noscript", "meta", "link", "head",
})


def _get_parent_tags(node) -> list[str]:
    """Return list of ancestor tag names for a NavigableString node."""
    tags = []
    parent = node.parent
    while parent and hasattr(parent, "name") and parent.name:
        tags.append(parent.name.lower())
        parent = parent.parent
    return tags


class HTMLService:
    """Translates HTML documents while preserving all structure and attributes."""

    def translate(
        self,
        html: str,
        translator,                       # Translator instance
        target_lang: str = "es-la",
        mode: str = "HTML",
        use_tm: bool = True,
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> str:
        """
        Translate all visible text in *html* into *target_lang*.

        Args:
            html:         Source HTML string.
            translator:   Translator instance with a .translate() method.
            target_lang:  Target language code.
            mode:         Translation mode (should be "HTML").
            use_tm:       Use Translation Memory.
            on_progress:  Optional callback(current, total) for progress bar.

        Returns:
            Translated HTML string with all structure intact.
        """
        if not html or not html.strip():
            return html

        soup = BeautifulSoup(html, "lxml")

        # Collect all translatable text nodes
        text_nodes = self._collect_text_nodes(soup)
        total = len(text_nodes)
        logger.info("HTML translation: %d text nodes found", total)

        for idx, node in enumerate(text_nodes):
            if on_progress:
                on_progress(idx, total)

            original = str(node)
            if not is_translatable(original):
                continue

            stripped = original.strip()
            if not stripped:
                continue

            try:
                result = translator.translate(
                    stripped, target_lang=target_lang, mode=mode, use_tm=use_tm
                )
                translated = result["translation"]
                # Preserve leading/trailing whitespace from original
                leading  = original[: len(original) - len(original.lstrip())]
                trailing = original[len(original.rstrip()):]
                node.replace_with(leading + translated + trailing)
            except Exception as exc:
                logger.error("Failed to translate node '%s': %s", stripped[:50], exc)
                # Leave original text untouched on error

        return str(soup)

    def translate_fragment(
        self,
        fragment: str,
        translator,
        target_lang: str = "es-la",
        mode: str = "HTML",
        use_tm: bool = True,
    ) -> str:
        """
        Translate an HTML fragment (no <html>/<body> wrapper required).

        Args:
            fragment:    Partial HTML string.
            translator:  Translator instance.
            target_lang: Target language code.
            mode:        Translation mode.
            use_tm:      Use Translation Memory.

        Returns:
            Translated HTML fragment.
        """
        soup = BeautifulSoup(fragment, "html.parser")
        text_nodes = self._collect_text_nodes(soup)

        for node in text_nodes:
            original = str(node)
            stripped = original.strip()
            if not stripped or not is_translatable(stripped):
                continue
            try:
                result = translator.translate(
                    stripped, target_lang=target_lang, mode=mode, use_tm=use_tm
                )
                node.replace_with(result["translation"])
            except Exception as exc:
                logger.error("Fragment node error: %s", exc)

        return str(soup)

    # ── Private helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _collect_text_nodes(soup: BeautifulSoup) -> list[NavigableString]:
        """
        Walk the parse tree and collect all translatable NavigableString nodes.

        Excluded:
          - HTML comments
          - Children of skip-tag ancestors
          - Nodes containing only whitespace
        """
        results: list[NavigableString] = []

        for node in soup.descendants:
            if isinstance(node, Comment):
                continue
            if not isinstance(node, NavigableString):
                continue
            if not str(node).strip():
                continue

            parents = _get_parent_tags(node)
            if any(p in _SKIP_TAGS for p in parents):
                continue

            results.append(node)

        return results

    @staticmethod
    def extract_text(html: str) -> str:
        """
        Extract all visible text from HTML (utility method).

        Args:
            html: HTML string.

        Returns:
            Plain text content.
        """
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(list(_SKIP_TAGS)):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)

    @staticmethod
    def validate_html(html: str) -> tuple[bool, str]:
        """
        Check if *html* is parseable and non-empty.

        Returns:
            Tuple of (is_valid: bool, message: str).
        """
        if not html or not html.strip():
            return False, "HTML content is empty."
        try:
            soup = BeautifulSoup(html, "lxml")
            if not soup.find():
                return False, "No HTML elements found."
            return True, "Valid HTML."
        except Exception as exc:
            return False, f"Parse error: {exc}"


# ── Module-level singleton ─────────────────────────────────────────────────────
html_service = HTMLService()
