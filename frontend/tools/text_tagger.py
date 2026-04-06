"""
Text Tagging Tool
Generates a self-contained HTML page for annotating text data.

Supports three annotation modes:
- binary:     Yes/No classification per text
- multiclass: Multiple category labels per text
- freetext:   Free-form text extraction per text

Usage:
    from frontend.text_tagger import render_tagging_html, save_and_open, AnnotationMode

    html = render_tagging_html(df, AnnotationMode.BINARY, {"question": "Is this positive?"})
    save_and_open(html, "tagging.html")
"""
import json
import os
import webbrowser
from enum import Enum
from typing import Any, Dict

from frontend.logo import LOGO_DATA_URI as _LOGO_DATA_URI

import pandas as pd


class AnnotationMode(str, Enum):
    """Supported annotation modes for the tagging tool."""

    BINARY = "binary"
    MULTICLASS = "multiclass"
    FREETEXT = "freetext"


def render_tagging_html(
    texts_df: pd.DataFrame,
    mode: AnnotationMode,
    config: Dict[str, Any],
    title: str = "Skynet - תיוג טקסטים",
) -> str:
    """Generate a self-contained HTML annotation page.

    Args:
        texts_df: DataFrame with 'id' and 'text' columns. Extra columns are exported.
        mode: Annotation mode (binary, multiclass, freetext).
        config: Mode-specific configuration:
            - binary:     {"question": "..."}
            - multiclass: {"categories": [{"id": "x", "label": "y"}, ...]}
            - freetext:   {"prompt": "...", "placeholder": "..."}
        title: Page title (Hebrew).

    Returns:
        Complete HTML string.
    """
    mode = AnnotationMode(mode)

    if "id" not in texts_df.columns or "text" not in texts_df.columns:
        raise ValueError("texts_df must have 'id' and 'text' columns")

    texts_df = texts_df.sort_values("id").reset_index(drop=True)

    texts_json = json.dumps(texts_df.to_dict(orient="records"), default=str, ensure_ascii=False)
    mode_json = json.dumps(mode.value)
    config_json = json.dumps(config, default=str, ensure_ascii=False)
    columns_json = json.dumps(list(texts_df.columns), ensure_ascii=False)

    html = f'''<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Orbitron:wght@400;700&display=swap" rel="stylesheet">
<link rel="icon" type="image/svg+xml" href="{_LOGO_DATA_URI}">
<title>{title}</title>
<style>
    :root {{
        /* Skynet Theme - Navy, Steel, Cyan (matching logo) */
        --primary: #51A2C9;
        --primary-dark: #2178A6;
        --primary-light: #7BB8D4;
        --primary-bg: rgba(81,162,201,0.1);
        --primary-bg-hover: rgba(81,162,201,0.18);

        --g-900: #C1D0D6;
        --g-800: #97ABB5;
        --g-700: #7B9AA8;
        --g-600: #628494;
        --g-500: #4A6B7A;
        --g-400: #274A61;
        --g-300: #1E3A4F;
        --g-200: #153448;
        --g-150: #0D2B3E;
        --g-100: #072233;
        --g-50: #011E32;
        --white: #0D2B3E;

        --green: #00E676;
        --green-bg: #0A2D14;
        --red: #FF4444;
        --red-bg: #2D0A0A;

        --radius: 0.75rem;
        --radius-sm: 0.5rem;
        --radius-md: 0.625rem;
        --radius-lg: 1rem;
        --radius-xl: 1.25rem;
        --radius-pill: 100px;
        --shadow-sm: 0 1px 3px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.06);
        --shadow-md: 0 4px 12px rgba(0,0,0,0.08);
        --shadow-lg: 0 8px 24px rgba(0,0,0,0.1);
        --transition: all 0.2s ease;
    }}

    * {{ box-sizing: border-box; margin: 0; padding: 0; }}

    ::-webkit-scrollbar {{ width: 5px; }}
    ::-webkit-scrollbar-track {{ background: transparent; }}
    ::-webkit-scrollbar-thumb {{ background: var(--g-300); border-radius: 10px; }}
    * {{ scrollbar-width: thin; scrollbar-color: var(--g-300) transparent; }}

    body {{
        font-family: 'Share Tech Mono', 'Courier New', Consolas, monospace, 'Arial Hebrew';
        background: var(--g-100);
        color: var(--g-900);
        line-height: 1.5;
        direction: rtl;
        height: 100vh;
        overflow: hidden;
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
    }}

    /* Layout — sidebar + main */
    .app {{
        display: grid;
        grid-template-columns: 240px 1fr;
        height: 100vh;
    }}

    /* Sidebar */
    .sidebar {{
        background: var(--g-50);
        border-left: 1px solid var(--g-200);
        padding: 20px 16px;
        display: flex;
        flex-direction: column;
        gap: 20px;
        overflow-y: auto;
    }}

    .sidebar-title {{
        font-family: 'Orbitron', 'Share Tech Mono', monospace;
        font-size: 0.95rem;
        font-weight: 700;
        color: var(--primary);
        text-shadow: 0 0 8px rgba(81,162,201,0.5);
        letter-spacing: 1px;
    }}

    .sidebar-section {{
        display: flex;
        flex-direction: column;
        gap: 8px;
    }}

    .sidebar-label {{
        font-size: 0.65rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.6px;
        color: var(--g-400);
        display: flex;
        align-items: center;
        gap: 6px;
    }}

    .sidebar-label svg {{
        width: 14px;
        height: 14px;
    }}

    /* Progress */
    .progress-bar-track {{
        height: 4px;
        background: var(--g-150);
        border-radius: 2px;
        overflow: hidden;
    }}

    .progress-bar-fill {{
        height: 100%;
        background: var(--primary);
        border-radius: 2px;
        transition: width 0.3s ease;
        width: 0%;
    }}

    .progress-text {{
        font-size: 0.8rem;
        color: var(--g-600);
        font-variant-numeric: tabular-nums;
    }}

    .progress-text strong {{ color: var(--primary); }}

    /* Distribution */
    .dist-list {{
        display: flex;
        flex-direction: column;
        gap: 3px;
    }}

    .dist-row {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        font-size: 0.78rem;
        padding: 4px 8px;
        border-radius: 6px;
        background: var(--g-50);
    }}

    .dist-label {{ color: var(--g-700); font-weight: 500; }}
    .dist-count {{
        color: var(--g-900);
        font-weight: 700;
        font-variant-numeric: tabular-nums;
        min-width: 20px;
        text-align: center;
    }}

    /* Search */
    .search-input {{
        width: 100%;
        padding: 7px 10px;
        border: 1px solid var(--g-200);
        border-radius: 6px;
        font-family: inherit;
        font-size: 0.8rem;
        color: var(--g-900);
        background: var(--white);
        direction: rtl;
        transition: border-color 0.15s ease;
    }}

    .search-input:focus {{
        outline: none;
        border-color: var(--primary);
        box-shadow: 0 0 0 3px rgba(124,154,130,0.15);
    }}

    .search-nav {{
        display: flex;
        align-items: center;
        gap: 4px;
    }}

    .search-nav-btn {{
        padding: 2px 8px;
        border: 1px solid var(--g-200);
        background: var(--white);
        color: var(--g-600);
        border-radius: 4px;
        cursor: pointer;
        font-family: inherit;
        font-size: 0.7rem;
        transition: var(--transition);
    }}

    .search-nav-btn:hover {{ background: var(--g-50); }}

    .search-count {{
        font-size: 0.7rem;
        color: var(--g-500);
        font-variant-numeric: tabular-nums;
    }}

    /* Export button */
    .export-btn {{
        width: 100%;
        padding: 12px;
        background: var(--primary);
        color: var(--white);
        border: none;
        border-radius: var(--radius);
        font-family: inherit;
        font-size: 0.88rem;
        font-weight: 600;
        cursor: pointer;
        transition: var(--transition);
        margin-top: auto;
        box-shadow: 0 2px 8px rgba(124,154,130,0.3);
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
    }}

    .export-btn:hover {{
        background: var(--primary-dark);
        transform: translateY(-1px);
        box-shadow: 0 4px 14px rgba(124,154,130,0.35);
    }}

    .export-btn:active {{ transform: scale(0.98); }}

    /* Shortcuts modal */
    .modal-overlay {{
        display: none;
        position: fixed;
        top: 0; left: 0;
        width: 100%; height: 100%;
        background: rgba(0,0,0,0.35);
        z-index: 9000;
        align-items: center;
        justify-content: center;
    }}

    .modal-overlay.open {{ display: flex; }}

    .modal {{
        background: var(--white);
        border-radius: var(--radius-lg);
        box-shadow: 0 20px 60px rgba(0,0,0,0.18);
        padding: 24px;
        min-width: 300px;
        max-width: 380px;
        direction: rtl;
    }}

    .modal-header {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 16px;
        padding-bottom: 12px;
        border-bottom: 1px solid var(--g-150);
    }}

    .modal-title {{
        font-size: 0.95rem;
        font-weight: 700;
        color: var(--g-900);
    }}

    .modal-close {{
        background: none;
        border: none;
        cursor: pointer;
        color: var(--g-400);
        font-size: 1.2rem;
        padding: 2px 6px;
        border-radius: 4px;
        transition: var(--transition);
        line-height: 1;
    }}

    .modal-close:hover {{ color: var(--g-900); background: var(--g-100); }}

    .shortcuts-list {{
        display: flex;
        flex-direction: column;
        gap: 6px;
    }}

    .shortcut-row {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        font-size: 0.8rem;
        color: var(--g-600);
        padding: 3px 0;
    }}

    kbd {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-width: 24px;
        height: 22px;
        padding: 0 6px;
        background: var(--g-100);
        border: 1px solid var(--g-200);
        border-radius: 4px;
        font-family: inherit;
        font-size: 0.7rem;
        font-weight: 600;
        color: var(--g-700);
    }}

    /* Main content */
    .main {{
        padding: 20px 28px;
        display: flex;
        flex-direction: column;
        gap: 12px;
        overflow: hidden;
    }}

    /* Navigation controls — bottom bar */
    .nav-controls {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-shrink: 0;
        gap: 15px;
    }}

    .nav-center {{
        display: flex;
        align-items: center;
        gap: 8px;
    }}

    .nav-btn {{
        padding: 12px 24px;
        background: var(--g-800);
        color: var(--white);
        border: none;
        border-radius: var(--radius);
        cursor: pointer;
        font-family: inherit;
        font-size: 0.9rem;
        font-weight: 600;
        transition: var(--transition);
        box-shadow: 0 2px 8px rgba(0,0,0,0.15);
        display: flex;
        align-items: center;
        gap: 8px;
    }}

    .nav-btn svg {{
        width: 18px;
        height: 18px;
    }}

    .nav-btn:hover:not(:disabled) {{
        background: var(--g-700);
        transform: translateY(-1px);
        box-shadow: var(--shadow-md);
    }}

    .nav-btn:active:not(:disabled) {{
        transform: scale(0.98);
    }}

    .nav-btn:disabled {{
        opacity: 0.4;
        cursor: not-allowed;
        background: var(--g-400);
        box-shadow: none;
    }}

    .nav-btn-secondary {{
        background: var(--white);
        color: var(--g-700);
        border: 1px solid var(--g-200);
        box-shadow: var(--shadow-sm);
    }}

    .nav-btn-secondary svg {{
        width: 16px;
        height: 16px;
    }}

    .nav-btn-secondary:hover:not(:disabled) {{
        background: var(--g-50);
        border-color: var(--g-300);
        box-shadow: var(--shadow-md);
    }}

    .nav-btn-secondary:disabled {{
        background: var(--white);
        opacity: 0.4;
    }}

    /* Text card */
    .text-card {{
        flex: 1;
        background: var(--white);
        border: 1px solid var(--g-200);
        border-radius: var(--radius-lg);
        box-shadow: var(--shadow-sm);
        display: flex;
        flex-direction: column;
        overflow: hidden;
        min-height: 0;
    }}

    .text-card-header {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 8px 16px;
        border-bottom: 1px solid var(--g-150);
        flex-shrink: 0;
    }}

    .text-card-id {{
        font-size: 0.75rem;
        font-weight: 600;
        color: var(--g-400);
        font-variant-numeric: tabular-nums;
    }}

    .text-card-link {{
        font-size: 0.75rem;
        color: var(--g-400);
        text-decoration: none;
        transition: var(--transition);
    }}

    .text-card-link:hover {{ color: var(--g-900); text-decoration: underline; }}

    .text-card-body {{
        flex: 1;
        padding: 28px 32px;
        font-size: 1.1rem;
        line-height: 2;
        color: var(--g-800);
        white-space: pre-wrap;
        word-wrap: break-word;
        overflow-y: auto;
    }}

    /* Annotation card — same size as text card */
    .annotation-card {{
        flex: 1;
        background: var(--white);
        border: 1px solid var(--g-200);
        border-radius: var(--radius-lg);
        padding: 24px 28px;
        box-shadow: var(--shadow-sm);
        display: flex;
        flex-direction: column;
        justify-content: center;
        min-height: 0;
        overflow: hidden;
    }}

    .annotation-label {{
        font-size: 0.82rem;
        font-weight: 600;
        color: var(--g-500);
        margin-bottom: 16px;
        text-align: center;
    }}

    /* Unified selection list — used by both binary and multiclass */
    .selection-list {{
        display: flex;
        flex-direction: column;
        gap: 6px;
        flex: 1;
        overflow-y: auto;
        min-height: 0;
    }}

    .selection-item {{
        flex: 1;
        min-height: 0;
        border: 1px solid var(--g-200);
        border-radius: var(--radius);
        background: var(--white);
        cursor: pointer;
        transition: var(--transition);
        font-family: inherit;
        font-size: 1rem;
        font-weight: 500;
        color: var(--g-700);
        user-select: none;
        box-shadow: var(--shadow-sm);
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 10px;
        padding: 8px 20px;
    }}

    .selection-item:hover {{
        border-color: var(--g-300);
        background: var(--g-50);
        box-shadow: var(--shadow-md);
    }}

    .selection-item .key-hint {{
        font-size: 0.7rem;
        font-weight: 700;
        color: var(--g-400);
    }}

    .selection-item.selected {{
        background: var(--primary);
        border-color: var(--primary);
        color: var(--white);
        box-shadow: 0 2px 8px rgba(124,154,130,0.35);
    }}

    .selection-item.selected .key-hint {{
        color: rgba(255,255,255,0.6);
    }}

    /* Binary-specific selected states */
    .selection-item.selected-yes {{
        background: var(--green-bg);
        border-color: var(--green);
        color: var(--green);
        box-shadow: 0 2px 8px rgba(76,175,80,0.25);
    }}

    .selection-item.selected-yes .key-hint {{ color: rgba(76,175,80,0.5); }}

    .selection-item.selected-no {{
        background: var(--red-bg);
        border-color: var(--red);
        color: var(--red);
        box-shadow: 0 2px 8px rgba(229,115,115,0.3);
    }}

    .selection-item.selected-no .key-hint {{ color: rgba(229,115,115,0.6); }}

    /* Adaptive: compact mode for 7+ items */
    .selection-list.compact {{
        gap: 4px;
    }}

    .selection-list.compact .selection-item {{
        padding: 2px 12px;
        font-size: 0.85rem;
        gap: 6px;
    }}

    .selection-list.compact .selection-item .key-hint {{
        font-size: 0.6rem;
        min-width: 16px;
        height: 16px;
    }}

    /* Freetext — spans full card height */
    #freetextPanel {{
        flex: 1;
        display: flex;
        flex-direction: column;
    }}

    .freetext-input {{
        width: 100%;
        flex: 1;
        padding: 16px 18px;
        border: 1px solid var(--g-200);
        border-radius: var(--radius);
        font-family: inherit;
        font-size: 1rem;
        color: var(--g-900);
        background: var(--white);
        resize: none;
        direction: rtl;
        line-height: 1.7;
        transition: border-color 0.15s ease;
    }}

    .freetext-input:focus {{
        outline: none;
        border-color: var(--primary);
        box-shadow: 0 0 0 3px rgba(124,154,130,0.15);
    }}

    /* Tagged dot */
    .tagged-dot {{
        display: inline-block;
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: var(--primary);
        margin-inline-start: 6px;
        vertical-align: middle;
    }}

    /* Confetti */
    .confetti-container {{
        position: fixed;
        top: 0; left: 0;
        width: 100%; height: 100%;
        pointer-events: none;
        z-index: 9999;
        overflow: hidden;
    }}

    .confetti {{
        position: absolute;
        width: 10px; height: 10px;
        opacity: 0;
        animation: confetti-fall 3s ease-out forwards;
    }}

    .confetti.circle {{ border-radius: 50%; }}
    .confetti.square {{ border-radius: 2px; }}
    .confetti.rect {{ width: 6px; height: 14px; border-radius: 2px; }}

    @keyframes confetti-fall {{
        0% {{ opacity: 1; transform: translateY(-100px) rotate(0deg); }}
        100% {{ opacity: 0; transform: translateY(100vh) rotate(720deg); }}
    }}

    @media (max-width: 768px) {{
        .app {{ grid-template-columns: 1fr; }}
        .sidebar {{
            height: auto;
            border-left: none;
            border-bottom: 1px solid var(--g-200);
            flex-direction: row;
            flex-wrap: wrap;
            padding: 12px;
        }}
        .sidebar-section {{ flex: 1; min-width: 140px; }}
        .main {{ padding: 12px; }}
        .nav-controls {{ flex-wrap: wrap; gap: 8px; }}
        .nav-btn {{ padding: 8px 14px; font-size: 0.82rem; }}
        .nav-center {{ order: 3; width: 100%; justify-content: center; }}
    }}

        /* Skynet Scan Lines */
        body::before {{
            content: '';
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: repeating-linear-gradient(
                0deg,
                rgba(0, 0, 0, 0.06) 0px,
                rgba(0, 0, 0, 0.06) 1px,
                transparent 1px,
                transparent 3px
            );
            pointer-events: none;
            z-index: 9999;
        }}

        /* Vignette */
        body::after {{
            content: '';
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: radial-gradient(
                ellipse at center,
                transparent 60%,
                rgba(0, 0, 0, 0.35) 100%
            );
            pointer-events: none;
            z-index: 9998;
        }}
</style>
</head>
<body>
<div class="app">
    <!-- Sidebar -->
    <aside class="sidebar">
        <div style="display: flex; align-items: center; gap: 10px;">
            <img src="{_LOGO_DATA_URI}" alt="Skynet" style="height: 32px; width: 32px; filter: drop-shadow(0 0 6px rgba(81, 162, 201, 0.4));">
            <div class="sidebar-title">{title}</div>
        </div>

        <div class="sidebar-section">
            <div class="sidebar-label"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12.586 2.586A2 2 0 0 0 11.172 2H4a2 2 0 0 0-2 2v7.172a2 2 0 0 0 .586 1.414l8.704 8.704a2.426 2.426 0 0 0 3.42 0l6.58-6.58a2.426 2.426 0 0 0 0-3.42z"/><circle cx="7.5" cy="7.5" r=".5" fill="currentColor"/></svg>התקדמות</div>
            <div class="progress-bar-track"><div class="progress-bar-fill" id="progressFill"></div></div>
            <div class="progress-text"><strong id="taggedCount">0</strong> / <span id="totalItems">0</span> תויגו</div>
        </div>

        <div class="sidebar-section">
            <div class="sidebar-label"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v16a2 2 0 0 0 2 2h16"/><path d="M18 17V9"/><path d="M13 17V5"/><path d="M8 17v-3"/></svg>התפלגות</div>
            <div class="dist-list" id="distList"></div>
        </div>

        <div class="sidebar-section">
            <div class="sidebar-label"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21 21-4.34-4.34"/><circle cx="11" cy="11" r="8"/></svg>חיפוש</div>
            <input class="search-input" id="searchInput" type="text" placeholder="חפש בטקסטים...">
            <div class="search-nav" id="searchNav" style="display:none">
                <button class="search-nav-btn" onclick="searchNext()">הבא</button>
                <button class="search-nav-btn" onclick="searchPrev()">הקודם</button>
                <span class="search-count" id="searchCount"></span>
            </div>
        </div>

        <button class="export-btn" onclick="exportCSV()"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:16px;height:16px"><path d="M12 15V3"/><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/></svg>ייצוא CSV</button>
    </aside>

    <!-- Shortcuts modal -->
    <div class="modal-overlay" id="shortcutsModal">
        <div class="modal">
            <div class="modal-header">
                <span class="modal-title">קיצורי מקשים</span>
                <button class="modal-close" onclick="toggleShortcutsModal()">&times;</button>
            </div>
            <div class="shortcuts-list" id="shortcutsList"></div>
        </div>
    </div>

    <!-- Main -->
    <main class="main">
        <!-- Text card -->
        <div class="text-card">
            <div class="text-card-header">
                <span class="text-card-id" id="textIdBadge">1 / 1</span>
                <span id="taggedDot" style="display:none"><span class="tagged-dot"></span></span>
                <a class="text-card-link" id="textLinkEl" href="#" target="_blank" style="display:none">קישור &#8599;</a>
            </div>
            <div class="text-card-body" id="textDisplay"></div>
        </div>

        <!-- Annotation -->
        <div class="annotation-card">
            <div class="annotation-label" id="annotationLabel"></div>

            <div id="binaryPanel" style="display:none;flex:1;flex-direction:column">
                <div class="selection-list" id="binaryList"></div>
            </div>

            <div id="multiclassPanel" style="display:none;flex:1;flex-direction:column">
                <div class="selection-list" id="categoriesGrid"></div>
            </div>

            <div id="freetextPanel" style="display:none">
                <textarea class="freetext-input" id="freetextInput"></textarea>
            </div>
        </div>

        <!-- Navigation -->
        <div class="nav-controls">
            <button class="nav-btn" id="prevBtn" onclick="navigate(-1)">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
                הקודם
            </button>
            <div class="nav-center">
                <button class="nav-btn nav-btn-secondary" id="jumpFirstBtn" onclick="showText(0)">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.971 4.285A2 2 0 0 1 21 6v12a2 2 0 0 1-3.029 1.715l-9.997-5.998a2 2 0 0 1-.003-3.432z"/><path d="M3 20V4"/></svg>
                    התחלה
                </button>
                <button class="nav-btn nav-btn-secondary" id="jumpUntaggedBtn" onclick="jumpToUntagged()">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M8 12h8"/></svg>
                    לא מתויג
                </button>
            </div>
            <button class="nav-btn" id="nextBtn" onclick="navigate(1)">
                הבא
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
            </button>
        </div>
    </main>
</div>

<script>
    var TEXTS = {texts_json};
    var MODE = {mode_json};
    var CONFIG = {config_json};
    var COLUMNS = {columns_json};

    var currentIndex = 0;
    var annotations = {{}};
    var confettiFired = false;

    var undoStack = [];

    var STORAGE_KEY = 'tagging_' + MODE + '_' + TEXTS.length + '_' + (TEXTS.length > 0 ? TEXTS[0].id : '');

    function saveState() {{
        try {{ localStorage.setItem(STORAGE_KEY, JSON.stringify(annotations)); }} catch(e) {{}}
    }}

    function pushUndo(id) {{
        var prev = annotations[id] === undefined ? undefined :
                   (Array.isArray(annotations[id]) ? annotations[id].slice() : annotations[id]);
        undoStack.push({{ id: id, value: prev }});
        if (undoStack.length > 50) undoStack.shift();
    }}

    function undo() {{
        if (undoStack.length === 0) return;
        var entry = undoStack.pop();
        if (entry.value === undefined) delete annotations[entry.id];
        else annotations[entry.id] = entry.value;
        // Navigate to the item that was undone
        for (var i = 0; i < TEXTS.length; i++) {{
            if (TEXTS[i].id === entry.id) {{ showText(i); break; }}
        }}
        updateUI();
        saveState();
    }}

    function loadState() {{
        try {{
            var saved = localStorage.getItem(STORAGE_KEY);
            if (saved) {{
                var parsed = JSON.parse(saved);
                if (parsed && typeof parsed === 'object') annotations = parsed;
            }}
        }} catch(e) {{}}
    }}

    function escapeHtml(s) {{
        var d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    }}

    // --- Init ---

    function init() {{
        loadState();
        document.getElementById('totalItems').textContent = TEXTS.length;

        document.getElementById(MODE + 'Panel').style.display = 'flex';

        if (MODE === 'binary') {{
            document.getElementById('annotationLabel').textContent = CONFIG.question || 'סיווג';
            renderBinaryOptions();
        }} else if (MODE === 'multiclass') {{
            document.getElementById('annotationLabel').textContent = 'בחר קטגוריות';
            renderCategories();
        }} else if (MODE === 'freetext') {{
            document.getElementById('annotationLabel').textContent = CONFIG.prompt || 'הקלד טקסט';
            document.getElementById('freetextInput').placeholder = CONFIG.placeholder || '';
            document.getElementById('freetextInput').addEventListener('input', function() {{
                var id = TEXTS[currentIndex].id;
                var val = this.value.trim();
                if (val) annotations[id] = val;
                else delete annotations[id];
                updateUI();
                saveState();
            }});
        }}

        renderShortcuts();
        showText(0);
    }}

    function renderBinaryOptions() {{
        var list = document.getElementById('binaryList');
        list.innerHTML = '';
        var options = [
            {{ value: 'yes', label: 'כן', key: 'Y' }},
            {{ value: 'no', label: 'לא', key: 'N' }}
        ];
        for (var i = 0; i < options.length; i++) {{
            var item = document.createElement('div');
            item.className = 'selection-item';
            item.dataset.value = options[i].value;
            item.innerHTML = '<span class="key-hint">' + options[i].key + '</span>' + escapeHtml(options[i].label);
            item.addEventListener('click', (function(val) {{
                return function() {{ onBinary(val); }};
            }})(options[i].value));
            list.appendChild(item);
        }}
    }}

    function renderCategories() {{
        var cats = CONFIG.categories || [];
        var grid = document.getElementById('categoriesGrid');
        grid.innerHTML = '';
        if (cats.length >= 7) grid.classList.add('compact');
        else grid.classList.remove('compact');
        for (var i = 0; i < cats.length; i++) {{
            var item = document.createElement('div');
            item.className = 'selection-item';
            item.dataset.id = cats[i].id;
            var keyNum = i < 9 ? String(i + 1) : '';
            var inner = '';
            if (keyNum) inner += '<span class="key-hint">' + keyNum + '.</span>';
            inner += escapeHtml(cats[i].label);
            item.innerHTML = inner;
            item.addEventListener('click', (function(catId) {{
                return function() {{ onCategory(catId); }};
            }})(cats[i].id));
            grid.appendChild(item);
        }}
    }}

    function renderShortcuts() {{
        var list = document.getElementById('shortcutsList');
        var shortcuts = [];
        if (MODE === 'binary') {{
            shortcuts.push(['Y', 'כן'], ['N', 'לא']);
        }} else if (MODE === 'multiclass') {{
            var cats = CONFIG.categories || [];
            var max = Math.min(cats.length, 9);
            for (var i = 0; i < max; i++) {{
                shortcuts.push([String(i + 1), cats[i].label]);
            }}
        }}
        shortcuts.push(
            ['&#8592; / &#8594;', 'הבא / הקודם'],
            ['Home', 'התחלה'],
            ['U', 'קפיצה ללא מתויג'],
            ['/ or F', 'חיפוש'],
            ['E', 'ייצוא CSV'],
            ['Ctrl+Z', 'ביטול'],
            ['Ctrl+H', 'חלון זה']
        );
        var html = '';
        for (var i = 0; i < shortcuts.length; i++) {{
            html += '<div class="shortcut-row"><span>' + shortcuts[i][1] + '</span><kbd>' + shortcuts[i][0] + '</kbd></div>';
        }}
        list.innerHTML = html;
    }}

    // --- Navigation ---

    function showText(idx) {{
        if (idx < 0 || idx >= TEXTS.length) return;

        // Save freetext before navigating
        if (MODE === 'freetext') {{
            var prevId = TEXTS[currentIndex].id;
            var val = document.getElementById('freetextInput').value.trim();
            if (val) annotations[prevId] = val;
            else delete annotations[prevId];
            saveState();
        }}

        currentIndex = idx;
        var item = TEXTS[idx];

        document.getElementById('textDisplay').textContent = item.text;
        document.getElementById('textIdBadge').textContent = (idx + 1) + ' / ' + TEXTS.length;

        var linkEl = document.getElementById('textLinkEl');
        if (item.link) {{
            linkEl.href = item.link;
            linkEl.style.display = '';
        }} else {{
            linkEl.style.display = 'none';
        }}

        restoreAnnotation(item.id);
        updateUI();
    }}

    function navigate(dir) {{
        var next = currentIndex + dir;
        if (next >= 0 && next < TEXTS.length) showText(next);
    }}

    function jumpToUntagged() {{
        // Always start from the first item
        for (var i = 0; i < TEXTS.length; i++) {{
            if (!isTagged(TEXTS[i].id)) {{
                showText(i);
                return;
            }}
        }}
    }}

    function isTagged(id) {{
        var v = annotations[id];
        if (v === undefined || v === null) return false;
        if (MODE === 'multiclass') return v.length > 0;
        if (MODE === 'freetext') return v !== '';
        return v !== '';
    }}

    // --- Annotation ---

    function restoreAnnotation(id) {{
        if (MODE === 'binary') {{
            var items = document.querySelectorAll('#binaryList .selection-item');
            for (var i = 0; i < items.length; i++) {{
                items[i].classList.remove('selected-yes', 'selected-no');
                if (annotations[id] === items[i].dataset.value) {{
                    items[i].classList.add(annotations[id] === 'yes' ? 'selected-yes' : 'selected-no');
                }}
            }}
        }} else if (MODE === 'multiclass') {{
            var selected = annotations[id] || [];
            var items = document.querySelectorAll('#categoriesGrid .selection-item');
            for (var i = 0; i < items.length; i++) {{
                items[i].classList.toggle('selected', selected.indexOf(items[i].dataset.id) >= 0);
            }}
        }} else if (MODE === 'freetext') {{
            document.getElementById('freetextInput').value = annotations[id] || '';
        }}
    }}

    function onBinary(value) {{
        var id = TEXTS[currentIndex].id;
        pushUndo(id);
        if (annotations[id] === value) {{
            delete annotations[id];
        }} else {{
            annotations[id] = value;
        }}
        restoreAnnotation(id);
        updateUI();
        saveState();
    }}

    function onCategory(catId) {{
        var id = TEXTS[currentIndex].id;
        pushUndo(id);
        if (!annotations[id]) annotations[id] = [];
        var idx = annotations[id].indexOf(catId);
        if (idx >= 0) annotations[id].splice(idx, 1);
        else annotations[id].push(catId);
        if (annotations[id].length === 0) delete annotations[id];
        restoreAnnotation(id);
        updateUI();
        saveState();
    }}

    // --- UI updates ---

    function updateUI() {{
        var tagged = 0;
        for (var i = 0; i < TEXTS.length; i++) {{
            if (isTagged(TEXTS[i].id)) tagged++;
        }}

        document.getElementById('taggedCount').textContent = tagged;
        var pct = TEXTS.length > 0 ? (tagged / TEXTS.length * 100) : 0;
        document.getElementById('progressFill').style.width = pct + '%';

        // Nav buttons
        document.getElementById('prevBtn').disabled = currentIndex === 0;
        document.getElementById('nextBtn').disabled = currentIndex === TEXTS.length - 1;

        // Tagged dot
        var dotEl = document.getElementById('taggedDot');
        dotEl.style.display = isTagged(TEXTS[currentIndex].id) ? '' : 'none';

        // Jump to untagged disabled if all tagged
        document.getElementById('jumpUntaggedBtn').disabled = tagged === TEXTS.length;

        // Distribution
        updateDistribution();

        // Reset confetti if items get untagged
        if (tagged < TEXTS.length) confettiFired = false;

        // Confetti on completion
        if (tagged === TEXTS.length && !confettiFired) {{
            confettiFired = true;
            fireConfetti();
        }}
    }}

    function updateDistribution() {{
        var html = '';

        if (MODE === 'binary') {{
            var yes = 0, no = 0, none = 0;
            for (var i = 0; i < TEXTS.length; i++) {{
                var v = annotations[TEXTS[i].id];
                if (v === 'yes') yes++;
                else if (v === 'no') no++;
                else none++;
            }}
            html += '<div class="dist-row"><span class="dist-label">כן</span><span class="dist-count">' + yes + '</span></div>';
            html += '<div class="dist-row"><span class="dist-label">לא</span><span class="dist-count">' + no + '</span></div>';
            html += '<div class="dist-row"><span class="dist-label" style="color:var(--g-400)">ללא תיוג</span><span class="dist-count">' + none + '</span></div>';
        }} else if (MODE === 'multiclass') {{
            var cats = CONFIG.categories || [];
            var untagged = 0;
            var counts = {{}};
            for (var i = 0; i < cats.length; i++) counts[cats[i].id] = 0;
            for (var i = 0; i < TEXTS.length; i++) {{
                var sel = annotations[TEXTS[i].id];
                if (!sel || sel.length === 0) {{ untagged++; continue; }}
                for (var j = 0; j < sel.length; j++) {{
                    if (counts[sel[j]] !== undefined) counts[sel[j]]++;
                }}
            }}
            for (var i = 0; i < cats.length; i++) {{
                html += '<div class="dist-row"><span class="dist-label">' + escapeHtml(cats[i].label) + '</span><span class="dist-count">' + counts[cats[i].id] + '</span></div>';
            }}
            html += '<div class="dist-row"><span class="dist-label" style="color:var(--g-400)">ללא תיוג</span><span class="dist-count">' + untagged + '</span></div>';
        }} else if (MODE === 'freetext') {{
            var filled = 0, empty = 0;
            for (var i = 0; i < TEXTS.length; i++) {{
                if (isTagged(TEXTS[i].id)) filled++;
                else empty++;
            }}
            html += '<div class="dist-row"><span class="dist-label">הוזן טקסט</span><span class="dist-count">' + filled + '</span></div>';
            html += '<div class="dist-row"><span class="dist-label" style="color:var(--g-400)">ריק</span><span class="dist-count">' + empty + '</span></div>';
        }}

        document.getElementById('distList').innerHTML = html;
    }}

    // --- Search ---

    var searchResults = [];
    var searchIdx = -1;

    document.getElementById('searchInput').addEventListener('input', function() {{
        var q = this.value.trim().toLowerCase();
        var nav = document.getElementById('searchNav');
        if (!q) {{
            searchResults = [];
            searchIdx = -1;
            nav.style.display = 'none';
            return;
        }}
        searchResults = [];
        for (var i = 0; i < TEXTS.length; i++) {{
            if (TEXTS[i].text.toLowerCase().indexOf(q) >= 0) searchResults.push(i);
        }}
        nav.style.display = '';
        if (searchResults.length > 0) {{
            searchIdx = 0;
            showText(searchResults[0]);
        }} else {{
            searchIdx = -1;
        }}
        updateSearchCount();
    }});

    function searchNext() {{
        if (searchResults.length === 0) return;
        searchIdx = (searchIdx + 1) % searchResults.length;
        showText(searchResults[searchIdx]);
        updateSearchCount();
    }}

    function searchPrev() {{
        if (searchResults.length === 0) return;
        searchIdx = (searchIdx - 1 + searchResults.length) % searchResults.length;
        showText(searchResults[searchIdx]);
        updateSearchCount();
    }}

    function updateSearchCount() {{
        var el = document.getElementById('searchCount');
        if (searchResults.length === 0) {{
            el.textContent = 'לא נמצא';
        }} else {{
            el.textContent = (searchIdx + 1) + ' / ' + searchResults.length;
        }}
    }}

    // --- Shortcuts modal ---

    function toggleShortcutsModal() {{
        var modal = document.getElementById('shortcutsModal');
        modal.classList.toggle('open');
    }}

    document.getElementById('shortcutsModal').addEventListener('click', function(e) {{
        if (e.target === this) toggleShortcutsModal();
    }});


    // --- Keyboard ---

    document.addEventListener('keydown', function(e) {{
        // Ctrl+Z undo
        if ((e.ctrlKey || e.metaKey) && (e.key === 'z' || e.key === 'Z')) {{
            e.preventDefault();
            undo();
            return;
        }}

        // Ctrl+H toggles shortcuts modal
        if ((e.ctrlKey || e.metaKey) && (e.key === 'h' || e.key === 'H')) {{
            e.preventDefault();
            toggleShortcutsModal();
            return;
        }}

        // Close modal on Escape
        if (e.key === 'Escape') {{
            var modal = document.getElementById('shortcutsModal');
            if (modal.classList.contains('open')) {{
                toggleShortcutsModal();
                e.preventDefault();
                return;
            }}
        }}

        // Don't hijack when typing in inputs
        if (document.activeElement.tagName === 'TEXTAREA' || document.activeElement.tagName === 'INPUT') {{
            if (e.key === 'Escape') {{
                e.preventDefault();
                document.activeElement.blur();
                return;
            }}
            // Enter in search navigates to next result
            if (document.activeElement.id === 'searchInput' && e.key === 'Enter') {{
                e.preventDefault();
                if (e.shiftKey) searchPrev();
                else searchNext();
            }}
            return;
        }}

        var key = e.key;

        if (key === 'ArrowLeft') {{
            e.preventDefault();
            navigate(1);
        }} else if (key === 'ArrowRight') {{
            e.preventDefault();
            navigate(-1);
        }} else if (key === 'Home') {{
            e.preventDefault();
            showText(0);
        }} else if (key === 'u' || key === 'U') {{
            e.preventDefault();
            jumpToUntagged();
        }} else if (key === 'e' || key === 'E') {{
            e.preventDefault();
            exportCSV();
        }} else if (key === '/' || key === 'f' || key === 'F') {{
            e.preventDefault();
            document.getElementById('searchInput').focus();
        }} else if (MODE === 'binary') {{
            if (key === 'y' || key === 'Y') {{ e.preventDefault(); onBinary('yes'); }}
            else if (key === 'n' || key === 'N') {{ e.preventDefault(); onBinary('no'); }}
        }} else if (MODE === 'multiclass') {{
            var num = parseInt(key);
            if (num >= 1 && num <= 9) {{
                var cats = CONFIG.categories || [];
                if (num <= cats.length) {{
                    e.preventDefault();
                    onCategory(cats[num - 1].id);
                }}
            }}
        }}
    }});

    // --- Export ---

    function exportCSV() {{
        if (MODE === 'freetext') {{
            var curId = TEXTS[currentIndex].id;
            var val = document.getElementById('freetextInput').value.trim();
            if (val) annotations[curId] = val;
            else delete annotations[curId];
        }}

        // Warn if untagged items remain
        var untaggedCount = 0;
        for (var i = 0; i < TEXTS.length; i++) {{
            if (!isTagged(TEXTS[i].id)) untaggedCount++;
        }}
        if (untaggedCount > 0) {{
            if (!confirm('נותרו ' + untaggedCount + ' טקסטים ללא תיוג. להמשיך בייצוא?')) return;
        }}

        var annotCol = MODE === 'binary' ? 'binary_label' :
                       MODE === 'multiclass' ? 'selected_categories' : 'extracted_text';

        var allCols = COLUMNS.concat([annotCol]);

        var csv = '\\ufeff';
        csv += allCols.map(function(c) {{ return '"' + c.replace(/"/g, '""') + '"'; }}).join(',') + '\\n';

        for (var i = 0; i < TEXTS.length; i++) {{
            var item = TEXTS[i];
            var row = [];
            for (var j = 0; j < COLUMNS.length; j++) {{
                var v = item[COLUMNS[j]];
                v = v !== undefined && v !== null ? String(v) : '';
                row.push('"' + v.replace(/"/g, '""') + '"');
            }}
            var ann = annotations[item.id];
            var annStr = '';
            if (MODE === 'binary') {{
                annStr = ann || '';
            }} else if (MODE === 'multiclass') {{
                if (ann && ann.length > 0) {{
                    var cats = CONFIG.categories || [];
                    var labels = [];
                    for (var k = 0; k < ann.length; k++) {{
                        for (var c = 0; c < cats.length; c++) {{
                            if (cats[c].id === ann[k]) {{ labels.push(cats[c].label); break; }}
                        }}
                    }}
                    annStr = labels.join('; ');
                }}
            }} else {{
                annStr = ann || '';
            }}
            row.push('"' + annStr.replace(/"/g, '""') + '"');
            csv += row.join(',') + '\\n';
        }}

        var blob = new Blob([csv], {{ type: 'text/csv;charset=utf-8' }});
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = 'tagging_' + MODE + '_' + new Date().toISOString().slice(0, 10) + '.csv';
        a.click();
        URL.revokeObjectURL(url);

        fireConfetti();
    }}

    // --- Confetti ---

    function fireConfetti() {{
        var container = document.createElement('div');
        container.className = 'confetti-container';
        document.body.appendChild(container);
        var colors = ['#7C9A82', '#5E7E64', '#9AB4A0', '#4CAF50', '#d0d0d0'];
        var shapes = ['circle', 'square', 'rect'];
        for (var i = 0; i < 50; i++) {{
            var el = document.createElement('div');
            el.className = 'confetti ' + shapes[Math.floor(Math.random() * shapes.length)];
            el.style.backgroundColor = colors[Math.floor(Math.random() * colors.length)];
            el.style.left = Math.random() * 100 + '%';
            el.style.animationDelay = Math.random() * 0.5 + 's';
            el.style.animationDuration = (2 + Math.random() * 2) + 's';
            var size = 6 + Math.random() * 10;
            if (!el.classList.contains('rect')) {{
                el.style.width = size + 'px';
                el.style.height = size + 'px';
            }}
            container.appendChild(el);
        }}
        setTimeout(function() {{
            if (container.parentNode) container.parentNode.removeChild(container);
        }}, 4000);
    }}

    init();
</script>
</body>
</html>'''

    return html


def save_and_open(html: str, output_path: str = "tagging.html") -> str:
    """Save HTML to file and open in the default browser.

    Args:
        html: Complete HTML string from render_tagging_html().
        output_path: File path to write. Defaults to 'tagging.html'.

    Returns:
        Absolute path to the saved file.
    """
    abs_path = os.path.abspath(output_path)
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(html)
    webbrowser.open(f"file://{abs_path}")
    return abs_path


if __name__ == "__main__":
    data = [
        {"id": 1, "text": "היי, איך אתה מרגיש היום?", "link": "https://example.com/1"},
        {"id": 2, "text": "אני אוהב אותך כל כך", "link": "https://example.com/2"},
        {"id": 3, "text": "בוא נדבר על הפרויקט החדש", "link": "https://example.com/3"},
        {"id": 4, "text": "תודה על העזרה במשימה", "link": "https://example.com/4"},
        {"id": 5, "text": "אימא, מתי תגיעי לבקר?", "link": "https://example.com/5"},
    ]
    df = pd.DataFrame(data)

    html = render_tagging_html(df, AnnotationMode.BINARY, {"question": "האם הטקסט חיובי?"})
    save_and_open(html, "/tmp/tagging_binary.html")
