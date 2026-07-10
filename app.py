"""
app.py — AI SEO Translation Studio
Main Streamlit application entry point.

Run with:
    streamlit run app.py
"""

import os
import io
import time
import streamlit as st

# ── Page config must be first Streamlit call ───────────────────────────────────
st.set_page_config(
    page_title="AI SEO Translation Studio",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Internal imports ───────────────────────────────────────────────────────────
from config import (
    APP_NAME, APP_VERSION,
    LANGUAGES, TRANSLATION_MODES, MODE_DESCRIPTIONS,
    DEFAULT_TARGET_LANG, HISTORY_LIMIT,
    NVIDIA_API_KEY,
)
from translator import Translator, TranslationError, APIKeyError
from glossary import glossary_manager, GlossaryManager
from utils import (
    text_stats, format_ms, format_bytes, is_supported_file,
    validate_file_size, save_upload, output_filename, truncate,
    detect_content_type,
)
from logger import translation_logger
from services.translation_memory import translation_memory
from services.html_service import html_service
from services.excel_service import excel_service
from services.docx_service import docx_service
from services.pptx_service import pptx_service
from services.seo_service import seo_service


# ══════════════════════════════════════════════════════════════════════════════
# CSS INJECTION
# ══════════════════════════════════════════════════════════════════════════════

def _load_css() -> None:
    css_path = os.path.join(os.path.dirname(__file__), "assets", "style.css")
    if os.path.exists(css_path):
        with open(css_path, encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# SESSION STATE
# ══════════════════════════════════════════════════════════════════════════════

def _init_session() -> None:
    defaults = {
        "api_key":        NVIDIA_API_KEY,
        "translator":     None,
        "history":        [],      # list of dicts
        "tm_stats":       None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def _get_translator() -> Translator | None:
    """Return a cached Translator or None if no valid key is set."""
    key = st.session_state.get("api_key", "").strip()
    if not key:
        return None
    # Re-use cached instance if key hasn't changed
    tr = st.session_state.get("translator")
    if tr is None or getattr(tr, "_client", None) is None:
        try:
            tr = Translator(api_key=key)
            st.session_state["translator"] = tr
        except APIKeyError:
            return None
    return tr


def _add_history(entry: dict) -> None:
    history: list = st.session_state["history"]
    history.insert(0, entry)
    if len(history) > HISTORY_LIMIT:
        history.pop()


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════

def render_sidebar() -> tuple[str, str, str]:
    """
    Render the sidebar and return (api_key, target_lang, mode).
    """
    with st.sidebar:
        # Logo / Title
        st.markdown(
            """
            <div style='text-align:center;padding:1rem 0 0.5rem'>
              <span style='font-size:2.5rem'>🌐</span>
              <h2 style='color:#fff;margin:0;font-size:1.1rem;font-weight:700'>
                AI SEO<br>Translation Studio
              </h2>
              <p style='color:#64748b;font-size:0.72rem;margin:0.25rem 0 0'>
                v{version}
              </p>
            </div>
            """.format(version=APP_VERSION),
            unsafe_allow_html=True,
        )

        st.divider()

        # ── API Key ────────────────────────────────────────────────────────────
        st.markdown("### 🔑 API Key")
        api_key = st.text_input(
            "NVIDIA API Key",
            value=st.session_state.get("api_key", ""),
            type="password",
            placeholder="nvapi-...",
            label_visibility="collapsed",
        )
        if api_key != st.session_state.get("api_key"):
            st.session_state["api_key"] = api_key
            st.session_state["translator"] = None  # reset on key change

        if api_key:
            st.success("API key set ✓", icon="🔒")
        else:
            st.warning("Enter your NVIDIA API key to start.", icon="⚠️")

        st.divider()

        # ── Language ───────────────────────────────────────────────────────────
        st.markdown("### 🌍 Target Language")
        lang_options = list(LANGUAGES.values())
        lang_codes   = list(LANGUAGES.keys())
        default_idx  = lang_codes.index(DEFAULT_TARGET_LANG)
        selected_lang_name = st.selectbox(
            "Language",
            options=lang_options,
            index=default_idx,
            label_visibility="collapsed",
        )
        target_lang = lang_codes[lang_options.index(selected_lang_name)]

        # ── Translation Mode ───────────────────────────────────────────────────
        st.markdown("### ⚙️ Translation Mode")
        mode = st.selectbox(
            "Mode",
            options=TRANSLATION_MODES,
            index=0,
            label_visibility="collapsed",
        )
        st.caption(MODE_DESCRIPTIONS.get(mode, ""))

        st.divider()

        # ── Translation Memory Stats ───────────────────────────────────────────
        st.markdown("### 💾 Translation Memory")
        tm_stats = translation_memory.stats()
        col1, col2 = st.columns(2)
        col1.metric("Entries", f"{tm_stats['total_entries']:,}")
        col2.metric("Cache Hits", f"{tm_stats['total_hits']:,}")
        st.caption(f"DB size: {format_bytes(tm_stats['db_size_bytes'])}")

        if st.button("🗑 Clear TM", use_container_width=True):
            n = translation_memory.clear()
            st.toast(f"Cleared {n} entries from Translation Memory.")

        st.divider()

        # ── History count ──────────────────────────────────────────────────────
        st.caption(f"Session history: {len(st.session_state['history'])} translations")

    return api_key, target_lang, mode


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — PLAIN TEXT
# ══════════════════════════════════════════════════════════════════════════════

def tab_text(translator: Translator | None, target_lang: str, mode: str) -> None:
    st.markdown("#### ✏️ Plain Text Translation")
    st.caption("Paste any text and translate instantly.")

    col_in, col_out = st.columns(2, gap="large")

    with col_in:
        st.markdown("**Source (English)**")
        source = st.text_area(
            "Source text",
            height=320,
            placeholder="Paste your text here…",
            label_visibility="collapsed",
        )
        stats = text_stats(source)
        st.caption(
            f"Words: **{stats['words']}** · "
            f"Chars: **{stats['chars']}** · "
            f"Sentences: **{stats['sentences']}**"
        )

    with col_out:
        st.markdown("**Translation**")
        result_placeholder = st.empty()

        use_tm    = st.checkbox("Use Translation Memory", value=False, key="text_use_tm")
        use_gloss = st.checkbox("Apply Glossary Protection", value=True, key="text_use_glos")

        if st.button("🚀 Translate", type="primary", use_container_width=True, key="btn_text"):
            if not translator:
                st.error("Please enter a valid NVIDIA API key in the sidebar.")
                return
            if not source.strip():
                st.warning("Source text is empty.")
                return

            with st.spinner("Translating…"):
                try:
                    result = translator.translate(
                        source,
                        target_lang=target_lang,
                        mode=mode,
                        use_tm=use_tm,
                        use_glossary=use_gloss,
                    )
                    translation = result["translation"]
                    tm_hit      = result["tm_hit"]
                    time_ms     = result["time_ms"]

                    # Display output
                    result_placeholder.markdown(
                        f'<div class="translation-box">{translation}</div>',
                        unsafe_allow_html=True,
                    )

                    # Badges
                    badge = "tm-badge" if tm_hit else "api-badge"
                    label = "⚡ From Cache" if tm_hit else "🤖 API"
                    st.markdown(
                        f'<span class="{badge}">{label}</span> '
                        f'<span style="font-size:.78rem;color:#64748b">{format_ms(time_ms)}</span>',
                        unsafe_allow_html=True,
                    )

                    # Download
                    st.download_button(
                        "⬇️ Download Translation",
                        data=translation.encode("utf-8"),
                        file_name="translation.txt",
                        mime="text/plain",
                        use_container_width=True,
                    )

                    # History
                    _add_history({
                        "mode":        mode,
                        "lang":        target_lang,
                        "source":      truncate(source, 80),
                        "translation": truncate(translation, 80),
                        "tm_hit":      tm_hit,
                        "time_ms":     time_ms,
                        "ts":          time.strftime("%H:%M:%S"),
                    })

                except (TranslationError, APIKeyError) as exc:
                    st.error(f"Translation failed: {exc}")
                except Exception as exc:
                    st.error(f"Unexpected error: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — HTML
# ══════════════════════════════════════════════════════════════════════════════

def tab_html(translator: Translator | None, target_lang: str, mode: str) -> None:
    st.markdown("#### 🏷️ HTML Translation")
    st.caption("Translates only visible text — all tags, attributes, and structure are preserved.")

    source_html = st.text_area(
        "Paste HTML",
        height=280,
        placeholder="<h1>Market Report</h1><p>The global market size...</p>",
        label_visibility="collapsed",
    )

    col1, col2 = st.columns([1, 1])
    with col1:
        use_tm = st.checkbox("Use Translation Memory", value=False, key="html_tm")
    with col2:
        use_gloss = st.checkbox("Glossary Protection", value=True, key="html_glos")

    if st.button("🚀 Translate HTML", type="primary", key="btn_html"):
        if not translator:
            st.error("API key required.")
            return
        if not source_html.strip():
            st.warning("HTML content is empty.")
            return

        valid, msg = html_service.validate_html(source_html)
        if not valid:
            st.error(f"Invalid HTML: {msg}")
            return

        progress = st.progress(0, text="Translating HTML…")

        def update_progress(current: int, total: int) -> None:
            if total:
                progress.progress(min(int(current / total * 100), 100), text=f"Node {current}/{total}")

        try:
            translated_html = html_service.translate(
                source_html,
                translator=translator,
                target_lang=target_lang,
                mode="HTML",
                use_tm=use_tm,
                on_progress=update_progress,
            )
            progress.empty()
            st.success("HTML translated successfully!")

            st.markdown("**Translated HTML (source)**")
            st.code(translated_html, language="html")

            st.markdown("**Preview**")
            st.components.v1.html(translated_html, height=400, scrolling=True)

            st.download_button(
                "⬇️ Download HTML",
                data=translated_html.encode("utf-8"),
                file_name="translated.html",
                mime="text/html",
                use_container_width=True,
            )

        except Exception as exc:
            progress.empty()
            st.error(f"Error: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — EXCEL
# ══════════════════════════════════════════════════════════════════════════════

def tab_excel(translator: Translator | None, target_lang: str, mode: str) -> None:
    st.markdown("#### 📊 Excel Translation")
    st.caption("Upload a workbook, select the columns to translate, and download the result.")

    uploaded = st.file_uploader(
        "Upload Excel file (.xlsx)",
        type=["xlsx", "xls"],
        key="excel_upload",
    )

    if not uploaded:
        return

    if not validate_file_size(uploaded.getvalue()):
        st.error("File exceeds the 50 MB limit.")
        return

    file_path = save_upload(uploaded.getvalue(), uploaded.name)

    # Sheet selector
    sheets = excel_service.get_sheets(file_path)
    sheet  = st.selectbox("Sheet", sheets) if len(sheets) > 1 else sheets[0]

    # Column selector
    columns = excel_service.get_columns(file_path, sheet)
    selected_cols = st.multiselect("Select columns to translate", columns)

    # Preview
    with st.expander("📋 Data Preview (first 5 rows)", expanded=False):
        preview_df = excel_service.preview(file_path, sheet, rows=5)
        st.dataframe(preview_df, use_container_width=True)

    # Options
    col1, col2, col3 = st.columns(3)
    with col1:
        add_suffix = st.checkbox("Add '_ES' column", value=True)
    with col2:
        use_tm = st.checkbox("Use TM", value=False, key="xl_tm")
    with col3:
        full_sheet = st.checkbox("All text cells", value=False)

    if st.button("🚀 Translate Excel", type="primary", key="btn_xl"):
        if not translator:
            st.error("API key required.")
            return
        if not selected_cols and not full_sheet:
            st.warning("Select at least one column or enable 'All text cells'.")
            return

        progress = st.progress(0, text="Translating Excel…")

        def upd(cur: int, tot: int) -> None:
            if tot:
                progress.progress(min(int(cur / tot * 100), 100), text=f"Row {cur}/{tot}")

        try:
            if full_sheet:
                result_bytes = excel_service.translate_full_sheet(
                    file_path, translator, target_lang, mode,
                    sheet_name=sheet, use_tm=use_tm, on_progress=upd,
                )
            else:
                result_bytes = excel_service.translate_columns(
                    file_path, selected_cols, translator, target_lang, mode,
                    sheet_name=sheet, add_suffix=add_suffix,
                    use_tm=use_tm, on_progress=upd,
                )
            progress.empty()
            st.success("Excel translated successfully!")

            out_name = output_filename(uploaded.name, "_translated")
            st.download_button(
                "⬇️ Download Translated Excel",
                data=result_bytes,
                file_name=out_name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

        except Exception as exc:
            progress.empty()
            st.error(f"Error: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — DOCX
# ══════════════════════════════════════════════════════════════════════════════

def tab_docx(translator: Translator | None, target_lang: str, mode: str) -> None:
    st.markdown("#### 📄 Word Document Translation")
    st.caption("Translate .docx files preserving all formatting, tables, and styles.")

    uploaded = st.file_uploader(
        "Upload Word document (.docx)",
        type=["docx"],
        key="docx_upload",
    )

    if not uploaded:
        return
    if not validate_file_size(uploaded.getvalue()):
        st.error("File exceeds the 50 MB limit.")
        return

    file_path = save_upload(uploaded.getvalue(), uploaded.name)

    # Stats
    stats = docx_service.get_stats(file_path)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Paragraphs", stats["paragraphs"])
    c2.metric("Words",      f"{stats['words']:,}")
    c3.metric("Characters", f"{stats['chars']:,}")
    c4.metric("Tables",     stats["tables"])

    use_tm = st.checkbox("Use Translation Memory", value=False, key="docx_tm")

    if st.button("🚀 Translate Document", type="primary", key="btn_docx"):
        if not translator:
            st.error("API key required.")
            return

        progress = st.progress(0, text="Translating document…")

        def upd(cur: int, tot: int) -> None:
            if tot:
                progress.progress(min(int(cur / tot * 100), 100), text=f"Paragraph {cur}/{tot}")

        try:
            result_bytes = docx_service.translate(
                file_path, translator, target_lang, mode,
                use_tm=use_tm, on_progress=upd,
            )
            progress.empty()
            st.success("Document translated successfully!")

            out_name = output_filename(uploaded.name, "_ES")
            st.download_button(
                "⬇️ Download Translated Document",
                data=result_bytes,
                file_name=out_name,
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
            )

        except Exception as exc:
            progress.empty()
            st.error(f"Error: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — PPTX
# ══════════════════════════════════════════════════════════════════════════════

def tab_pptx(translator: Translator | None, target_lang: str, mode: str) -> None:
    st.markdown("#### 📊 PowerPoint Translation")
    st.caption("Translate slide text while preserving all layouts, fonts, and design.")

    uploaded = st.file_uploader(
        "Upload PowerPoint file (.pptx)",
        type=["pptx"],
        key="pptx_upload",
    )

    if not uploaded:
        return
    if not validate_file_size(uploaded.getvalue()):
        st.error("File exceeds the 50 MB limit.")
        return

    file_path = save_upload(uploaded.getvalue(), uploaded.name)

    stats = pptx_service.get_stats(file_path)
    c1, c2, c3 = st.columns(3)
    c1.metric("Slides",  stats["slides"])
    c2.metric("Shapes",  stats["shapes"])
    c3.metric("Words",   f"{stats['words']:,}")

    col1, col2 = st.columns(2)
    with col1:
        translate_notes = st.checkbox("Translate speaker notes", value=True)
    with col2:
        use_tm = st.checkbox("Use Translation Memory", value=False, key="pptx_tm")

    if st.button("🚀 Translate Presentation", type="primary", key="btn_pptx"):
        if not translator:
            st.error("API key required.")
            return

        progress = st.progress(0, text="Translating slides…")

        def upd(cur: int, tot: int) -> None:
            if tot:
                progress.progress(min(int(cur / tot * 100), 100), text=f"Slide {cur+1}/{tot}")

        try:
            result_bytes = pptx_service.translate(
                file_path, translator, target_lang, mode,
                translate_notes=translate_notes,
                use_tm=use_tm, on_progress=upd,
            )
            progress.empty()
            st.success("Presentation translated successfully!")

            out_name = output_filename(uploaded.name, "_ES")
            st.download_button(
                "⬇️ Download Translated Presentation",
                data=result_bytes,
                file_name=out_name,
                mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                use_container_width=True,
            )

        except Exception as exc:
            progress.empty()
            st.error(f"Error: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 6 — BATCH
# ══════════════════════════════════════════════════════════════════════════════

def tab_batch(translator: Translator | None, target_lang: str, mode: str) -> None:
    st.markdown("#### 📦 Batch Translation")
    st.caption("Upload multiple files (.txt, .html, .md, .json) and download a ZIP of translations.")

    uploaded_files = st.file_uploader(
        "Upload files (TXT, HTML, MD, JSON)",
        type=["txt", "html", "htm", "md", "json"],
        accept_multiple_files=True,
        key="batch_upload",
    )

    if not uploaded_files:
        return

    st.info(f"{len(uploaded_files)} file(s) selected.")
    use_tm = st.checkbox("Use Translation Memory", value=False, key="batch_tm")

    if st.button("🚀 Translate All", type="primary", key="btn_batch"):
        if not translator:
            st.error("API key required.")
            return

        import zipfile

        results: dict[str, bytes] = {}
        overall = st.progress(0, text="Processing files…")

        for fi, uploaded in enumerate(uploaded_files):
            overall.progress(
                int(fi / len(uploaded_files) * 100),
                text=f"Translating {uploaded.name}…",
            )
            raw = uploaded.getvalue()
            if not validate_file_size(raw):
                st.warning(f"{uploaded.name}: exceeds size limit, skipped.")
                continue

            ext = os.path.splitext(uploaded.name)[1].lower()
            text = raw.decode("utf-8", errors="replace")

            try:
                if ext in (".html", ".htm"):
                    translated = html_service.translate(
                        text, translator, target_lang, mode="HTML", use_tm=use_tm
                    )
                else:
                    result = translator.translate(text, target_lang, mode, use_tm=use_tm)
                    translated = result["translation"]

                out_name = output_filename(uploaded.name, "_ES")
                results[out_name] = translated.encode("utf-8")

            except Exception as exc:
                st.error(f"{uploaded.name}: {exc}")

        overall.empty()

        if results:
            # Bundle into ZIP
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for fname, data in results.items():
                    zf.writestr(fname, data)
            buf.seek(0)

            st.success(f"{len(results)} file(s) translated.")
            st.download_button(
                "⬇️ Download ZIP",
                data=buf.read(),
                file_name="translations.zip",
                mime="application/zip",
                use_container_width=True,
            )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 7 — SEO ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

def tab_seo(translator: Translator | None, target_lang: str, mode: str) -> None:
    st.markdown("#### 🔍 SEO Analysis")
    st.caption("Analyse keyword density, readability, and translation quality.")

    col_l, col_r = st.columns(2)
    with col_l:
        source = st.text_area("Source text (English)", height=200, key="seo_src")
    with col_r:
        translation = st.text_area("Translation (paste or auto-fill below)", height=200, key="seo_tr")

    if st.button("🚀 Translate + Analyse", type="primary", key="btn_seo"):
        if not source.strip():
            st.warning("Source text is required.")
            return
        if not translation.strip() and not translator:
            st.error("Provide a translation or set your API key to auto-translate.")
            return

        with st.spinner("Processing…"):
            # Translate if no manual translation provided
            if not translation.strip():
                try:
                    res = translator.translate(source, target_lang, mode="SEO")
                    translation = res["translation"]
                    st.session_state["seo_tr"] = translation
                except Exception as exc:
                    st.error(f"Translation failed: {exc}")
                    return

            report = seo_service.compare(source, translation)

        # ── Source Stats ───────────────────────────────────────────────────────
        st.markdown("---")
        st.markdown("**Source Statistics**")
        ss = report["source_stats"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Words",     ss["word_count"])
        c2.metric("Sentences", ss["sentence_count"])
        c3.metric("Readability", ss["readability_label"])
        c4.metric("Score",     f"{ss['readability_score']:.0f}")

        # ── Translation Stats ──────────────────────────────────────────────────
        st.markdown("**Translation Statistics**")
        ts = report["translation_stats"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Words",      ts["word_count"],
                  delta=f"{ts['word_count']-ss['word_count']:+d}")
        c2.metric("Sentences",  ts["sentence_count"])
        c3.metric("Readability", ts["readability_label"])
        c4.metric("Length Ratio", f"{report['length_ratio']:.2f}x")

        # ── Keyword Density ────────────────────────────────────────────────────
        with st.expander("📊 Keyword Density", expanded=True):
            kd_col1, kd_col2 = st.columns(2)
            with kd_col1:
                st.caption("Source Top Keywords")
                for kw, pct in list(ss["keyword_density"].items())[:8]:
                    st.markdown(f"`{kw}` — {pct}%")
            with kd_col2:
                st.caption("Translation Top Keywords")
                for kw, pct in list(ts["keyword_density"].items())[:8]:
                    st.markdown(f"`{kw}` — {pct}%")

        # ── Issues ─────────────────────────────────────────────────────────────
        if report["issues"]:
            st.warning("**SEO Issues Detected:**\n" + "\n".join(f"• {i}" for i in report["issues"]))
        else:
            st.success("No SEO issues detected — translation looks good!")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 8 — TRANSLATION MEMORY BROWSER
# ══════════════════════════════════════════════════════════════════════════════

def tab_tm_browser() -> None:
    st.markdown("#### 💾 Translation Memory Browser")
    st.caption("Search, browse, and manage cached translations.")

    stats = translation_memory.stats()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Entries",  f"{stats['total_entries']:,}")
    c2.metric("Cache Hits",     f"{stats['total_hits']:,}")
    c3.metric("Languages",      stats["unique_languages"])
    c4.metric("DB Size",        format_bytes(stats["db_size_bytes"]))

    st.markdown("---")
    query = st.text_input("🔍 Search translations", placeholder="Type a keyword…")

    if query:
        rows = translation_memory.search(query, limit=30)
    else:
        rows = translation_memory.recent(limit=20)

    if not rows:
        st.info("No entries found.")
        return

    for row in rows:
        with st.expander(
            f"[{row['target_lang'].upper()}] [{row['mode']}] {truncate(row['source_text'], 70)}",
            expanded=False,
        ):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Source**")
                st.text(row["source_text"])
            with col2:
                st.markdown("**Translation**")
                st.text(row["translation"])
            st.caption(f"Saved: {row['created_at']} · Hits: {row['hit_count']}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 9 — HISTORY
# ══════════════════════════════════════════════════════════════════════════════

def tab_history() -> None:
    st.markdown("#### 📜 Session History")
    history = st.session_state.get("history", [])
    if not history:
        st.info("No translations yet in this session.")
        return

    if st.button("🗑 Clear History", key="btn_clear_hist"):
        st.session_state["history"] = []
        st.rerun()

    for i, entry in enumerate(history):
        badge_color = "#dcfce7" if entry.get("tm_hit") else "#dbeafe"
        badge_text  = "⚡ Cache" if entry.get("tm_hit") else "🤖 API"
        st.markdown(
            f"""
            <div class="history-row">
              <div style="display:flex;justify-content:space-between;align-items:center">
                <span style="font-size:.72rem;color:#94a3b8">{entry.get('ts','')} ·
                  <b>{entry.get('mode','')}</b> → <b>{entry.get('lang','')}</b>
                </span>
                <span style="background:{badge_color};
                  padding:0.1rem 0.5rem;border-radius:20px;
                  font-size:.72rem;font-weight:600">{badge_text}</span>
              </div>
              <div style="margin-top:.4rem;font-size:.82rem;color:#374151">
                {entry.get('source','')}
              </div>
              <div style="margin-top:.2rem;font-size:.82rem;color:#2563eb">
                ↳ {entry.get('translation','')}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 10 — GLOSSARY MANAGER
# ══════════════════════════════════════════════════════════════════════════════

def tab_glossary() -> None:
    st.markdown("#### 📖 Glossary Manager")
    st.caption("View and extend the list of protected terms.")

    # Show existing protected terms
    with st.expander("Protected Terms (preserved unchanged)", expanded=False):
        terms = glossary_manager.get_all_protected_terms()
        cols = st.columns(3)
        for i, term in enumerate(terms):
            cols[i % 3].markdown(f"• `{term}`")

    st.markdown("---")
    st.markdown("**Add Custom Term**")
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        new_term = st.text_input("Term to protect", placeholder="MyCompany Inc.")
    with col2:
        replacement = st.text_input("Replacement (blank = same)", placeholder="Optional")
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("➕ Add", key="btn_add_term"):
            if new_term.strip():
                glossary_manager.add_term(new_term.strip(), replacement.strip() or None)
                st.success(f"'{new_term}' added to glossary.")
            else:
                st.warning("Term cannot be empty.")

    # Market research translation glossary
    with st.expander("Market Research Term Translations", expanded=False):
        from glossary import TRANSLATION_GLOSSARY
        for en, es in TRANSLATION_GLOSSARY.items():
            st.markdown(f"**{en}** → {es}")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    _load_css()
    _init_session()

    # Header
    st.markdown(
        """
        <div class="app-header">
          <h1>🌐 AI SEO Translation Studio</h1>
          <p>Market Research Report Translation — Powered by NVIDIA Riva</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Sidebar
    api_key, target_lang, mode = render_sidebar()

    # Build translator (None if no key)
    translator = _get_translator()

    # Tabs
    tabs = st.tabs([
        "✏️ Text",
        "🏷️ HTML",
        "📊 Excel",
        "📄 DOCX",
        "🎯 PPT",
        "📦 Batch",
        "🔍 SEO",
        "💾 TM",
        "📜 History",
        "📖 Glossary",
    ])

    with tabs[0]:
        tab_text(translator, target_lang, mode)
    with tabs[1]:
        tab_html(translator, target_lang, mode)
    with tabs[2]:
        tab_excel(translator, target_lang, mode)
    with tabs[3]:
        tab_docx(translator, target_lang, mode)
    with tabs[4]:
        tab_pptx(translator, target_lang, mode)
    with tabs[5]:
        tab_batch(translator, target_lang, mode)
    with tabs[6]:
        tab_seo(translator, target_lang, mode)
    with tabs[7]:
        tab_tm_browser()
    with tabs[8]:
        tab_history()
    with tabs[9]:
        tab_glossary()


if __name__ == "__main__":
    main()
