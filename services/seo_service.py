"""
services/seo_service.py — SEO analysis and comparison utilities.

Provides:
  - Keyword density analysis
  - Readability scoring (Flesch-Kincaid approximation)
  - Heading structure extraction
  - SEO quality comparison between source and translation
  - Keyword preservation check
"""

import re
from collections import Counter
from typing import Optional

from logger import setup_logger

logger = setup_logger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# STOP WORDS (English + Spanish — excluded from keyword density)
# ══════════════════════════════════════════════════════════════════════════════

_EN_STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can", "need", "that",
    "this", "these", "those", "it", "its", "as", "if", "not", "no",
})

_ES_STOP_WORDS = frozenset({
    "el", "la", "los", "las", "un", "una", "unos", "unas", "y", "o",
    "pero", "en", "de", "del", "al", "a", "con", "por", "para", "sin",
    "sobre", "entre", "este", "esta", "estos", "estas", "ese", "esa",
    "esos", "esas", "es", "son", "fue", "ser", "estar", "tiene", "han",
    "se", "su", "sus", "que", "no", "si", "como", "más", "muy",
})

STOP_WORDS = _EN_STOP_WORDS | _ES_STOP_WORDS


# ══════════════════════════════════════════════════════════════════════════════
# SEO SERVICE
# ══════════════════════════════════════════════════════════════════════════════

class SEOService:
    """Analyses SEO metrics of text and compares source vs. translation."""

    # ── Public: single-text analysis ──────────────────────────────────────────

    def analyse(self, text: str, top_n: int = 10) -> dict:
        """
        Compute SEO metrics for a single text.

        Args:
            text:  Input text (plain or lightly marked-up).
            top_n: Number of top keywords to return.

        Returns:
            Dict with keys:
              word_count, char_count, sentence_count, paragraph_count,
              avg_words_per_sentence, keyword_density (dict), headings (list),
              readability_score, readability_label.
        """
        clean = self._strip_html(text)
        words = self._tokenise(clean)
        sentences = self._split_sentences(clean)
        paragraphs = [p for p in text.split("\n\n") if p.strip()]

        kw_density = self._keyword_density(words, top_n)
        headings   = self._extract_headings(text)
        readability = self._flesch_kincaid(words, sentences)

        return {
            "word_count":            len(words),
            "char_count":            len(clean),
            "sentence_count":        len(sentences),
            "paragraph_count":       len(paragraphs),
            "avg_words_per_sentence": round(len(words) / max(len(sentences), 1), 1),
            "keyword_density":       kw_density,
            "headings":              headings,
            "readability_score":     readability["score"],
            "readability_label":     readability["label"],
        }

    def compare(
        self,
        source: str,
        translation: str,
        source_keywords: Optional[list[str]] = None,
        top_n: int = 10,
    ) -> dict:
        """
        Compare SEO metrics between source and translation.

        Args:
            source:           Original English text.
            translation:      Translated text.
            source_keywords:  Specific keywords to track (optional).
            top_n:            Top keywords to compare.

        Returns:
            Dict with source_stats, translation_stats,
            keyword_preservation_pct, length_ratio, issues (list).
        """
        src_stats = self.analyse(source, top_n)
        tr_stats  = self.analyse(translation, top_n)

        # Keyword preservation
        src_keywords = set(src_stats["keyword_density"].keys())
        tr_keywords  = set(tr_stats["keyword_density"].keys())

        # For language-crossing, we check if density structure is preserved
        # (exact keyword match is not expected across languages)
        length_ratio = round(tr_stats["word_count"] / max(src_stats["word_count"], 1), 2)

        issues: list[str] = []
        if length_ratio < 0.7:
            issues.append("Translation is significantly shorter than source (possible truncation).")
        if length_ratio > 1.6:
            issues.append("Translation is significantly longer — may affect readability.")
        if tr_stats["sentence_count"] < src_stats["sentence_count"] * 0.7:
            issues.append("Fewer sentences in translation — some content may be missing.")

        # Check specific keywords if provided
        preserved_kw: list[str] = []
        missing_kw: list[str] = []
        if source_keywords:
            tr_lower = translation.lower()
            for kw in source_keywords:
                if kw.lower() in tr_lower:
                    preserved_kw.append(kw)
                else:
                    missing_kw.append(kw)

        return {
            "source_stats":               src_stats,
            "translation_stats":          tr_stats,
            "length_ratio":               length_ratio,
            "heading_count_match":        src_stats["headings"] == tr_stats["headings"],
            "preserved_keywords":         preserved_kw,
            "missing_keywords":           missing_kw,
            "keyword_preservation_pct":   (
                round(len(preserved_kw) / len(source_keywords) * 100, 1)
                if source_keywords else None
            ),
            "issues":                     issues,
        }

    def check_glossary_preservation(
        self,
        source: str,
        translation: str,
        terms: list[str],
    ) -> dict:
        """
        Verify that protected glossary terms appear in the translation.

        Args:
            source:      Source text.
            translation: Translated text.
            terms:       List of terms that should appear unchanged.

        Returns:
            Dict with preserved (list), missing (list), score (float 0–100).
        """
        preserved = []
        missing   = []
        for term in terms:
            if term in translation:
                preserved.append(term)
            else:
                missing.append(term)

        score = round(len(preserved) / max(len(terms), 1) * 100, 1)
        return {"preserved": preserved, "missing": missing, "score": score}

    # ── Private: text processing ───────────────────────────────────────────────

    @staticmethod
    def _strip_html(text: str) -> str:
        """Remove HTML tags from text."""
        return re.sub(r"<[^>]+>", " ", text)

    @staticmethod
    def _tokenise(text: str) -> list[str]:
        """Lowercase word tokenisation, excluding stop words and short tokens."""
        words = re.findall(r"\b[a-záéíóúüñà-ÿa-z]{3,}\b", text.lower())
        return [w for w in words if w not in STOP_WORDS]

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """Split text into sentences on terminal punctuation."""
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        return [s for s in sentences if s.strip()]

    @staticmethod
    def _keyword_density(words: list[str], top_n: int) -> dict[str, float]:
        """
        Compute top-N keyword density as percentage of total words.

        Returns:
            {keyword: density_pct, ...}
        """
        if not words:
            return {}
        counts = Counter(words)
        total  = len(words)
        return {
            word: round(count / total * 100, 2)
            for word, count in counts.most_common(top_n)
        }

    @staticmethod
    def _extract_headings(text: str) -> list[str]:
        """Extract Markdown headings (# H1, ## H2, etc.)."""
        return re.findall(r"^#{1,6}\s+(.+)$", text, re.MULTILINE)

    @staticmethod
    def _flesch_kincaid(words: list[str], sentences: list[str]) -> dict:
        """
        Approximate Flesch Reading Ease score.
        (Simplified: uses word length as syllable proxy.)

        Returns:
            {"score": float, "label": str}
        """
        n_words     = max(len(words), 1)
        n_sentences = max(len(sentences), 1)
        # Proxy for syllables: characters / 3
        n_syllables = sum(max(len(w) // 3, 1) for w in words)

        score = 206.835 - 1.015 * (n_words / n_sentences) - 84.6 * (n_syllables / n_words)
        score = max(0.0, min(100.0, round(score, 1)))

        if score >= 70:
            label = "Easy"
        elif score >= 50:
            label = "Moderate"
        elif score >= 30:
            label = "Difficult"
        else:
            label = "Very Difficult"

        return {"score": score, "label": label}


# ── Module-level singleton ─────────────────────────────────────────────────────
seo_service = SEOService()
