# AI SEO Translation Studio

Production-ready AI translation tool for Market Research reports.
Built with Python 3.13, Streamlit, and the NVIDIA Riva API.

---

## Quick Start

```bash
# 1. Clone / download the project
cd "AI SEO Translation Agent"

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure API key
cp .env.example .env
# Edit .env → set NVIDIA_API_KEY=nvapi-your-key-here

# 5. Run
streamlit run app.py
```

---

## Project Structure

```
AI SEO Translation Agent/
├── app.py                      ← Streamlit UI (10 tabs)
├── config.py                   ← All settings & constants
├── translator.py               ← Core translation engine
├── prompt.py                   ← System prompt templates
├── glossary.py                 ← Term protection & glossary
├── utils.py                    ← Shared helpers
├── logger.py                   ← Logging (file + console + audit)
├── requirements.txt
├── .env.example
│
├── services/
│   ├── translation_memory.py   ← SQLite TM cache
│   ├── html_service.py         ← HTML-aware translation
│   ├── excel_service.py        ← Excel column translation
│   ├── docx_service.py         ← Word document translation
│   ├── pptx_service.py         ← PowerPoint translation
│   └── seo_service.py          ← SEO analysis & comparison
│
├── assets/
│   └── style.css               ← Custom Streamlit CSS
│
├── uploads/                    ← Uploaded files (auto-created)
├── outputs/                    ← Output files (auto-created)
├── logs/                       ← Log files (auto-created)
└── temp/                       ← Temporary files (auto-created)
```

---

## Features

| Tab | Feature |
|-----|---------|
| ✏️ Text | Plain text translation with TM cache |
| 🏷️ HTML | HTML-aware translation (preserves all tags) |
| 📊 Excel | Translate selected columns in .xlsx files |
| 📄 DOCX | Translate Word documents preserving formatting |
| 🎯 PPT | Translate PowerPoint slides preserving design |
| 📦 Batch | Translate multiple files → download as ZIP |
| 🔍 SEO | SEO analysis & source vs translation comparison |
| 💾 TM | Browse, search, and manage the translation cache |
| 📜 History | Session translation history |
| 📖 Glossary | View and add protected terms |

---

## API

- **Provider:** NVIDIA Build  
- **Base URL:** `https://integrate.api.nvidia.com/v1`  
- **Model:** `nvidia/riva-translate-4b-instruct-v1.1`  
- **SDK:** OpenAI Python SDK (OpenAI-compatible interface)

---

## Translation Modes

| Mode | Description |
|------|-------------|
| Standard | General-purpose, natural translation |
| SEO | Preserves keyword density and search intent |
| HTML | Translates only visible text, never touches tags |
| Technical | Enforces consistent Market Research terminology |

---

## Glossary System

Protected terms (company names, abbreviations, currencies, domain terms)
are replaced with unique tokens before the API call and restored after.
This guarantees 100% preservation of terms like IMARC Group, CAGR, USD, AI, etc.

Market Research section labels (Historical Period, Forecast Period, etc.)
are automatically translated to their standard Spanish equivalents.

---

## Adding Languages

In `config.py`, add your language to `LANGUAGES` and `LANG_FULL_NAMES`:

```python
LANGUAGES["ja"] = "Japanese"
LANG_FULL_NAMES["ja"] = "Japanese"
```

The prompts and all services will automatically pick up the new language.

---

## Logging

Two log types are written daily to `logs/`:

- `app_YYYYMMDD.log` — standard application log (INFO level)
- `translations_YYYYMMDD.jsonl` — structured JSON Lines audit trail

Each translation record includes: timestamp, mode, language, word count,
character count, processing time, TM hit flag, and any error details.
