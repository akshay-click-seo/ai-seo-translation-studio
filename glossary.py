"""
glossary.py — Glossary protection system for AI SEO Translation Studio.

Strategy:
  1. Before translation: replace protected terms with unique placeholder tokens.
  2. Pass tokenised text to the translation API.
  3. After translation: restore original terms from tokens.

This guarantees that company names, abbreviations, currencies, and domain-
specific terminology are NEVER altered by the model.
"""

import re
import uuid
from typing import Optional

from logger import setup_logger

logger = setup_logger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# PROTECTED TERMS
# Keys   = original term (case-sensitive as it should appear in output)
# Values = preferred translated form, OR the same string to leave untouched
# ══════════════════════════════════════════════════════════════════════════════

# Company / Brand names — always preserved as-is
COMPANY_NAMES: dict[str, str] = {
    "IMARC Group":            "IMARC Group",
    "Expert Market Research": "Expert Market Research",
    "Informes de Expertos":   "Informes de Expertos",
    "Grand View Research":    "Grand View Research",
    "MarketsandMarkets":      "MarketsandMarkets",
    "Mordor Intelligence":    "Mordor Intelligence",
    "Technavio":              "Technavio",
    "Statista":               "Statista",
    "Bloomberg":              "Bloomberg",
    "Reuters":                "Reuters",
    "McKinsey":               "McKinsey",
    "Deloitte":               "Deloitte",
    "PwC":                    "PwC",
    "KPMG":                   "KPMG",
    "EY":                     "EY",
}

# Financial / market abbreviations
FINANCIAL_TERMS: dict[str, str] = {
    "CAGR":  "CAGR",
    "USD":   "USD",
    "EUR":   "EUR",
    "GBP":   "GBP",
    "JPY":   "JPY",
    "BRL":   "BRL",
    "MXN":   "MXN",
    "COP":   "COP",
    "ARS":   "ARS",
    "CLP":   "CLP",
    "IPO":   "IPO",
    "M&A":   "M&A",
    "ROI":   "ROI",
    "EBITDA":"EBITDA",
    "GDP":   "GDP",
    "PIB":   "PIB",
    "GNP":   "GNP",
}

# Technology / domain abbreviations
TECH_TERMS: dict[str, str] = {
    "AI":    "AI",
    "ML":    "ML",
    "IoT":   "IoT",
    "API":   "API",
    "SaaS":  "SaaS",
    "PaaS":  "PaaS",
    "IaaS":  "IaaS",
    "ERP":   "ERP",
    "CRM":   "CRM",
    "B2B":   "B2B",
    "B2C":   "B2C",
    "HTML":  "HTML",
    "SEO":   "SEO",
    "SEM":   "SEM",
    "KPI":   "KPI",
    "URL":   "URL",
    "UI":    "UI",
    "UX":    "UX",
    "5G":    "5G",
    "EV":    "EV",
    "R&D":   "R&D",
}

# Industry-specific
INDUSTRY_TERMS: dict[str, str] = {
    "FMCG": "FMCG",
    "BFSI": "BFSI",
    "HVAC": "HVAC",
    "OEM":  "OEM",
    "ODM":  "ODM",
    "SME":  "SME",
    "SMB":  "SMB",
    "ESG":  "ESG",
    "CO2":  "CO2",
    "GHG":  "GHG",
    "LNG":  "LNG",
    "LPG":  "LPG",
}

# Market research report section labels — consistent Spanish translations
MARKET_RESEARCH_TERMS: dict[str, str] = {
    "Historical Period":      "Período Histórico",
    "Forecast Period":        "Período de Pronóstico",
    "Base Year":              "Año Base",
    "Market Size":            "Tamaño del Mercado",
    "Segmentation":           "Segmentación",
    "Regional Analysis":      "Análisis Regional",
    "Competitive Landscape":  "Panorama Competitivo",
    "Key Players":            "Principales Actores",
    "Market Dynamics":        "Dinámica del Mercado",
    "Drivers":                "Impulsores",
    "Challenges":             "Desafíos",
    "Opportunities":          "Oportunidades",
    "Restraints":             "Limitantes",
    "Executive Summary":      "Resumen Ejecutivo",
    "Table of Contents":      "Índice de Contenidos",
    "List of Figures":        "Lista de Figuras",
    "List of Tables":         "Lista de Tablas",
    "Key Findings":           "Hallazgos Clave",
    "Porter's Five Forces":   "Las Cinco Fuerzas de Porter",
    "SWOT Analysis":          "Análisis FODA",
    "Value Chain":            "Cadena de Valor",
    "Supply Chain":           "Cadena de Suministro",
    "North America":          "América del Norte",
    "Latin America":          "América Latina",
    "Asia Pacific":           "Asia Pacífico",
    "Middle East":            "Medio Oriente",
    "Rest of the World":      "Resto del Mundo",
}

# Merge all dictionaries into one master glossary
MASTER_GLOSSARY: dict[str, str] = {
    **COMPANY_NAMES,
    **FINANCIAL_TERMS,
    **TECH_TERMS,
    **INDUSTRY_TERMS,
    # Note: MARKET_RESEARCH_TERMS are not protected (they have desired translations)
}

# Terms that should be replaced with a specific Spanish equivalent
TRANSLATION_GLOSSARY: dict[str, str] = {
    **MARKET_RESEARCH_TERMS,
}


# ══════════════════════════════════════════════════════════════════════════════
# GLOSSARY MANAGER
# ══════════════════════════════════════════════════════════════════════════════

class GlossaryManager:
    """
    Protects glossary terms through tokenisation before API translation,
    and restores them after.

    Usage::

        gm = GlossaryManager()
        tokenised, token_map = gm.protect(source_text)
        translated = call_api(tokenised)
        final = gm.restore(translated, token_map)
    """

    # Token format: unlikely to appear in any natural text
    TOKEN_PREFIX = "GLOSS"
    TOKEN_SUFFIX = "END"

    def __init__(self, extra_terms: Optional[dict[str, str]] = None) -> None:
        """
        Args:
            extra_terms: Additional user-defined protected terms
                         (merged on top of MASTER_GLOSSARY).
        """
        self._protected = dict(MASTER_GLOSSARY)
        if extra_terms:
            self._protected.update(extra_terms)

        # Pre-sort by length (longest first) to avoid partial-match conflicts
        self._sorted_terms = sorted(
            self._protected.keys(), key=len, reverse=True
        )

    # ── Public methods ─────────────────────────────────────────────────────────

    def protect(self, text: str) -> tuple[str, dict[str, str]]:
        """
        Replace all protected terms in *text* with unique placeholder tokens.

        Args:
            text: Source text to process.

        Returns:
            Tuple of (tokenised_text, token_to_original_map).
        """
        token_map: dict[str, str] = {}

        for term in self._sorted_terms:
            if term not in text:
                continue
            token = self._make_token()
            token_map[token] = self._protected[term]   # restore to desired form
            # Case-insensitive replacement, preserving surrounding whitespace
            pattern = re.compile(re.escape(term), re.IGNORECASE)
            text = pattern.sub(token, text)
            logger.debug("Glossary protected: '%s' → %s", term, token)

        return text, token_map

    def restore(self, text: str, token_map: dict[str, str]) -> str:
        """
        Replace placeholder tokens in *text* back with their original terms.

        Args:
            text:      Translated (tokenised) text.
            token_map: Map returned by protect().

        Returns:
            Text with all tokens replaced by the correct glossary terms.
        """
        for token, original in token_map.items():
            text = text.replace(token, original)
        return text

    def apply_translation_glossary(self, text: str) -> str:
        """
        Apply preferred translations for known market-research terms
        AFTER the main translation (post-processing pass).

        Args:
            text: Already-translated text.

        Returns:
            Text with preferred Spanish equivalents enforced.
        """
        for english, spanish in TRANSLATION_GLOSSARY.items():
            pattern = re.compile(re.escape(english), re.IGNORECASE)
            text = pattern.sub(spanish, text)
        return text

    def get_all_protected_terms(self) -> list[str]:
        """Return sorted list of all currently protected terms."""
        return sorted(self._protected.keys())

    def add_term(self, term: str, replacement: Optional[str] = None) -> None:
        """
        Add a new term to the protection list at runtime.

        Args:
            term:        The term to protect.
            replacement: The form to restore after translation
                         (defaults to *term* unchanged).
        """
        self._protected[term] = replacement or term
        self._sorted_terms = sorted(
            self._protected.keys(), key=len, reverse=True
        )

    # ── Private helpers ────────────────────────────────────────────────────────

    def _make_token(self) -> str:
        """Generate a unique short token unlikely to appear in translated text."""
        uid = uuid.uuid4().hex[:8].upper()
        return f"{self.TOKEN_PREFIX}{uid}{self.TOKEN_SUFFIX}"


# ── Module-level singleton ─────────────────────────────────────────────────────
glossary_manager = GlossaryManager()
