"""
prompt.py — Prompt templates for AI SEO Translation Studio.

NVIDIA Riva translate models work best with direct, concise instructions.
The translation target is embedded in the user message itself.
"""

from config import LANG_FULL_NAMES


# ══════════════════════════════════════════════════════════════════════════════
# SYSTEM PROMPTS (kept minimal — Riva ignores complex system instructions)
# ══════════════════════════════════════════════════════════════════════════════

_SYSTEM_BASE = "You are a professional translator. Translate accurately and return only the translated text."

_SYSTEM_SEO  = "You are an SEO translator. Preserve keyword density and search intent. Return only the translated text."

_SYSTEM_HTML = "You are an HTML translator. Translate only visible text between HTML tags. Never modify any HTML tags, attributes, or structure. Return valid HTML."

_SYSTEM_TECH = (
    "You are a Market Research translator. Use consistent terminology:\n"
    "Historical Period=Período Histórico, Forecast Period=Período de Pronóstico, "
    "Base Year=Año Base, Market Size=Tamaño del Mercado, Drivers=Impulsores, "
    "Challenges=Desafíos, Opportunities=Oportunidades, Restraints=Limitantes, "
    "Segmentation=Segmentación, Key Players=Principales Actores. "
    "Return only the translated text."
)


# ══════════════════════════════════════════════════════════════════════════════
# USER MESSAGE BUILDER
# Instruction is embedded directly in the user message for Riva compatibility
# ══════════════════════════════════════════════════════════════════════════════

def get_system_prompt(mode: str, target_lang_code: str) -> str:
    """Return a minimal system prompt for the given mode."""
    map_ = {
        "Standard":  _SYSTEM_BASE,
        "SEO":       _SYSTEM_SEO,
        "HTML":      _SYSTEM_HTML,
        "Technical": _SYSTEM_TECH,
    }
    return map_.get(mode, _SYSTEM_BASE)


def get_cell_system_prompt(target_lang_code: str) -> str:
    """Minimal system prompt for single-cell Excel translation."""
    return _SYSTEM_BASE


def build_messages(
    system_prompt: str,
    source_text: str,
    target_lang_code: str = "es-la",
) -> list[dict[str, str]]:
    """
    Completion-style prompt for Riva translate model.
    Model sees 'English: ...' and 'Spanish:' prefix forcing it to complete
    with the translation rather than echoing or ignoring instructions.
    """
    target_lang = LANG_FULL_NAMES.get(target_lang_code, "Latin American Spanish")

    # Riva translate model works best with label-completion format.
    # Do NOT add any instructions — the model translates ALL text in user message.
    user_content = f"English:\n{source_text}\n\n{target_lang}:\n"

    return [
        {"role": "user", "content": user_content},
    ]
