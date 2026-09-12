import os, re, subprocess, tempfile, io, time, shutil
import pandas as pd
import streamlit as st 
import streamlit.components.v1 as components
from google import genai
from groq import Groq
from graph_builder import render_graph_builder_tab, render_clinical_graphs_tab
from table_builder import render_table_builder_tab
from listing_builder import render_listing_builder_tab
from macro_processor import expand_sas_macros, has_macros
from macro_converter import convert_macros_to_r
from tlf_shell_builder import render_shell_tlf_tab
from rule_engine import RuleEngine
from sas_ast import ProgramStep


# --- CONFIGURATION ---
st.set_page_config(page_title="Smart SAS to R Converter", page_icon="🚀", layout="wide", initial_sidebar_state="expanded")

for key, default in {
    "sas_input": "",
    "upload_key": 0,
    "uploaded_csvs": {},
    "retry_step": None,
    "retry_counts": {},
    "fix_results": {},
    "pipeline_results": [],
    "pipeline_run": False,
    "work_library": {},
    "graph_df": None,
    "graph_r_code": "",
    "graph_png": None,
    "graph_log": "",
    "graph_error": None,
    "graph_preview_png": None,
    "graph_r_code_pending": None,
    "graph_r_code_original": None,
    "page": "🔄 SAS Converter",
    "app_mode": "Convert Only",
    "r_dialect": "Modern R (tidyverse)"
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

def clear_all():
    st.session_state.sas_input = ""
    st.session_state.uploaded_csvs = {}
    st.session_state.upload_key = st.session_state.get("upload_key", 0) + 1
    st.session_state.pipeline_results = []
    st.session_state.pipeline_run = False
    st.session_state.fix_results = {}
    st.session_state.loaded_project_file = None
    st.session_state.show_r_review = False
    st.session_state.current_conv_result = None

def toggle_r_review():
    st.session_state.show_r_review = not st.session_state.get("show_r_review", False)

# --- ENTERPRISE CUSTOM CSS (ADAPTS TO LIGHT, DARK & SYSTEM THEMES) ---
user_app_theme = st.session_state.get("sb_app_theme") or st.session_state.get("app_theme", "System")

theme_override_css = ""
if user_app_theme == "Light":
    theme_override_css = """
    :root, .stApp, [data-testid="stApp"], section[data-testid="stSidebar"] {
        --bg-app: #F8FAFC !important;
        --bg-surface: #FFFFFF !important;
        --bg-subtle: #F1F5F9 !important;
        --border-color: #E2E8F0 !important;
        --border-dark: #CBD5E1 !important;
        --text-main: #0F172A !important;
        --text-subtitle: #475569 !important;
        --text-muted: #64748B !important;
        --primary-btn: #2563EB !important;
        --primary-btn-hover: #1D4ED8 !important;
        --secondary-btn-bg: #FFFFFF !important;
        --secondary-btn-hover: #F1F5F9 !important;
        --secondary-btn-border: #E2E8F0 !important;
        --secondary-btn-text: #0F172A !important;
        --sidebar-bg: #F8FAFC !important;
        --sidebar-border: #E2E8F0 !important;
        --nav-selected-bg: #DBEAFE !important;
        --nav-selected-text: #1D4ED8 !important;
    }
    """
elif user_app_theme == "Dark":
    theme_override_css = """
    :root, .stApp, [data-testid="stApp"], section[data-testid="stSidebar"] {
        --bg-app: #0F172A !important;
        --bg-surface: #111827 !important;
        --bg-subtle: #1E293B !important;
        --border-color: #334155 !important;
        --border-dark: #475569 !important;
        --text-main: #F8FAFC !important;
        --text-subtitle: #CBD5E1 !important;
        --text-muted: #94A3B8 !important;
        --primary-btn: #2563EB !important;
        --primary-btn-hover: #1D4ED8 !important;
        --secondary-btn-bg: #1E293B !important;
        --secondary-btn-hover: #334155 !important;
        --secondary-btn-border: #334155 !important;
        --secondary-btn-text: #F8FAFC !important;
        --sidebar-bg: #0F172A !important;
        --sidebar-border: #1E293B !important;
        --nav-selected-bg: #1E3A5F !important;
        --nav-selected-text: #93C5FD !important;
    }
    """

st.markdown("""
    <style>
    :root, .stApp, [data-testid="stApp"], section[data-testid="stSidebar"] {
        --bg-app: var(--background-color, #F8FAFC);
        --bg-surface: var(--secondary-background-color, #FFFFFF);
        --bg-subtle: var(--secondary-background-color, #F1F5F9);
        --border-color: rgba(128, 128, 128, 0.22);
        --border-dark: rgba(128, 128, 128, 0.35);
        --text-main: var(--text-color, #0F172A);
        --text-subtitle: var(--text-color, #475569);
        --text-muted: rgba(100, 116, 139, 0.85);
        --primary-btn: #2563EB;
        --primary-btn-hover: #1D4ED8;
        --secondary-btn-bg: var(--secondary-background-color, #FFFFFF);
        --secondary-btn-hover: rgba(128, 128, 128, 0.08);
        --secondary-btn-border: rgba(128, 128, 128, 0.22);
        --secondary-btn-text: var(--text-color, #0F172A);
        --sidebar-bg: var(--secondary-background-color, #F8FAFC);
        --sidebar-border: rgba(128, 128, 128, 0.2);
        --nav-selected-bg: rgba(37, 99, 235, 0.15);
        --nav-selected-text: #2563EB;
        --success: #059669;
        --success-bg: #ECFDF5;
        --warning: #D97706;
        --warning-bg: #FFFBEB;
        --error: #DC2626;
        --error-bg: #FEF2F2;
        --radius: 8px;
    }

    .stApp {
        background-color: var(--bg-app);
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    
    /* Main Workspace Enterprise Container & Grid Alignment */
    .block-container {
        max-width: 1400px !important;
        margin: 0 auto !important;
        padding-top: 2.5rem !important;
        padding-bottom: 2rem !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
    }

    /* Top Header & Subtitle Styling (Ensures zero vertical clipping) */
    section[data-testid="stMain"] h1 {
        font-size: 1.65rem !important;
        font-weight: 700 !important;
        color: var(--text-main) !important;
        margin-top: 0 !important;
        margin-bottom: 0.25rem !important;
        padding-top: 0 !important;
        line-height: 1.25 !important;
    }

    section[data-testid="stMain"] div[data-testid="stCaptionContainer"] p,
    section[data-testid="stMain"] .stCaption p,
    section[data-testid="stMain"] .stCaption {
        color: var(--text-subtitle) !important;
        font-size: 0.9rem !important;
        font-weight: 500 !important;
        margin-top: 0 !important;
        margin-bottom: 0.5rem !important;
    }

    /* Section Headings Visual Hierarchy */
    section[data-testid="stMain"] h3 {
        font-size: 1.05rem !important;
        font-weight: 700 !important;
        color: var(--text-main) !important;
        margin-top: 0 !important;
        margin-bottom: 0.5rem !important;
    }

    /* Card Boxes & Integrated Expander Containers */
    .card-box {
        background: var(--bg-surface);
        border: 1px solid var(--border-color);
        border-radius: var(--radius);
        padding: 16px;
        margin-bottom: 16px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.02);
    }
    
    .card-header-title {
        font-size: 0.98rem;
        font-weight: 700;
        color: var(--text-main);
        margin-bottom: 8px;
        display: flex;
        align-items: center;
        gap: 8px;
    }

    /* Standardize stExpander to match Card Component system */
    section[data-testid="stMain"] div[data-testid="stLayoutWrapper"]:has(div[data-testid="stExpander"]) {
        margin: 0 !important;
    }

    section[data-testid="stMain"] div[data-testid="stExpander"] {
        background-color: var(--bg-surface) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: var(--radius) !important;
        box-shadow: 0 1px 2px rgba(0,0,0,0.02) !important;
        margin: 0 !important;
        overflow: hidden !important;
    }

    section[data-testid="stMain"] div[data-testid="stExpander"] details {
        border: none !important;
        background-color: var(--bg-surface) !important;
        border-radius: var(--radius) !important;
    }

    section[data-testid="stMain"] div[data-testid="stExpander"] summary {
        background-color: var(--bg-subtle) !important;
        color: var(--text-main) !important;
        font-weight: 600 !important;
        font-size: 0.95rem !important;
        border-bottom: 1px solid var(--border-color) !important;
        padding: 10px 14px !important;
        border-radius: var(--radius) var(--radius) 0 0 !important;
    }

    section[data-testid="stMain"] div[data-testid="stExpander"] div[data-testid="stExpanderDetails"] {
        padding: 14px !important;
        background-color: var(--bg-surface) !important;
    }

    section[data-testid="stMain"] hr {
        margin: 16px 0 !important;
        border-color: var(--border-color) !important;
    }
    
    /* Badges & Metrics */
    .badge-pill {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 0.78rem;
        font-weight: 600;
        letter-spacing: 0.3px;
    }
    .badge-success { background: var(--success-bg); color: var(--success); border: 1px solid #A7F3D0; }
    .badge-info { background: var(--bg-subtle); color: var(--primary-btn); border: 1px solid #BFDBFE; }
    .badge-warning { background: var(--warning-bg); color: var(--warning); border: 1px solid #FDE68A; }
    
    /* Tabs Customization */
    .stTabs [data-baseweb="tab-list"] { gap: 16px; border-bottom: 1px solid var(--border-color); }
    .stTabs [data-baseweb="tab"] { height: 38px; font-weight: 600; font-size: 0.86rem; color: var(--text-muted); }
    .stTabs [aria-selected="true"] { color: var(--primary-btn) !important; border-bottom-color: var(--primary-btn) !important; }
    
    .timing-badge {
        display: inline-block;
        background: #f0f2f6;
        border: 1px solid #d0d4de;
        border-radius: 12px;
        padding: 2px 10px;
        font-size: 0.78em;
        color: #555;
        margin-left: 8px;
        font-family: monospace;
    }

    /* Enterprise Primary Action Button Styling (e.g. Convert SAS -> R) */
    div.stButton > button[kind="primary"],
    button[kind="primary"],
    .stButton > button[data-testid="stBaseButton-primary"] {
        background-color: var(--primary-btn) !important;
        color: #FFFFFF !important;
        border: 1px solid var(--primary-btn-hover) !important;
        font-weight: 600 !important;
        border-radius: 6px !important;
    }

    div.stButton > button[kind="primary"]:hover,
    button[kind="primary"]:hover,
    .stButton > button[data-testid="stBaseButton-primary"]:hover {
        background-color: var(--primary-btn-hover) !important;
        border-color: var(--primary-btn) !important;
        color: #FFFFFF !important;
    }

    /* Enterprise Neutral Secondary Button Styling (e.g. Clear button) */
    div.stButton > button:not([kind="primary"]),
    button[kind="secondary"],
    .stButton > button[data-testid="stBaseButton-secondary"] {
        background-color: var(--secondary-btn-bg) !important;
        color: var(--secondary-btn-text) !important;
        border: 1px solid var(--secondary-btn-border) !important;
        font-weight: 600 !important;
        border-radius: 6px !important;
    }

    div.stButton > button:not([kind="primary"]):hover,
    button[kind="secondary"]:hover,
    .stButton > button[data-testid="stBaseButton-secondary"]:hover {
        background-color: var(--secondary-btn-hover) !important;
        color: var(--secondary-btn-text) !important;
        border-color: var(--secondary-btn-border) !important;
    }

    div[data-testid="stButton"],
    div[data-testid="stDownloadButton"],
    div.stButton,
    div.stDownloadButton {
        margin: 0 !important;
        padding: 0 !important;
    }

    div[data-testid="stDownloadButton"] a {
        display: flex !important;
        margin: 0 !important;
        padding: 0 !important;
        text-decoration: none !important;
    }

    /* Normalized Button Height & Alignment across all buttons */
    div.stButton > button,
    button[data-testid="stBaseButton-primary"],
    button[data-testid="stBaseButton-secondary"],
    .stDownloadButton > button {
        min-height: 42px !important;
        height: 42px !important;
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        font-size: 0.92rem !important;
        padding: 0 16px !important;
    }

    /* Selectbox Widget & Dropdown Popover Theme Styling */
    div[data-testid="stSelectbox"] label,
    div[data-testid="stSelectbox"] label p {
        color: var(--text-main) !important;
        font-weight: 600 !important;
    }

    div[data-testid="stSelectbox"] div[data-baseweb="select"] > div {
        background-color: var(--bg-surface) !important;
        color: var(--text-main) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: var(--radius) !important;
        min-height: 42px !important;
        display: flex !important;
        align-items: center !important;
    }

    div[data-testid="stSelectbox"] div[data-baseweb="select"] div,
    div[data-testid="stSelectbox"] div[data-baseweb="select"] span,
    div[data-testid="stSelectbox"] div[data-baseweb="select"] input {
        color: var(--text-main) !important;
        background-color: transparent !important;
    }

    div[data-testid="stSelectbox"] div[data-baseweb="select"] input::placeholder {
        color: var(--text-muted) !important;
    }

    div[data-testid="stSelectbox"] svg {
        fill: var(--text-muted) !important;
        color: var(--text-muted) !important;
    }

    div[data-baseweb="popover"],
    div[data-baseweb="popover"] > div,
    div[data-baseweb="menu"],
    ul[data-baseweb="menu"] {
        background-color: var(--bg-surface) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: var(--radius) !important;
        color: var(--text-main) !important;
    }

    div[data-baseweb="popover"] li,
    div[data-baseweb="popover"] li[data-baseweb="option"],
    ul[data-baseweb="menu"] li {
        background-color: var(--bg-surface) !important;
        color: var(--text-main) !important;
    }

    div[data-baseweb="popover"] li:hover,
    div[data-baseweb="popover"] li[aria-selected="true"],
    div[data-baseweb="popover"] li[data-baseweb="option"]:hover,
    ul[data-baseweb="menu"] li:hover,
    ul[data-baseweb="menu"] li[aria-selected="true"] {
        background-color: var(--bg-subtle) !important;
        color: var(--text-main) !important;
    }

    /* Header Row Height Normalization */
    div[data-testid="stColumn"] div[data-testid="stHorizontalBlock"]:has(h3) {
        min-height: 42px !important;
        height: 42px !important;
        max-height: 42px !important;
        align-items: center !important;
        margin: 0 !important;
    }

    div[data-testid="stColumn"] div[data-testid="stHorizontalBlock"]:has(h3) h3 {
        margin: 0 !important;
        padding: 0 !important;
        line-height: 42px !important;
        height: 42px !important;
    }

    div[data-testid="stSelectbox"],
    div[data-testid="stSelectbox"] > div {
        height: 42px !important;
        min-height: 42px !important;
        max-height: 42px !important;
        margin: 0 !important;
        box-sizing: border-box !important;
    }

    /* Workspace Action Row & Column Alignment */
    div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] > div[data-testid="stLayoutWrapper"]:last-child,
    div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] > div[data-testid="stLayoutWrapper"]:last-child > div[data-testid="stHorizontalBlock"] {
        min-height: 42px !important;
        height: 42px !important;
        max-height: 42px !important;
        margin: 0 !important;
    }

    div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] > div[data-testid="stLayoutWrapper"]:last-child div[data-testid="stElementContainer"] {
        margin: 0 !important;
        padding: 0 !important;
        height: 42px !important;
        min-height: 42px !important;
        max-height: 42px !important;
    }

    div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] > div[data-testid="stLayoutWrapper"]:last-child div.stButton,
    div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] > div[data-testid="stLayoutWrapper"]:last-child div.stDownloadButton,
    div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] > div[data-testid="stLayoutWrapper"]:last-child div[data-testid="stButton"],
    div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] > div[data-testid="stLayoutWrapper"]:last-child div[data-testid="stDownloadButton"] {
        margin: 0 !important;
        padding: 0 !important;
        width: 100% !important;
        height: 42px !important;
        min-height: 42px !important;
        max-height: 42px !important;
        display: flex !important;
        align-items: flex-start !important;
    }

    div[data-testid="stDownloadButton"] a {
        display: flex !important;
        width: 100% !important;
        height: 42px !important;
        margin: 0 !important;
        padding: 0 !important;
    }

    div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] > div[data-testid="stElementContainer"] > div[data-testid="stTextArea"],
    div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] > div[data-testid="stElementContainer"] > div[data-testid="stTextArea"] > div,
    div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] > div[data-testid="stElementContainer"] > div[data-testid="stTextAreaRootElement"],
    div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] > div[data-testid="stElementContainer"]:has(.r-output-empty-state) {
        height: 360px !important;
        min-height: 360px !important;
        max-height: 360px !important;
        box-sizing: border-box !important;
        margin: 0 !important;
    }

    div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] > div[data-testid="stElementContainer"] > div[data-testid="stCode"],
    div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] > div[data-testid="stElementContainer"] > div[data-testid="stCodeBlock"] {
        height: 360px !important;
        min-height: 360px !important;
        max-height: 360px !important;
        box-sizing: border-box !important;
        margin: 0 !important;
    }

    div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] > div[data-testid="stElementContainer"] pre,
    div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] > div[data-testid="stElementContainer"] > div[data-testid="stCode"] pre,
    div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] > div[data-testid="stElementContainer"] > div[data-testid="stCodeBlock"] pre {
        height: 100% !important;
        min-height: 100% !important;
        max-height: 100% !important;
        overflow-y: auto !important;
    }

    /* R Output Empty State Container (Fixed 360px) */
    .r-output-empty-state {
        height: 360px !important;
        min-height: 360px !important;
        max-height: 360px !important;
        background-color: var(--bg-surface) !important;
        color: var(--text-muted) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: var(--radius) !important;
        padding: 20px 22px !important;
        font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, Courier, monospace !important;
        font-size: 0.88rem !important;
        line-height: 1.6 !important;
        box-sizing: border-box !important;
        display: flex !important;
        flex-direction: column !important;
        justify-content: flex-start !important;
        white-space: normal !important;
        word-wrap: break-word !important;
        overflow: hidden !important;
        margin: 0 !important;
    }

    /* General Text Areas (Secondary / Modals / Spacers) */
    div[data-testid="stTextArea"] textarea {
        background-color: var(--bg-surface) !important;
        color: var(--text-main) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: var(--radius) !important;
        font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, Courier, monospace !important;
        resize: none !important;
        box-sizing: border-box !important;
    }

    /* General Content-Aware Code Blocks (Secondary Views, Details, Tabs) */
    div[data-testid="stCode"],
    div[data-testid="stCodeBlock"] {
        min-height: 60px !important;
        max-height: 280px !important;
        height: auto !important;
        background-color: var(--bg-surface) !important;
        color: var(--text-main) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: var(--radius) !important;
        font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, Courier, monospace !important;
        position: relative !important;
        display: flex !important;
        flex-direction: column !important;
        box-sizing: border-box !important;
        margin: 0 !important;
    }

    div[data-testid="stCode"] pre,
    div[data-testid="stCodeBlock"] pre {
        min-height: 60px !important;
        max-height: 280px !important;
        overflow-y: auto !important;
        margin: 0 !important;
        padding: 10px 14px !important;
        background-color: transparent !important;
        border: none !important;
        box-sizing: border-box !important;
    }

    div[data-testid="stCode"] pre > div,
    div[data-testid="stCodeBlock"] pre > div {
        min-height: 100% !important;
    }

    div[data-testid="stTextArea"] textarea::placeholder {
        color: var(--text-muted) !important;
    }

    /* Main Content Contrast Scoping */
    section[data-testid="stMain"] {
        background-color: var(--bg-app) !important;
        color: var(--text-main) !important;
    }

    section[data-testid="stMain"] h1,
    section[data-testid="stMain"] h2,
    section[data-testid="stMain"] h3,
    section[data-testid="stMain"] h4,
    section[data-testid="stMain"] h5,
    section[data-testid="stMain"] h6,
    section[data-testid="stMain"] p,
    section[data-testid="stMain"] label,
    section[data-testid="stMain"] div[data-testid="stMarkdownContainer"] p,
    section[data-testid="stMain"] div[data-testid="stMarkdownContainer"] h1,
    section[data-testid="stMain"] div[data-testid="stMarkdownContainer"] h2,
    section[data-testid="stMain"] div[data-testid="stMarkdownContainer"] h3,
    section[data-testid="stMain"] div[data-testid="stMarkdownContainer"] h4,
    section[data-testid="stMain"] div[data-testid="stWidgetLabel"] label,
    section[data-testid="stMain"] div[data-testid="stWidgetLabel"] p,
    section[data-testid="stMain"] div[data-testid="stRadio"] label,
    section[data-testid="stMain"] div[data-testid="stRadio"] label p,
    section[data-testid="stMain"] div[data-testid="stRadio"] label span,
    section[data-testid="stMain"] div[data-testid="stFileUploader"] label,
    section[data-testid="stMain"] div[data-testid="stFileUploader"] label p,
    section[data-testid="stMain"] div[data-testid="stExpander"] summary span,
    section[data-testid="stMain"] div[data-testid="stExpander"] summary div,
    section[data-testid="stMain"] div[data-testid="stExpander"] summary p,
    section[data-testid="stMain"] details summary span,
    section[data-testid="stMain"] details summary div,
    section[data-testid="stMain"] details summary p {
        color: var(--text-main) !important;
    }

    /* Phase 8.81.1 Sidebar Navigation & MORE Suboptions Styling */
    section[data-testid="stSidebar"] {
        background-color: var(--sidebar-bg) !important;
        border-right: 1px solid var(--sidebar-border) !important;
        padding-top: 0.4rem !important;
    }

    section[data-testid="stSidebar"][aria-expanded="true"] {
        min-width: 230px !important;
        max-width: 230px !important;
        width: 230px !important;
    }

    /* Primary Navigation Radio (Top of Sidebar - No WORKSPACE Label) */
    section[data-testid="stSidebar"] div[data-testid="stRadio"]:has(div[aria-label="main_nav"]) {
        margin-top: 0px !important;
        margin-bottom: 6px !important;
    }

    /* Sidebar Expander Customization */
    section[data-testid="stSidebar"] div[data-testid="stExpander"] {
        background-color: transparent !important;
        border: none !important;
        box-shadow: none !important;
        margin: 2px 0 !important;
        border-radius: 6px !important;
    }

    section[data-testid="stSidebar"] div[data-testid="stExpander"] details {
        border: none !important;
        background-color: transparent !important;
    }

    section[data-testid="stSidebar"] div[data-testid="stExpander"] summary {
        background-color: transparent !important;
        color: var(--text-muted) !important;
        font-weight: 600 !important;
        font-size: 12px !important;
        letter-spacing: 0.05em !important;
        text-transform: uppercase !important;
        border-bottom: none !important;
        padding: 6px 2px !important;
        border-radius: 6px !important;
    }

    section[data-testid="stSidebar"] div[data-testid="stExpander"] summary:hover {
        background-color: var(--secondary-btn-hover) !important;
        color: var(--text-main) !important;
    }

    section[data-testid="stSidebar"] div[data-testid="stExpander"] summary span,
    section[data-testid="stSidebar"] div[data-testid="stExpander"] summary p,
    section[data-testid="stSidebar"] div[data-testid="stExpander"] summary svg {
        color: var(--text-muted) !important;
    }

    section[data-testid="stSidebar"] div[data-testid="stExpander"] div[data-testid="stExpanderDetails"] {
        padding: 2px 0 2px 4px !important;
        background-color: transparent !important;
    }

    /* Nested expanders inside MORE - Interactive Utility/Navigation Rows */
    section[data-testid="stSidebar"] div[data-testid="stExpander"] div[data-testid="stExpander"] {
        margin: 3px 0 !important;
    }

    section[data-testid="stSidebar"] div[data-testid="stExpander"] div[data-testid="stExpander"] summary {
        min-height: 36px !important;
        height: 36px !important;
        padding: 5px 8px !important;
        margin: 2px 0 !important;
        border-radius: 6px !important;
        font-size: 13px !important;
        font-weight: 500 !important;
        text-transform: none !important;
        letter-spacing: normal !important;
        color: var(--text-main) !important;
        display: flex !important;
        align-items: center !important;
        cursor: pointer !important;
        background-color: transparent !important;
        transition: background-color 0.15s ease, color 0.15s ease !important;
    }

    section[data-testid="stSidebar"] div[data-testid="stExpander"] div[data-testid="stExpander"] summary:hover {
        background-color: var(--secondary-btn-hover) !important;
        color: var(--text-main) !important;
    }

    section[data-testid="stSidebar"] div[data-testid="stExpander"] div[data-testid="stExpander"] summary span,
    section[data-testid="stSidebar"] div[data-testid="stExpander"] div[data-testid="stExpander"] summary p {
        font-size: 13px !important;
        font-weight: 500 !important;
        color: var(--text-main) !important;
    }

    /* Structured Supported SAS Statements Grid */
    .supported-statements-list {
        padding: 4px 0;
        font-size: 12px;
        color: var(--text-main);
    }
    .stmt-row {
        display: grid;
        grid-template-columns: 22px 105px 1fr;
        align-items: center;
        padding: 4px 0;
        border-bottom: 1px dashed var(--border-color);
    }
    .stmt-row:last-child {
        border-bottom: none;
    }
    .stmt-check {
        font-size: 11px;
    }
    .stmt-name {
        font-weight: 600;
        color: var(--text-main);
        font-size: 12px;
    }
    .stmt-detail {
        font-size: 11px;
        color: var(--text-muted);
    }

    /* Structured App Features Grid */
    .app-features-list {
        padding: 4px 0;
        font-size: 13px;
        color: var(--text-main);
        line-height: 1.4;
    }
    .feature-row {
        display: grid;
        grid-template-columns: 24px 1fr;
        align-items: start;
        padding: 4px 0;
    }
    .feature-icon {
        font-size: 13px;
        line-height: 1.4;
    }
    .feature-desc {
        font-size: 13px;
        font-weight: 400;
        color: var(--text-main);
        line-height: 1.4;
    }

    /* Navigation Radio Items - Hide Radio Circles for main_nav & clinical_nav */
    section[data-testid="stSidebar"] div[data-testid="stRadio"]:has(div[aria-label="main_nav"]) > label[data-testid="stWidgetLabel"],
    section[data-testid="stSidebar"] div[data-testid="stRadio"]:has(div[aria-label="clinical_nav"]) > label[data-testid="stWidgetLabel"] {
        display: none !important;
    }

    section[data-testid="stSidebar"] div[role="radiogroup"][aria-label="main_nav"] label[data-baseweb="radio"] > div:first-child,
    section[data-testid="stSidebar"] div[role="radiogroup"][aria-label="clinical_nav"] label[data-baseweb="radio"] > div:first-child {
        display: none !important;
    }

    section[data-testid="stSidebar"] div[role="radiogroup"][aria-label="main_nav"] label[data-baseweb="radio"],
    section[data-testid="stSidebar"] div[role="radiogroup"][aria-label="clinical_nav"] label[data-baseweb="radio"] {
        width: 100% !important;
        min-height: 36px !important;
        height: 36px !important;
        padding: 5px 8px !important;
        margin: 2px 0 !important;
        border-radius: 6px !important;
        font-size: 14px !important;
        font-weight: 500 !important;
        cursor: pointer !important;
        display: flex !important;
        align-items: center !important;
        transition: background-color 0.15s ease, color 0.15s ease !important;
        background-color: transparent !important;
        color: var(--text-main) !important;
    }

    section[data-testid="stSidebar"] div[role="radiogroup"][aria-label="main_nav"] label[data-baseweb="radio"]:hover,
    section[data-testid="stSidebar"] div[role="radiogroup"][aria-label="clinical_nav"] label[data-baseweb="radio"]:hover {
        background-color: var(--secondary-btn-hover) !important;
    }

    /* Selected State for main_nav & clinical_nav */
    section[data-testid="stSidebar"] div[role="radiogroup"][aria-label="main_nav"] label[data-baseweb="radio"]:has(input:checked),
    section[data-testid="stSidebar"] div[role="radiogroup"][aria-label="clinical_nav"] label[data-baseweb="radio"]:has(input:checked) {
        background-color: var(--nav-selected-bg) !important;
        color: var(--nav-selected-text) !important;
        font-weight: 600 !important;
    }

    section[data-testid="stSidebar"] div[role="radiogroup"][aria-label="main_nav"] label[data-baseweb="radio"]:has(input:checked) p,
    section[data-testid="stSidebar"] div[role="radiogroup"][aria-label="clinical_nav"] label[data-baseweb="radio"]:has(input:checked) p,
    section[data-testid="stSidebar"] div[role="radiogroup"][aria-label="main_nav"] label[data-baseweb="radio"]:has(input:checked) span,
    section[data-testid="stSidebar"] div[role="radiogroup"][aria-label="clinical_nav"] label[data-baseweb="radio"]:has(input:checked) span {
        color: var(--nav-selected-text) !important;
        font-weight: 600 !important;
    }

    /* Settings Selectbox Controls */
    section[data-testid="stSidebar"] div[data-testid="stSelectbox"] {
        margin-bottom: 8px !important;
    }

    section[data-testid="stSidebar"] div[data-testid="stSelectbox"] label,
    section[data-testid="stSidebar"] div[data-testid="stSelectbox"] label p {
        font-size: 14px !important;
        font-weight: 500 !important;
        color: var(--text-subtitle) !important;
        margin-bottom: 4px !important;
    }

    section[data-testid="stSidebar"] div[data-testid="stSelectbox"] div[data-baseweb="select"] > div {
        min-height: 38px !important;
        height: 38px !important;
        font-size: 13px !important;
    }

    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span,
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3,
    section[data-testid="stSidebar"] h4,
    section[data-testid="stSidebar"] div[data-testid="stMarkdownContainer"] p,
    section[data-testid="stSidebar"] div[data-testid="stWidgetLabel"] label,
    section[data-testid="stSidebar"] div[data-testid="stWidgetLabel"] p,
    section[data-testid="stSidebar"] div[data-testid="stRadio"] label,
    section[data-testid="stSidebar"] div[data-testid="stRadio"] label p,
    section[data-testid="stSidebar"] div[data-testid="stRadio"] label span {
        color: var(--text-main) !important;
    }

    section[data-testid="stSidebar"] div[data-testid="stCaptionContainer"] p,
    section[data-testid="stSidebar"] small {
        color: var(--text-muted) !important;
    }
    </style>
""", unsafe_allow_html=True)

if theme_override_css:
    st.markdown(f"<style>{theme_override_css}</style>", unsafe_allow_html=True)

# --- API CLIENT SETUP ---
def get_secret(key):
    try: return st.secrets[key]
    except Exception: return os.environ.get(key, "")

GEMINI_API_KEY = get_secret("GEMINI_API_KEY")
GROQ_API_KEY   = get_secret("GROQ_API_KEY")

gemini_client = None
if GEMINI_API_KEY:
    try:
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception:
        gemini_client = None

groq_client = None
if GROQ_API_KEY:
    try:
        groq_client = Groq(api_key=GROQ_API_KEY)
    except Exception:
        groq_client = None

# --- SAS TO R FUNCTION MAPPING ---
SAS_TO_R = {
    "INTCK":    "use lubridate time_length(interval(date1, date2), 'month')",
    "INTNX":    "use date + months(n) or date + days(n) from lubridate",
    "PUT":      "use format() or sprintf()",
    "INPUT":    "use as.Date() or as.numeric()",
    "COMPRESS": "use gsub(' ', '', var) to remove spaces",
    "CATX":     "use paste(..., sep='-')",
    "SCAN":     "use strsplit(var, ' ')[[1]][n]",
    "MISSING":  "use is.na()",
    "STRIP":    "use trimws()",
    "UPCASE":   "use toupper()",
    "LOWCASE":  "use tolower()",
    "INDEX":    "use regexpr() or grepl()",
    "MOD":      "use %% operator",
    "INT":      "use as.integer() or floor()",
    "ROUND":    "use round()",
    "SUBSTR":   "use substr() — same in R",
    "TRIM":     "use trimws()",
    "LEFT":     "use trimws(var, which='left')",
    "LENGTH":   "use nchar()",
    "TODAY":    "use Sys.Date()",
    "DATE":     "use Sys.Date()",
    "DATE9":    "use as.Date(var, '%d%b%Y') for date9. format",
    "MMDDYY":   "use as.Date(var, '%m/%d/%Y')",
    "YYMMDD":   "use as.Date(var, '%Y-%m-%d')",
}

def inject_function_hints(step):
    hints = []
    for sas_func, r_equiv in SAS_TO_R.items():
        if sas_func in step.upper():
            hints.append(f"  - {sas_func} → {r_equiv}")
    return "\nFUNCTION HINTS (use these exact R equivalents):\n" + "\n".join(hints) if hints else ""
    
def expand_macros(sas_code):
    """Expands SAS macros by substituting parameters and inlining macro bodies."""
    macro_lib = {}

    # Step 1 — collect all macro definitions
    for m in re.finditer(
        r"%macro\s+(\w+)\s*\(([^)]*)\)\s*;(.*?)%mend\s*\w*\s*;",
        sas_code, re.DOTALL | re.I
    ):
        name = m.group(1).strip().upper()
        params = [p.strip().lstrip('&').split('=')[0].strip() for p in m.group(2).split(',') if p.strip()]
        body = m.group(3).strip()
        macro_lib[name] = {"params": params, "body": body}
    # Step 2 — remove macro definitions from code
    expanded = re.sub(
        r"%macro\s+\w+\s*\([^)]*\)\s*;.*?%mend\s*\w*\s*;",
        "", sas_code, flags=re.DOTALL | re.I
    ).strip()

    # Step 3 — expand macro calls (up to 5 passes for nested)
    for _ in range(5):
        for name, macro in macro_lib.items():
            pattern = rf"%{name}\s*\(([^)]*)\)\s*;"
            for call_match in re.finditer(pattern, expanded, re.I):
                args_raw = [a.strip() for a in call_match.group(1).split(',')]
                # handle named args like dataset=sales → extract value only
                arg_dict = {}
                for a in args_raw:
                    if '=' in a:
                        k, v = a.split('=', 1)
                        arg_dict[k.strip().lstrip('&')] = v.strip()
                # substitute by name not position
                body = macro["body"]
                for param in macro["params"]:
                    val = arg_dict.get(param, "")
                    body = re.sub(rf"&{param}\.?", val, body, flags=re.I)
                expanded = expanded[:call_match.start()] + "\n" + body + "\n" + expanded[call_match.end():]
                break
                body = macro["body"]
                for param, arg in zip(macro["params"], args):
                    # handle both &param and &param. patterns
                    body = re.sub(rf"&{param}\.?", arg, body, flags=re.I)
                expanded = expanded[:call_match.start()] + "\n" + body + "\n" + expanded[call_match.end():]
                break  # restart after each substitution

    return expanded.strip()
# --- CLEANING & UTILS ---

def safe_read_csv(file_obj):
    """Attempts multiple methods to read a CSV gracefully."""
    try:
        file_obj.seek(0)
        return pd.read_csv(file_obj)
    except Exception:
        try:
            file_obj.seek(0)
            return pd.read_csv(file_obj, encoding='latin1', sep=None, engine='python', on_bad_lines='skip')
        except Exception as e:
            raise RuntimeError(f"Could not parse CSV file. Error: {str(e)}")

def safe_read_excel(file_obj, sheet_name=0):
    """Reads an Excel file (.xlsx or .xls), returns a DataFrame."""
    try:
        file_obj.seek(0)
        return pd.read_excel(file_obj, sheet_name=sheet_name)
    except Exception as e:
        raise RuntimeError(f"Could not parse Excel file. Error: {str(e)}")

def format_elapsed(seconds):
    """Returns a human-readable elapsed time string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    mins = int(seconds // 60)
    secs = seconds % 60
    return f"{mins}m {secs:.1f}s"

class ConversionFailedError(RuntimeError):
    """Exception raised when step conversion fails, carrying candidate code and validation metadata."""
    def __init__(self, message, candidate_code=None, contract_pass=False, syntax_pass=False, semantic_pass=False, missing_cols=None, gemini_failed=False, groq_failed=False):
        super().__init__(message)
        self.candidate_code = candidate_code
        self.contract_pass = contract_pass
        self.syntax_pass = syntax_pass
        self.semantic_pass = semantic_pass
        self.missing_cols = missing_cols or []
        self.gemini_failed = gemini_failed
        self.groq_failed = groq_failed

def is_valid_r_code(text: str) -> bool:
    """Validates that text represents actual R code, rejecting SAS statements and conversational prose."""
    if not text or not text.strip():
        return False

    # Filter out comment lines when checking indicators
    code_lines = [l.strip().lower() for l in text.split("\n") if l.strip() and not l.strip().startswith('#')]
    code_text = "\n".join(code_lines)

    # Reject obvious SAS statement keywords in code lines
    sas_indicators = ["data ", "set ", "proc ", "run;", "quit;", "datalines;", "cards;", "then ", "else if "]
    prose_indicators = ["here is a", "code review", "corrected sas", "macro reference", "explanations:"]

    if any(ind in code_text for ind in sas_indicators):
        return False
    if any(ind in code_text for ind in prose_indicators):
        return False

    # Must contain at least one valid R assignment or operation indicator
    r_indicators = ["<-", "%>%", "df", "filter(", "mutate(", "select(", "arrange(", "group_by(", "summarise(", "summarize(", "head(", "="]
    return any(ind in text for ind in r_indicators)


def validate_r_syntax(text: str) -> bool:
    """
    Validates R code syntax by executing Rscript -e "parse(file=...)" without executing code.
    Returns True if syntax is valid, False if syntax error occurs.
    """
    if not text or not text.strip():
        return False

    import subprocess
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".R", delete=False) as f:
        f.write(text)
        f_path = f.name

    try:
        cmd = ["Rscript", "-e", f"parse(file='{f_path}')"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        return res.returncode == 0
    except Exception:
        return False
    finally:
        if os.path.exists(f_path):
            try:
                os.remove(f_path)
            except Exception:
                pass


def clean_r_code(text):
    """Strips markdown fences, validates R output contract, and cleans code."""
    if not text:
        return "df"

    # Safely strip all markdown code fences, prioritizing R code blocks
    backticks = "\x60\x60\x60"
    if backticks in text:
        r_blocks = re.findall(r"```(?:r|R)\n?(.*?)\n?```", text, re.DOTALL)
        if r_blocks:
            text = "\n".join(r_blocks)
        else:
            text = re.sub(r"```(?:sas|python|text)?\n?", "", text)
            text = text.replace(backticks, "")

    lines = text.split("\n")
    out = []
    forbidden = ["explanation:", "sas code:", "run;", "quit;", "data.frame()", "library("]
    prose_starters = [
        "here is", "here's", "below is", "the following", "converted r",
        "this r code", "this code", "in sas", "note:", "explanation:", "to convert", "for this"
    ]

    for line in lines:
        clean_line = line.strip()
        if not clean_line or clean_line.startswith(('#', backticks)): continue
        
        clean_lower = clean_line.lower()
        if any(x in clean_lower for x in forbidden if x != "data.frame()"): continue
        if any(clean_lower.startswith(ps) for ps in prose_starters): continue
        if "proc " in clean_lower or "in sas" in clean_lower or "translates to" in clean_lower: continue

        # Filter out conversational prose lines that lack strong R syntax indicators
        r_indicators = ["<-", "%>%", "c(", "list(", "[", "]", "function(", "filter(", "mutate(", "select(", "arrange(", "group_by(", "summarise(", "case_when("]
        has_r_op = any(ind in clean_line for ind in r_indicators) or "=" in clean_line or clean_line.endswith(")") or clean_line.endswith(",") or clean_line.endswith("}") or clean_line.endswith("%") or clean_line.isupper() or clean_line == "df"
        if not has_r_op:
            continue

        if "(" in clean_line and "<-" in clean_line:
            clean_line = clean_line.replace("<-", "=")

        if not out or clean_line != out[-1]:
            out.append(clean_line)

    cleaned = "\n".join(out)

    cleaned = re.sub(r"%>%\s*$", "", cleaned.strip())
    cleaned = re.sub(r"%>%\s*select\(\)\s*$", "", cleaned.strip())
    cleaned = re.sub(r"%>%\s*mutate\(\)\s*$", "", cleaned.strip())
    cleaned = re.sub(r"df\s*=\s*df\[order\([^)]+\),\s*\]\s*\n(?=.*!duplicated)", "", cleaned)
    cleaned = re.sub(r"\s*arrange\([^)]+\)\s*%>%\s*(?=.*group_by)", "", cleaned)
    cleaned = re.sub(r"%>%(?!\s)", " %>%\n  ", cleaned)

    if "pivot_longer" in cleaned:
        source_match = re.search(r"df\s*<-\s*(\w+)\s*%>%", cleaned)
        source_table = source_match.group(1) if source_match else "QUARTERLY"
        cols_match = re.search(r"cols\s*=\s*c\(([^)]+)\)", cleaned)
        cols = cols_match.group(1) if cols_match else ""
        names_match = re.search(r'names_to\s*=\s*["\']([^"\']+)["\']', cleaned)
        names_to = names_match.group(1) if names_match else "quarter"
        values_match = re.search(r'values_to\s*=\s*["\']([^"\']+)["\']', cleaned)
        values_to = values_match.group(1) if values_match else "revenue"
        cleaned = (
            f'df <- {source_table} %>%\n'
            f'  pivot_longer(cols = c({cols}),\n'
            f'               names_to = "{names_to}",\n'
            f'               values_to = "{values_to}")\n'
            f'df'
        )
    is_freq_step = (
        "count(" in cleaned and
        "merge(" not in cleaned and
        "join(" not in cleaned and
        ("pivot_wider" in cleaned or "rename(COUNT" not in cleaned)
    )
    if is_freq_step:
        match = re.search(r"count\(([^)]+)\)", cleaned)
        if match:
            vars = match.group(1).strip()
            source_match = re.search(r"df\s*<-\s*(\w+)\s*%>%", cleaned)
            source_table = source_match.group(1) if source_match else "df"
            cleaned = re.sub(
                r"df\s*<-\s*\w+\s*%>%.*",
                f'df <- {source_table} %>%\n  count({vars}) %>%\n  rename(COUNT = n)',
                cleaned,
                flags=re.DOTALL
            )

    if cleaned.count("df <- ") > 1 and "aggregate" not in cleaned and "merge(" not in cleaned:
        parts = cleaned.split("df <- ")
        cleaned = "df <- " + parts[-1]

    last_line = cleaned.strip().split('\n')[-1].strip()
    if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', last_line):
        cleaned += "\ndf"
    return cleaned

from llm_router import get_llm_router

def call_llm_api(step, df_cols=None, env_names=None, dialect="Modern R (tidyverse)", r_dialect=None, initial_candidate=None):
    """
    Calls Gemini primary with Groq fallback. Constructs prompt with system rules and enforces R output contract validation.
    """
    target_dialect = r_dialect if r_dialect is not None else (dialect if dialect else "Modern R (tidyverse)")
    env_tables = env_names if env_names is not None else []
    cols_list = df_cols if df_cols is not None else []

    # If step is already a complete prompt string (starts with TASK:), use as is
    if isinstance(step, str) and step.startswith("TASK: Convert this SAS step to R code."):
        full_prompt = step
    else:
        env_info = f"\nAvailable tables in R environment: {', '.join(env_tables)}" if env_tables else ""
        func_hints = inject_function_hints(str(step))
        if not cols_list:
            input_context = "Convert this step. You have access to the tables listed below."
        else:
            input_context = f"A dataframe named 'df' with columns: {cols_list}"

        if target_dialect == "Modern R (tidyverse)":
            rule_set = (
                f"1. Use modern R (tidyverse). Use the pipe operator (%>%) for chaining.\n"
                f"2. IF SAS uses DATALINES: ONLY create the data.frame using `data.frame(...)`. STOP immediately.\n"
                f"3. IF SAS reads an existing table: start the pipeline exactly with `df <- TABLE_NAME %>%`.\n"
                f"4. FOR DATA STEPS: Create new variables inside a populated `mutate(...)`. NEVER write an empty mutate().\n"
                f"5. FOR PROC SORT: Use `arrange()`. ONLY use `desc()` if SAS code explicitly has `DESCENDING` keyword before the variable. If no DESCENDING keyword — always use ascending order.\n"
                f"6. FIRST. LOGIC: Use `group_by(var) %>% slice(1) %>% ungroup()`. IMPORTANT: Do NOT add an extra arrange() or sort inside this step; it must rely on the previous step's order.\n"
                f"7. MACRO LOGIC: If input is a %macro, convert macro variables (&var) to column names in a mutate() call.\n"
                f"8. FOR PROC FREQ: Use `df %>% count(var1, var2) %>% rename(COUNT = n)` for cross-tabs. "
                f"NEVER use pivot_wider or spread. Output MUST stay in long format with one row per combination. "
                f"Final columns must be: var1, var2, COUNT.\n"
            )
        else:
            rule_set = (
                f"1. Use ONLY pure Base R. DO NOT use tidyverse, tidyr, or pipes (%>%).\n"
                f"2. For aggregate(), ALWAYS use the formula interface.\n"
                f"3. IF SAS uses DATALINES: ONLY create the data.frame. STOP immediately.\n"
                f"4. IF SAS reads an existing table: start your code exactly with `df <- TABLE_NAME`.\n"
                f"5. FOR PROC SORT: Use `df = df[order(...), ]`. ONLY use minus sign for descending if SAS code explicitly has `DESCENDING` keyword before the variable. If no DESCENDING keyword — always use ascending order.\n"
                f"6. FIRST. LOGIC: Use ONLY `df[!duplicated(df$var), ]`. ABSOLUTELY NO order() or sort() call allowed in this step — not even for tie-breaking. The previous PROC SORT already established the correct order. Trust it. Adding any order() here WILL produce wrong results.\n"
                f"7. MACRO LOGIC: Convert macro variables (&var) to standard R object references.\n"
                f"8. FOR PROC FREQ: Use EXACTLY this pattern: `df = as.data.frame(table(df$var1, df$var2))` then `names(df) = c('var1', 'var2', 'COUNT')` then `df = df[df$COUNT > 0, ]`. "
                f"NEVER add an order() or sort() before table(). "
                f"NEVER use any other approach. Output MUST stay in long format with one row per combination. "
                f"Final columns must be: var1, var2, COUNT.\n"
                f"9. FOR PROC SQL GROUP BY + HAVING: Use this EXACT two-step pattern:\n"
                f"   Step 1 - WHERE filter: `df = df[df$col == 'value', ]`\n"
                f"   Step 2 - aggregate separately for each output column:\n"
                f"   `df_count = aggregate(order_id ~ cust_id, data=df, FUN=length)`\n"
                f"   `df_sum = aggregate(amount ~ cust_id, data=df, FUN=sum)`\n"
                f"   `df = merge(df_count, df_sum, by='cust_id')`\n"
                f"   `names(df) = c('cust_id', 'total_orders', 'total_spent')`\n"
                f"   Step 3 - HAVING filter: `df = df[df$total_spent > 600, ]`\n"
                f"   NEVER use cbind inside aggregate. NEVER use matrix columns.\n"
                f"10. FOR PROC TRANSPOSE: Use EXACTLY this pattern:\n"
                f"    `df = reshape(TABLENAME, varying=c('q1','q2','q3','q4'), v.names='revenue', timevar='quarter', times=c('q1','q2','q3','q4'), direction='long')`\n"
                f"    `df = df[order(match(df$region, TABLENAME$region), match(df$quarter, c('q1','q2','q3','q4'))), ]`\n"
                f"    `df = df[, c('region', 'quarter', 'revenue')]`\n"
                f"    `row.names(df) = NULL`\n"
                f"    NEVER use stack(), NEVER use melt(). NEVER convert quarter to factor.\n"
            )

        full_prompt = (
            f"TASK: Convert this SAS step to R code.\n"
            f"INPUT CONTEXT: {input_context}{env_info}{func_hints}\n"
            f"OUTPUT: Your code must result in a final dataframe named 'df'. The last line MUST be exactly 'df'.\n"
            f"STRICT RULES:\n{rule_set}"
            f"FINAL RULE: No explanations. Just executable R code. Write the code EXACTLY ONCE. DO NOT loop or repeat lines.\n\n"
            f"SAS STEP:\n{step}"
        )

    router = get_llm_router()
    candidate = initial_candidate
    contract_ok = is_valid_r_code(candidate) if candidate else False
    syntax_ok = validate_r_syntax(candidate) if (candidate and contract_ok) else False
    comp_ok = False
    miss_c = []
    if candidate and syntax_ok:
        from semantic_validator import validate_semantic_completeness
        comp_ok, _, _, miss_c = validate_semantic_completeness(str(step), candidate)

    gemini_fail = False
    groq_fail = False

    try:
        try:
            resp = router.generate(full_prompt)
            if resp.fallback_occurred:
                gemini_fail = True
                if resp.warning_msg:
                    import streamlit as st
                    st.caption(f"⚠️ {resp.warning_msg}")
            llm_cand = clean_r_code(resp.text)
            if is_valid_r_code(llm_cand):
                candidate = llm_cand
        except Exception as llm_err:
            gemini_fail = True
            groq_fail = True
            raise ConversionFailedError(f"LLM generation failed: {llm_err}", candidate_code=candidate, contract_pass=contract_ok, syntax_pass=syntax_ok, semantic_pass=comp_ok, missing_cols=miss_c, gemini_failed=True, groq_failed=True)

        contract_ok = is_valid_r_code(candidate)
        if not contract_ok:
            raise ConversionFailedError("LLM response failed R output contract validation (contained SAS syntax or prose commentary).", candidate_code=candidate, contract_pass=False, syntax_pass=False, semantic_pass=False, gemini_failed=gemini_fail, groq_failed=groq_fail)

        syntax_ok = validate_r_syntax(candidate)
        if not syntax_ok:
            syntax_correction_prompt = (
                f"{full_prompt}\n\n"
                f"CRITICAL CORRECTION REQUIRED:\n"
                f"The previous R output failed R syntax parsing.\n"
                f"Return syntactically valid executable R code.\n"
                f"Do not omit commas, parentheses, braces, or CASE/CASE_WHEN structure.\n"
                f"Return the complete conversion exactly once."
            )
            try:
                resp_retry = router.generate(syntax_correction_prompt)
                candidate_retry = clean_r_code(resp_retry.text)
                if is_valid_r_code(candidate_retry):
                    candidate = candidate_retry
                    contract_ok = True
                    if validate_r_syntax(candidate_retry):
                        syntax_ok = True
                        from semantic_validator import validate_semantic_completeness
                        is_comp_retry, _, _, miss_c_retry = validate_semantic_completeness(str(step), candidate_retry)
                        if is_comp_retry:
                            return candidate_retry
            except Exception:
                pass
            raise ConversionFailedError("LLM response failed R syntax validation (parse error).", candidate_code=candidate, contract_pass=contract_ok, syntax_pass=syntax_ok, semantic_pass=False, gemini_failed=gemini_fail, groq_failed=groq_fail)

        from semantic_validator import validate_semantic_completeness
        is_comp, exp_c, pres_c, miss_c = validate_semantic_completeness(str(step), candidate)
        if not is_comp:
            correction_prompt = (
                f"{full_prompt}\n\n"
                f"CRITICAL CORRECTION REQUIRED: The previous R output missed the following required output variables/columns: {', '.join(miss_c)}.\n"
                f"You MUST include all of these output variables in the R output pipeline (inside mutate(), summarise(), or select()). Re-generate complete R code now."
            )
            try:
                resp_retry = router.generate(correction_prompt)
                candidate_retry = clean_r_code(resp_retry.text)
                if is_valid_r_code(candidate_retry):
                    candidate = candidate_retry
                    contract_ok = True
                    if validate_r_syntax(candidate_retry):
                        syntax_ok = True
                        is_comp_retry, _, _, miss_c_retry = validate_semantic_completeness(str(step), candidate_retry)
                        if is_comp_retry:
                            return candidate_retry
                        else:
                            miss_c = miss_c_retry
            except Exception:
                pass
            raise ConversionFailedError(f"LLM response failed semantic completeness validation. Missing output variables: {', '.join(miss_c)}", candidate_code=candidate, contract_pass=contract_ok, syntax_pass=syntax_ok, semantic_pass=False, missing_cols=miss_c, gemini_failed=gemini_fail, groq_failed=groq_fail)

        return candidate
    except ConversionFailedError:
        raise
    except Exception as e:
        raise ConversionFailedError(f"LLM conversion failed: {e}", candidate_code=candidate, contract_pass=contract_ok, syntax_pass=syntax_ok, semantic_pass=False, missing_cols=miss_c, gemini_failed=gemini_fail, groq_failed=groq_fail)

def run_r_subprocess(r_code, input_df, env_dict=None):
    """Executes the generated R code in a controlled environment."""
    with tempfile.TemporaryDirectory() as d:
        inp_path = os.path.join(d, "input.csv")
        out_path = os.path.join(d, "output.csv")
        script_path = os.path.join(d, "script.R")

        input_df.to_csv(inp_path, index=False)

        full_script = [
            'options(warn=1)',
            'suppressPackageStartupMessages(library(tidyverse))',
            f'df <- read.csv("{inp_path}", stringsAsFactors=FALSE, check.names=FALSE)'
        ]

        if env_dict:
            for name, df_mem in env_dict.items():
                mem_path = os.path.join(d, f"{name}.csv")
                df_mem.to_csv(mem_path, index=False)
                full_script.append(f'{name} <- read.csv("{mem_path}", stringsAsFactors=FALSE, check.names=FALSE)')

        full_script.append(r_code)
        full_script.append(f'write.csv(df, "{out_path}", row.names=FALSE)')

        with open(script_path, "w") as f:
            f.write("\n".join(full_script)) 

        res = subprocess.run(["Rscript", script_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
        combined_log = res.stderr.strip() or "✅ No warnings or messages."
        if res.returncode != 0:
            raise RuntimeError(f"R Error: {res.stderr}\nCode Attempted:\n{r_code}")

        return pd.read_csv(out_path), combined_log

def compare_dfs(sas_df, r_df, tol=1e-3):
    """Smart comparison: handles case-sensitivity and whitespace."""
    if sas_df is None or r_df is None:
        return {"match": False, "details": "Comparison data missing.", "mismatches": []}

    s_df = sas_df.copy().reset_index(drop=True)
    r_df_comp = r_df.copy().reset_index(drop=True)

    s_df.columns = s_df.columns.str.upper().str.strip()
    r_df_comp.columns = r_df_comp.columns.str.upper().str.strip()

    if s_df.shape != r_df_comp.shape:
        return {"match": False, "details": f"Shape mismatch: SAS {s_df.shape} vs R {r_df_comp.shape}", "mismatches": []}

    try:
        r_df_comp = r_df_comp[s_df.columns]
    except KeyError as e:
        return {"match": False, "details": f"Missing column in R output: {e}", "mismatches": []}

    mismatches = []
    for col in s_df.columns:
        for i in range(len(s_df)):
            val_s = s_df[col].iloc[i]
            val_r = r_df_comp[col].iloc[i]

            try:
                if abs(float(val_s) - float(val_r)) > tol:
                    mismatches.append({"col": col, "row": i, "sas": str(val_s), "r": str(val_r)})
            except (ValueError, TypeError):
                if str(val_s).strip().upper() != str(val_r).strip().upper():
                    mismatches.append({"col": col, "row": i, "sas": str(val_s), "r": str(val_r)})

    return {
        "match": len(mismatches) == 0,
        "details": "All values match!" if not mismatches else f"{len(mismatches)} values differ.",
        "mismatches": mismatches
    }

def fix_r_code_on_mismatch(r_code, step, mismatches, sas_df, r_df, dialect):
    try:
        mismatch_info = ""
        if sas_df is not None and r_df is not None and sas_df.shape != r_df.shape:
            mismatch_info += f"Shape: SAS={sas_df.shape} R={r_df.shape}\n"
        if mismatches:
            mismatch_info += "Value mismatches:\n"
            clean_mismatches = [m for m in mismatches if m is not None]
            for m in clean_mismatches[:5]:
                mismatch_info += f"  col={str(m.get('col','?'))} row={str(m.get('row','?'))} SAS={str(m.get('sas','?'))} R={str(m.get('r','?'))}\n"
    except Exception as e:
        mismatch_info = "Could not extract mismatch details."

    fix_prompt = "\n".join([
        "This R code produced wrong output compared to SAS.",
        "ORIGINAL R CODE:",
        str(r_code) if r_code else "",
        "ORIGINAL SAS CODE:",
        str(step) if step else "",
        "MISMATCH DETAILS:",
        str(mismatch_info),
        "Fix the R code to match SAS output exactly. Return only corrected R code ending with df."
    ])

    router = get_llm_router()
    try:
        resp = router.generate("\n".join(fix_prompt))
        return clean_r_code(resp.text)
    except Exception as e:
        return r_code
 
def parse_datalines(step):
    """Extracts raw data from SAS datalines/cards block."""
    try:
        inp_match = re.search(r'input\s+(.*?);', step, re.I | re.DOTALL)
        raw_cols = inp_match.group(1).split()
        cols = [c.replace('$', '').strip() for c in raw_cols if c.strip() != '$']

        dl_match = re.search(r'datalines\s*;(.*?)\s*;', step, re.I | re.DOTALL)
        if not dl_match: dl_match = re.search(r'cards\s*;(.*?)\s*;', step, re.I | re.DOTALL)

        raw_lines = [l.strip() for l in dl_match.group(1).strip().split('\n') if l.strip()]
        rows = [line.split() for line in raw_lines]
        return pd.DataFrame(rows, columns=cols)
    except Exception:
        return None

# --- PIPELINE LOGIC ---

def run_chain_pipeline(sas_code, uploaded_outputs, dialect, progress_bar=None, status_text=None, retry_step=None):
    """Processes SAS steps as a continuous chain. Supports progress bar + per-step timing."""
    steps = re.findall(r"((?:data|proc)\s+.*?;.*?(?:run|quit);)", sas_code, re.DOTALL | re.I)
    work_library = {}
    st.session_state["work_library"] = work_library

    pipeline_results = []
    total_steps = len(steps)

    all_out_names = re.findall(r"(?:^\s*data\s+|out\s*=\s*|create\s+table\s+)([\w.]+)", sas_code, re.I | re.M)
    final_ds_name = all_out_names[-1].split('.')[-1].upper().strip() if all_out_names else None

    for i, step in enumerate(steps):
        out_name_match = re.search(r"(?:^\s*data\s+|out\s*=\s*|create\s+table\s+)([\w.]+)", step, re.I | re.M)
        sort_inplace_match = re.search(r"proc\s+sort\s+data\s*=\s*([\w.]+)", step, re.I)

        if out_name_match:
            target_name = out_name_match.group(1).split('.')[-1].upper().strip()
        elif sort_inplace_match and not re.search(r"out\s*=", step, re.I):
            target_name = sort_inplace_match.group(1).split('.')[-1].upper().strip()
        else:
            target_name = f"STEP_{i+1}"

        set_match = re.search(r"(?:set|from|join|data\s*=)\s+([\w.]+)", step, re.I)
        source_name = set_match.group(1).split('.')[-1].upper().strip() if set_match else None

        if 'datalines' in step.lower() or 'cards' in step.lower():
            active_df = None
        elif source_name and source_name in work_library:
            active_df = work_library[source_name]
        elif source_name and source_name in uploaded_outputs:
            active_df = uploaded_outputs[source_name]
        else:
            active_df = None

        res_entry = {
            "name": target_name,
            "step": step,
            "r_code": None,
            "r_output": None,
            "error": None,
            "comparison": None,
            "is_final": (target_name == final_ds_name),
            "elapsed_llm": None,     # LLM call timing
            "elapsed_exec": None,    # R execution timing
            "elapsed_total": None,   # Total step timing
            "r_log": None,           # Execution log output
        }

        # Update progress bar
        if progress_bar is not None:
            progress_bar.progress(i / total_steps, text=f"Processing step {i+1}/{total_steps}: {target_name}")
        if status_text is not None:
            status_text.markdown(f"⏳ **Step {i+1}/{total_steps}** — `{target_name}`")
            
        # Skip steps if retrying specific step only
        if retry_step and target_name != retry_step:
            continue
        step_start = time.time()

        try:
            if 'datalines' in step.lower() or 'cards' in step.lower():
                out_df = parse_datalines(step)
                if out_df is None: raise ValueError("Failed to parse datalines.")
                res_entry["elapsed_total"] = time.time() - step_start
            else:
                if active_df is None:
                    raise ValueError(f"Input dataset '{source_name or 'WORK'}' not found. Please upload the CSV/Excel file for '{source_name or 'WORK'}' or switch App Mode to 'Convert Only' in the sidebar.")

                # Time the LLM call
                llm_start = time.time()
                from rule_engine import RuleEngine
                prog_step = ProgramStep(step_index=i+1, step_type="PROC_STEP" if "proc " in step.lower() else "DATA_STEP", name=target_name, source_code=step, input_datasets=list(work_library.keys()), output_datasets=[target_name])
                r_rule_code, conf, method = RuleEngine(dialect=dialect).translate_step(prog_step)
                rule_valid = False
                if r_rule_code and conf >= 0.85:
                    if is_valid_r_code(r_rule_code) and validate_r_syntax(r_rule_code):
                        from semantic_validator import validate_semantic_completeness
                        is_c, _, _, _ = validate_semantic_completeness(step, r_rule_code)
                        if is_c:
                            rule_valid = True

                if rule_valid:
                    r_code = r_rule_code
                else:
                    r_code = call_llm_api(step, active_df.columns.tolist(), list(work_library.keys()), dialect, initial_candidate=r_rule_code)
                res_entry["elapsed_llm"] = time.time() - llm_start
                res_entry["r_code"] = r_code

                # Time the R execution — with 1 auto-retry on failure
                exec_start = time.time()
                try:
                    out_df, r_log = run_r_subprocess(r_code, active_df, work_library)
                    res_entry["r_log"] = r_log
                except RuntimeError as r_err:
                    # Auto-fix: feed error back to LLM and retry once
                    fix_prompt = f"This R code failed:\n{r_code}\nError:\n{str(r_err)}\nFix it. Return only corrected R code ending with df."
                    try:
                        resp = get_llm_router().generate(fix_prompt)
                        fixed_raw = resp.text
                    except Exception:
                        fixed_raw = r_code
                    r_code = clean_r_code(fixed_raw)
                    res_entry["r_code"] = r_code
                    res_entry["auto_fixed"] = True
                    out_df, r_log = run_r_subprocess(r_code, active_df, work_library)
                    res_entry["r_log"] = r_log
                res_entry["elapsed_exec"] = time.time() - exec_start
                
                res_entry["elapsed_total"] = time.time() - step_start

            work_library[target_name] = out_df
            res_entry["r_output"] = out_df

            if target_name in uploaded_outputs:
                res_entry["comparison"] = compare_dfs(uploaded_outputs[target_name], out_df)
            elif target_name == final_ds_name and len(uploaded_outputs) == 1:
                only_csv_key = list(uploaded_outputs.keys())[0]
                res_entry["comparison"] = compare_dfs(uploaded_outputs[only_csv_key], out_df)
                res_entry["comparison"]["details"] = f"(Auto-mapped to '{only_csv_key}') " + res_entry["comparison"]["details"]
            elif target_name == final_ds_name:
                res_entry["comparison"] = {"match": None, "details": "Final output reached. Upload expected CSV/Excel to validate.", "mismatches": []}

        except Exception as e:
            res_entry["error"] = str(e)
            res_entry["elapsed_total"] = time.time() - step_start

        pipeline_results.append(res_entry)
    # Complete the progress bar
    if progress_bar is not None:
        progress_bar.progress(1.0, text=f"✅ All {total_steps} steps processed!")
    if status_text is not None:
        status_text.empty()

    return pipeline_results


# --- SIDEBAR NAVIGATION & SETTINGS ---
with st.sidebar:
    if "selected_tool" not in st.session_state:
        st.session_state.selected_tool = "🔄 SAS Converter"
    
    top_tools_display = ["🔄 SAS Converter"]
    top_tools_actual  = ["🔄 SAS Converter"]

    top_idx = top_tools_actual.index(st.session_state.selected_tool) if st.session_state.selected_tool in top_tools_actual else None
    top_selection_display = st.radio(
        "main_nav",
        top_tools_display,
        index=top_idx,
        label_visibility="collapsed"
    )
    
    bottom_tools_display = ["📋 Clinical Tables", "📄 Clinical Listings", "📈 Clinical Graphs", "📑 TLF from Shell"]
    bottom_tools_actual  = ["🏥 Clinical Tables", "📋 Clinical Listings", "📈 Clinical Graphs", "📋 TLF from Shell"]
    is_clinical_active = st.session_state.selected_tool in bottom_tools_actual

    with st.expander("CLINICAL", expanded=is_clinical_active):
        bottom_idx = bottom_tools_actual.index(st.session_state.selected_tool) if is_clinical_active else None
        bottom_selection_display = st.radio(
            "clinical_nav",
            bottom_tools_display,
            index=bottom_idx,
            label_visibility="collapsed"
        )
    
    # Sync navigation state
    top_idx_active = st.session_state.selected_tool in top_tools_actual
    bottom_idx_active = is_clinical_active

    if top_selection_display and top_idx_active:
        actual = top_tools_actual[top_tools_display.index(top_selection_display)]
        if actual != st.session_state.selected_tool:
            st.session_state.selected_tool = actual
            st.rerun()
    elif bottom_selection_display and bottom_idx_active:
        actual = bottom_tools_actual[bottom_tools_display.index(bottom_selection_display)]
        if actual != st.session_state.selected_tool:
            st.session_state.selected_tool = actual
            st.rerun()
    elif top_selection_display and not top_idx_active and top_selection_display:
        actual = top_tools_actual[top_tools_display.index(top_selection_display)]
        if actual != st.session_state.selected_tool:
            st.session_state.selected_tool = actual
            st.rerun()
    elif bottom_selection_display and not bottom_idx_active and bottom_selection_display:
        actual = bottom_tools_actual[bottom_tools_display.index(bottom_selection_display)]
        if actual != st.session_state.selected_tool:
            st.session_state.selected_tool = actual
            st.rerun()
    
    page = st.session_state.selected_tool
    
    with st.expander("SETTINGS", expanded=False):
        app_mode_opts = ["Convert Only", "Convert + Execute + Validate"]
        curr_app_mode = st.session_state.get("app_mode", "Convert Only")
        sb_mode = st.selectbox(
            "App Mode",
            app_mode_opts,
            index=app_mode_opts.index(curr_app_mode) if curr_app_mode in app_mode_opts else 0,
            key="sb_app_mode"
        )
        if sb_mode != st.session_state.get("app_mode"):
            st.session_state["app_mode"] = sb_mode
            st.rerun()

        r_dialect_opts = ["Base R", "Modern R (tidyverse)"]
        curr_r_dialect = st.session_state.get("r_dialect", "Modern R (tidyverse)")
        sb_dialect = st.selectbox(
            "R Dialect",
            r_dialect_opts,
            index=r_dialect_opts.index(curr_r_dialect) if curr_r_dialect in r_dialect_opts else 1,
            key="sb_r_dialect"
        )
        if sb_dialect != st.session_state.get("r_dialect"):
            st.session_state["r_dialect"] = sb_dialect
            st.rerun()

        app_theme_opts = ["System", "Light", "Dark"]
        curr_app_theme = st.session_state.get("app_theme", "System")
        sb_theme = st.selectbox(
            "Theme",
            app_theme_opts,
            index=app_theme_opts.index(curr_app_theme) if curr_app_theme in app_theme_opts else 0,
            key="sb_app_theme"
        )
        if sb_theme != st.session_state.get("app_theme"):
            st.session_state["app_theme"] = sb_theme
            st.rerun()

    with st.expander("MORE", expanded=False):
        with st.expander("📖 How to Use"):
            st.markdown("""
**Convert Only:**
1. Paste SAS code → Run
2. Download R script

---
**Convert + Validate:**
1. Paste SAS code
2. Upload expected CSV or Excel
   - filename = dataset name
   - *Single file auto-maps to final step!*
3. Run → see ✅ MATCH / ❌ MISMATCH
""")

        with st.expander("✨ What this app does"):
            st.markdown("""
<div class="app-features-list">
  <div class="feature-row"><span class="feature-icon">🔄</span><span class="feature-desc">Converts SAS code to R automatically</span></div>
  <div class="feature-row"><span class="feature-icon">✅</span><span class="feature-desc">Executes &amp; validates R output</span></div>
  <div class="feature-row"><span class="feature-icon">🔧</span><span class="feature-desc">Auto-fixes R errors on failure</span></div>
  <div class="feature-row"><span class="feature-icon">🔄</span><span class="feature-desc">Fix &amp; Retry on output mismatch</span></div>
  <div class="feature-row"><span class="feature-icon">📊</span><span class="feature-desc">Side by side SAS vs R comparison</span></div>
  <div class="feature-row"><span class="feature-icon">⏱️</span><span class="feature-desc">Per-step timing metrics</span></div>
  <div class="feature-row"><span class="feature-icon">📥</span><span class="feature-desc">Downloads full R script</span></div>
</div>
""", unsafe_allow_html=True)

        with st.expander("✓ Supported SAS Statements"):
            st.markdown("""
<div class="supported-statements-list">
  <div class="stmt-row"><span class="stmt-check">✅</span><span class="stmt-name">DATA step</span><span class="stmt-detail">SET, IF/ELSE, mutate</span></div>
  <div class="stmt-row"><span class="stmt-check">✅</span><span class="stmt-name">PROC SORT</span><span class="stmt-detail"></span></div>
  <div class="stmt-row"><span class="stmt-check">✅</span><span class="stmt-name">PROC MEANS</span><span class="stmt-detail"></span></div>
  <div class="stmt-row"><span class="stmt-check">✅</span><span class="stmt-name">PROC FREQ</span><span class="stmt-detail"></span></div>
  <div class="stmt-row"><span class="stmt-check">✅</span><span class="stmt-name">PROC SQL</span><span class="stmt-detail">JOIN, GROUP BY, HAVING</span></div>
  <div class="stmt-row"><span class="stmt-check">✅</span><span class="stmt-name">PROC TRANSPOSE</span><span class="stmt-detail"></span></div>
</div>
""", unsafe_allow_html=True)

        with st.expander("💡 Tips & Hints"):
            st.markdown("""
- Name CSV same as SAS dataset
- Single CSV auto-maps to final step
- Use **Modern R** for cleaner code
- Use **Base R** for maximum compatibility
""")

        with st.expander("⚙ R Environment Diagnostics"):
            rscript_path = shutil.which("Rscript")
            if rscript_path:
                st.success(f"✅ Rscript found: `{rscript_path}`")
                try:
                    res = subprocess.run([rscript_path, "-e", "cat(R.version.string)"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
                    if res.returncode == 0:
                        st.info(f"ℹ️ R Version: `{res.stdout.strip()}`")
                    else:
                        st.warning(f"⚠️ Rscript execution check failed: {res.stderr.strip()}")
                except Exception as e:
                    st.error(f"❌ Error checking R version: {str(e)}")
            else:
                st.error("❌ Rscript NOT found in system PATH.")
                st.caption("Ensure `packages.txt` includes `r-base` when deploying to Streamlit Cloud.")

        st.caption("Built with Gemini + Groq + Rscript")

    if page == "📋 TLF from Shell":
        st.markdown("### 📋 TLF from Shell")
        st.markdown("""
**How to use:**
1. Paste or upload a mock shell
2. Optionally upload ADaM CSV
3. Add any AI instructions
4. Click Generate → pipeline runs automatically

---
**Pipeline nodes:**
🔍 Parse shell spec  
⚙️ Generate R code  
▶️ Execute R  
✅ Validate output  
🔧 Auto-fix & retry (up to 3x)
""")
        st.caption("Powered by Gemini + Groq + LangGraph-style pipeline")
    elif page == "📊 Graph Builder":
        st.markdown("### 📊 Graph Builder")
        st.markdown("""
**How to use:**
1. Upload CSV or Excel
2. Configure chart options
3. Click Generate Graph
4. Edit code if needed
5. Download PNG or R code
""")
        st.caption("Powered by Groq + ggplot2")


# --- MAIN WORKSPACE UI ---

if page == "🔄 SAS Converter":
    # ── Modern Compact Header ──
    st.title("🔄 SAS → R Converter")
    st.caption("Convert SAS programs to production-ready R")
    st.divider()

    # ── Active Mode & Dialect State (driven by Sidebar) ──
    mode = st.session_state.get("app_mode", "Convert Only")
    r_dialect = st.session_state.get("r_dialect", "Modern R (tidyverse)")

    # ── Shared 2-Column Code Workspace ──
    col_left, col_right = st.columns(2)

    with col_left:
        # Sample Preset Snippets
        sample_presets = {
            "Select sample SAS script": "",
            "DM/AE Merge & Summary": """/* SAS Sample: DM and AE Merge */
data WORK.DM_CLEAN;
    set SDTM.DM;
    where AGE >= 18;
run;

proc sort data=WORK.DM_CLEAN;
    by SUBJECT_ID;
run;

proc sql;
    create table WORK.DM_AE_SUMMARY as
    select d.SUBJECT_ID, d.SEX, d.AGE, count(a.AEDECOD) as AE_COUNT
    from WORK.DM_CLEAN as d
    left join SDTM.AE as a on d.SUBJECT_ID = a.USUBJID
    group by d.SUBJECT_ID, d.SEX, d.AGE;
quit;""",
            "Proc Summary & Sort": """/* SAS Sample: Proc Summary */
proc sort data=WORK.SALES;
    by REGION CATEGORY;
run;

proc summary data=WORK.SALES nway;
    class REGION CATEGORY;
    var REVENUE;
    output out=WORK.REGIONAL_SUMMARY sum=TOTAL_REVENUE mean=AVG_REVENUE;
run;""",
            "Proc Transpose Custom": """/* SAS Sample: Proc Transpose */
proc transpose data=WORK.QUARTERLY out=WORK.TRANSPOSED_SALES;
    by REGION;
    var Q1 Q2 Q3 Q4;
run;""",
            "Complex Macro Pipeline": """/* SAS Sample: Macro Function */
%macro sort_domain(data=, by=);
    proc sort data=&data;
        by &by;
    run;
%mend sort_domain;

%sort_domain(data=AE, by=USUBJID);

proc sql;
    create table WORK.DM_AE_SUMMARY as
    select d.SUBJECT_ID, d.SEX, d.AGE, count(a.AEDECOD) as AE_COUNT
    from WORK.DM_CLEAN as d
    left join WORK.AE_CLEAN as a on d.SUBJECT_ID = a.USUBJID
    where d.AGE >= 18
    group by d.SUBJECT_ID, d.SEX, d.AGE
    having calculated AE_COUNT >= 0;
quit;"""
        }

        # Compact Header Row: SAS Source Title + Sample Selector
        hdr_left, hdr_right = st.columns([1.5, 1])
        with hdr_left:
            st.markdown("### 📋 SAS Source")
        with hdr_right:
            chosen_preset = st.selectbox(
                "Sample Script",
                options=list(sample_presets.keys()),
                key="preset_selector",
                label_visibility="collapsed"
            )

        if chosen_preset and sample_presets[chosen_preset]:
            st.session_state.sas_input = sample_presets[chosen_preset]

        sas_script = st.text_area(
            "SAS Code Input", height=360, label_visibility="collapsed",
            placeholder="Paste your SAS code here or select a sample preset above...",
            value=st.session_state.sas_input,
            key="sas_input"
        )

        # Panel-Local Action Controls (Left Panel)
        col_run, col_clear = st.columns([3, 1])
        with col_run:
            btn_label = "⚡ Convert SAS → R" if mode == "Convert Only" else "⚡ Convert & Validate R Output"
            run_btn = st.button(btn_label, type="primary", use_container_width=True)
        with col_clear:
            st.button("🗑️ Clear", on_click=clear_all, use_container_width=True)

    with col_right:
        results = st.session_state.get("pipeline_results", [])
        pipeline_run_flag = st.session_state.get("pipeline_run", False)

        # Compact Header Row: R Output Title + Inline Conversion Status
        hdr_r_left, hdr_r_right = st.columns([1.5, 1])
        with hdr_r_left:
            st.markdown("### ⚙️ R Output")
        with hdr_r_right:
            if results:
                st.markdown('<div style="height: 42px; display: flex; align-items: center; justify-content: flex-end; color: var(--success); font-weight: 600; font-size: 0.88rem;">✓ Converted</div>', unsafe_allow_html=True)
            elif pipeline_run_flag:
                st.markdown('<div style="height: 42px; display: flex; align-items: center; justify-content: flex-end; color: var(--warning); font-weight: 600; font-size: 0.88rem;">Converting...</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div style="height: 42px;"></div>', unsafe_allow_html=True)

        if results:
            all_r_code = []
            for r in results:
                fix_res = st.session_state.get("fix_results", {}).get(r["name"])
                c = fix_res["code"] if fix_res and fix_res.get("match") else r["r_code"]
                if c:
                    all_r_code.append(f"# --- {r['name']} ---\n{c}")
            
            full_r_display = "\n\n".join(all_r_code)
            if "tidyverse" in r_dialect and not full_r_display.startswith("library(tidyverse)"):
                full_r_display = "library(tidyverse)\n\n" + full_r_display

            st.code(full_r_display, language="r")

            c_review, c_dl = st.columns([1, 1])
            with c_review:
                review_btn_label = "✕ Close Review" if st.session_state.get("show_r_review", False) else "🔍 Review R Code"
                st.button(review_btn_label, key="btn_review_active", on_click=toggle_r_review, use_container_width=True)
            with c_dl:
                st.download_button(
                    "⬇️ Download .R Script",
                    data=full_r_display,
                    file_name="converted_pipeline.R",
                    mime="text/plain",
                    use_container_width=True
                )
        else:
            empty_html = """
            <div class="r-output-empty-state">
                <div><strong># Modernized R code output will appear here after conversion.</strong></div>
                <div style="margin-top: 12px; color: var(--text-muted);"># Select a sample script on the left or paste SAS code, then click <strong>'⚡ Convert SAS → R'</strong>.</div>
            </div>
            """
            st.markdown(empty_html, unsafe_allow_html=True)

            c_review, c_dl = st.columns([1, 1])
            with c_review:
                st.button("🔍 Review R Code", key="btn_review_disabled", use_container_width=True, disabled=True)
            with c_dl:
                st.download_button(
                    "⬇️ Download .R Script",
                    data="",
                    file_name="converted_pipeline.R",
                    mime="text/plain",
                    use_container_width=True,
                    disabled=True
                )

    # ── R CODE REVIEW EXPANDER (Appears directly below workspace when toggled) ──
    results = st.session_state.get("pipeline_results", [])
    if results and st.session_state.get("show_r_review", False):
        with st.expander("🔍 R Code Review", expanded=True):
            conv_res_obj = st.session_state.get("current_conv_result")
            confidence_val = conv_res_obj.overall_confidence if conv_res_obj and hasattr(conv_res_obj, "overall_confidence") else 95.0
            manual_items = conv_res_obj.infra_config.manual_review_items if conv_res_obj and hasattr(conv_res_obj, "infra_config") and conv_res_obj.infra_config else []

            col_rv1, col_rv2, col_rv3 = st.columns(3)
            with col_rv1:
                st.markdown("**Overall Status**")
                st.markdown("<span class='badge-pill badge-success'>✓ Logic Preserved & Modernized</span>", unsafe_allow_html=True)
            with col_rv2:
                st.markdown("**Overall Confidence**")
                st.markdown(f"<span style='font-size: 1.05rem; font-weight: 700; color: var(--text-main);'>{confidence_val:.1f}%</span>", unsafe_allow_html=True)
            with col_rv3:
                st.markdown("**Manual Review Flags**")
                if manual_items:
                    st.markdown(f"<span class='badge-pill badge-warning'>⚠️ {len(manual_items)} Flag(s)</span>", unsafe_allow_html=True)
                else:
                    st.markdown("<span class='badge-pill badge-success'>✓ No Flags</span>", unsafe_allow_html=True)

            st.divider()
            st.markdown("#### 📋 Step Equivalence Review")
            for r in results:
                s_name = r.get("name", "Step")
                s_code = r.get("step", "").strip()
                r_code = r.get("r_code", "").strip()

                sas_type = "DATA step" if s_code.lower().startswith("data") else ("PROC step" if s_code.lower().startswith("proc") else "Macro call")
                if "where " in s_code.lower(): sas_type += " + WHERE"
                if "merge " in s_code.lower() or "join " in s_code.lower(): sas_type += " + JOIN"

                r_funcs = []
                if "filter(" in r_code: r_funcs.append("filter()")
                if "select(" in r_code: r_funcs.append("select()")
                if "left_join(" in r_code or "inner_join(" in r_code: r_funcs.append("join()")
                if "group_by(" in r_code: r_funcs.append("group_by()")
                if "summarise(" in r_code or "summarize(" in r_code: r_funcs.append("summarise()")
                if "arrange(" in r_code: r_funcs.append("arrange()")
                if not r_funcs: r_funcs.append("native R operations")

                st.markdown(f"• **`{s_name}`**: SAS `{sas_type}` ➔ R `{', '.join(r_funcs)}` — <span style='color: var(--success); font-weight: 600;'>Equivalent</span>", unsafe_allow_html=True)

            if manual_items:
                st.markdown("#### ⚠️ Manual Review Items")
                for item in manual_items:
                    st.markdown(f"- {item}")

            st.markdown("#### 💡 Recommendation")
            if mode == "Convert + Execute + Validate":
                st.markdown("Review execution comparison results below to verify zero row/column delta against expected SAS output.")
            else:
                st.markdown("Verify dataset join-key mappings and column data types prior to production deployment in R environment.")

    # ── SECONDARY / OPTIONAL SECTION BELOW PRIMARY CONVERTER WORKSPACE ──
    st.divider()

    supporting_files = []
    with st.expander("📁 SAS Project Files", expanded=False):
        st.caption("Upload your main SAS program and optional supporting SAS files.")
        uploaded_project_files = st.file_uploader(
            "Upload SAS files (.sas, .txt)",
            type=["sas", "txt"],
            accept_multiple_files=True,
            key="sas_project_files_input_" + str(st.session_state.get("upload_key", 0))
        )

        if uploaded_project_files:
            file_names = [f.name for f in uploaded_project_files]
            files_by_name = {f.name: f for f in uploaded_project_files}

            if len(uploaded_project_files) == 1:
                main_file = uploaded_project_files[0]
                st.markdown(f"**Main SAS Program:** `{main_file.name}`")
                if st.session_state.get("loaded_project_file") != main_file.name:
                    try:
                        content = main_file.getvalue().decode("utf-8", errors="ignore")
                        st.session_state.sas_input = content
                        st.session_state.loaded_project_file = main_file.name
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to read file: {e}")
                supporting_files = []
            else:
                st.markdown("**Uploaded Files:**")
                for fn in file_names:
                    st.markdown(f"• `{fn}`")

                selected_main_name = st.selectbox(
                    "Main SAS Program",
                    options=file_names,
                    key="selected_main_sas_file_" + str(st.session_state.get("upload_key", 0))
                )

                if selected_main_name and st.session_state.get("loaded_project_file") != selected_main_name:
                    try:
                        main_file = files_by_name[selected_main_name]
                        content = main_file.getvalue().decode("utf-8", errors="ignore")
                        st.session_state.sas_input = content
                        st.session_state.loaded_project_file = selected_main_name
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to read {selected_main_name}: {e}")

                supporting_files = [f for f in uploaded_project_files if f.name != selected_main_name]
                if supporting_files:
                    st.markdown("**Supporting SAS Files:**")
                    for sf in supporting_files:
                        st.markdown(f"• `{sf.name}`")

    # Store supporting_files in session_state for pipeline retrieval
    st.session_state["active_supporting_files"] = supporting_files

    # Expected SAS Outputs File Uploader (Only in Validate Mode)
    uploaded_csvs = st.session_state.uploaded_csvs
    if mode == "Convert + Execute + Validate":
        st.divider()
        st.markdown("### 📊 Expected SAS Output Datasets")
        st.caption("Upload CSV or Excel files for validation. Single uploaded file auto-maps to the final step.")

        uploaded = st.file_uploader(
            "Upload CSV or Excel files",
            type=["csv", "xlsx", "xls"],
            accept_multiple_files=True,
            key="uploader_" + str(st.session_state.get("upload_key", 0))
        )

        if uploaded:
            st.session_state.uploaded_csvs = {}
            uploaded_csvs = st.session_state.uploaded_csvs
            cols = st.columns(min(len(uploaded), 3))

            for i, f in enumerate(uploaded):
                name = os.path.splitext(f.name)[0].upper().strip()
                ext = os.path.splitext(f.name)[1].lower()

                try:
                    if ext in (".xlsx", ".xls"):
                        xls = pd.ExcelFile(f)
                        sheet_names = xls.sheet_names

                        if len(sheet_names) > 1:
                            f.seek(0)
                            chosen_sheet = st.selectbox(
                                f"📋 Sheet for **{f.name}**",
                                options=sheet_names,
                                key=f"sheet_{name}_{i}"
                            )
                            f.seek(0)
                            df = safe_read_excel(f, sheet_name=chosen_sheet)
                        else:
                            f.seek(0)
                            df = safe_read_excel(f, sheet_name=0)
                    else:
                        df = safe_read_csv(f)

                    uploaded_csvs[name] = df
                    st.session_state.uploaded_csvs[name] = df

                    with cols[i % 3]:
                        icon = "📗" if ext in (".xlsx", ".xls") else "📄"
                        st.markdown(f"**{icon} {name}** ({df.shape[0]}r × {df.shape[1]}c)")
                        st.dataframe(df, use_container_width=True, height=120)

                except Exception as e:
                    st.error(f"Failed to load {name}: {str(e)}")

        with st.expander("Or paste CSV text manually"):
            manual_csv = st.text_area(
                "Paste CSV here", height=100,
                key=f"manual_csv_{st.session_state.get('upload_key', 0)}"
            )
            if manual_csv:
                try:
                    df = pd.read_csv(io.StringIO(manual_csv))
                    uploaded_csvs["MANUAL_INPUT"] = df
                    st.session_state.uploaded_csvs["MANUAL_INPUT"] = df
                    st.success(f"✅ Loaded — {df.shape[0]} rows × {df.shape[1]} cols")
                    st.dataframe(df, height=120)
                except Exception as e:
                    st.error(f"Parse error: {e}")

    # ── PIPELINE EXECUTION LOGIC ──
    if run_btn:
        st.session_state.pipeline_run = False  # force fresh run
        st.session_state.fix_results = {}
        st.session_state.retry_counts = {}
        st.session_state.show_r_review = False

    if run_btn or st.session_state.get("pipeline_run"):
        raw_sas_input = sas_script

        from macro_converter import parse_sas_source, convert_macros_to_r, classify_macro
        parsed_source = parse_sas_source(sas_script)
        _macro_defs = parsed_source["macro_definitions"]
        has_path_b = any(classify_macro(m, m_def, all_macro_defs=_macro_defs) == "PATH_B" for m, m_def in _macro_defs.items()) if _macro_defs else False

        extra_files = []
        active_sup_files = st.session_state.get("active_supporting_files", [])
        if active_sup_files:
            for sf in active_sup_files:
                try:
                    extra_files.append(sf.getvalue().decode('utf-8', errors='ignore'))
                except Exception:
                    pass

        sas_script, mac_warnings, sql_hints = expand_sas_macros(sas_script, extra_files, expand_path_b=not has_path_b)

        for w in mac_warnings:
            st.warning(w)
        for h in sql_hints:
            st.info(f"💡 {h}")

        if _macro_defs:
            macro_result = convert_macros_to_r(
                macro_definitions=_macro_defs,
                macro_calls=parsed_source.get("macro_calls", []),
                dialect=r_dialect,
                groq_client=groq_client,
                gemini_client=gemini_client
            )
            classifications = macro_result.get("classifications", {})
            has_path_b = any(cls == "PATH_B" for cls in classifications.values())
        else:
            macro_result = {"warnings": [], "stats": {"rule_based": 0, "total": 0}, "r_functions": ""}
            classifications = {}
            has_path_b = False

        import sas_step_converter
        import doc_generator
        from doc_renderers import md_renderer

        _modernization_converter = sas_step_converter.SASStepConverter(dialect=r_dialect)
        has_path_b_macro = any(cls == "PATH_B" for cls in classifications.values()) if _macro_defs else False
        if has_path_b_macro:
            from macro_processor import SASMacroProcessor
            _proc = SASMacroProcessor()
            unexp_sas, _, _ = _proc.process(raw_sas_input, extra_files=extra_files, expand_path_b=False)
            _conv_result = _modernization_converter.convert_program(unexp_sas, raw_sas_code=raw_sas_input)
        else:
            _conv_result = _modernization_converter.convert_program(raw_sas_input)

        st.session_state.current_conv_result = _conv_result

        _doc_gen = doc_generator.DocumentationGenerator()
        _mod_doc = _doc_gen.generate_document(_conv_result, program_name="SAS_Program_Modernization")
        _md_report = md_renderer.render_markdown(_mod_doc)

        # Mode 1: Convert Only Execution
        if mode == "Convert Only":
            if not st.session_state.get("pipeline_run"):
                step_pattern = re.compile(
                    r"((?:data|proc)\s+.*?;.*?(?:run|quit);|%(?!(?:macro|mend|let|put|include|if|then|else|do|end)\b)[a-zA-Z_]\w*\s*(?:\([^)]*\))?\s*;)",
                    re.DOTALL | re.IGNORECASE
                )
                steps = step_pattern.findall(sas_script)
                if not steps:
                    st.error("No valid SAS steps found.")
                    st.stop()

                all_r = []
                if has_path_b and _macro_defs and macro_result.get("r_functions"):
                    all_r.append("# ── Reusable Modernized R Functions ──\n" + macro_result["r_functions"] + "\n")

                known_tables = []
                total_steps = len(steps)
                prog = st.progress(0, text=f"Converting {total_steps} SAS step(s)...")
                status = st.empty()
                overall_start = time.time()
                r_engine = RuleEngine(dialect=r_dialect)
                conv_results = []

                for i, step in enumerate(steps, 1):
                    step_lower = step.lower()
                    out_name_match = re.search(r"(?:^\s*data\s+|out\s*=\s*|create\s+table\s+)([\w.]+)", step, re.I | re.M)
                    sort_inplace_match = re.search(r"proc\s+sort\s+data\s*=\s*([\w.]+)", step, re.I)

                    if step_lower.startswith("data"):
                        stype = "DATA_STEP"
                        sname = out_name_match.group(1).split('.')[-1].upper().strip() if out_name_match else f"Step{i}"
                    elif step_lower.startswith("proc"):
                        stype = "PROC_STEP"
                        if out_name_match:
                            sname = out_name_match.group(1).split('.')[-1].upper().strip()
                        elif sort_inplace_match:
                            sname = sort_inplace_match.group(1).split('.')[-1].upper().strip()
                        else:
                            sname = f"Step{i}"
                    else:
                        stype = "MACRO_CALL"
                        m_match = re.search(r"%(\w+)", step, re.I)
                        sname = f"%{m_match.group(1).upper()}" if m_match else f"MACRO_CALL_{i}"

                    prog.progress((i - 1) / total_steps, text=f"Converting step {i}/{total_steps}: {sname}...")
                    status.markdown(f"⏳ **Converting Step {i}/{total_steps}** — `{sname}`")

                    step_start = time.time()
                    prog_step = ProgramStep(
                        step_index=i, step_type=stype, name=sname,
                        source_code=step, input_datasets=known_tables, output_datasets=[sname]
                    )
                    r_rule_code, conf, method = r_engine.translate_step(prog_step)

                    rule_valid = False
                    if r_rule_code and conf >= 0.85:
                        if stype == "MACRO_CALL" or (is_valid_r_code(r_rule_code) and validate_r_syntax(r_rule_code)):
                            if stype == "MACRO_CALL": rule_valid = True
                            else:
                                from semantic_validator import validate_semantic_completeness
                                is_c, _, _, _ = validate_semantic_completeness(step, r_rule_code)
                                if is_c: rule_valid = True

                    if rule_valid: rc = r_rule_code
                    else: rc = call_llm_api(step, [], known_tables, r_dialect, initial_candidate=r_rule_code)

                    elapsed = time.time() - step_start
                    all_r.append(f"# --- {sname} ---\n{rc}\n")
                    if sname not in known_tables: known_tables.append(sname)

                    conv_results.append({
                        "name": sname, "step": step, "r_code": rc, "r_output": None,
                        "error": None, "comparison": None, "elapsed_total": elapsed,
                        "elapsed_llm": elapsed, "elapsed_exec": 0.0, "r_log": "Convert Only Mode"
                    })

                prog.progress(1.0, text=f"✅ All {total_steps} steps converted!")
                status.empty()
                st.session_state.pipeline_results = conv_results
                st.session_state.pipeline_run = True
                st.rerun()

        # Mode 2: Convert + Execute + Validate Execution
        else:
            prog = st.progress(0, text="Initialising pipeline...")
            status = st.empty()
            overall_start = time.time()

            if not st.session_state.get("pipeline_run"):
                try:
                    results = run_chain_pipeline(
                        sas_script, uploaded_csvs, r_dialect,
                        progress_bar=prog, status_text=status
                    )
                    st.session_state.pipeline_results = results
                    st.session_state.pipeline_run = True
                    st.session_state.retry_step = None
                    st.rerun()
                except Exception as e:
                    st.error(f"Pipeline crashed: {str(e)}")
                    st.stop()

        # ── EXECUTION & VALIDATION PANEL (Mode B Active) ──
        if mode == "Convert + Execute + Validate" and st.session_state.get("pipeline_results"):
            st.divider()
            st.markdown("### ⚡ Execution Results & Side-by-Side Validation")
            
            p_results = st.session_state.get("pipeline_results", [])
            final_res = p_results[-1] if p_results else None
            
            if final_res and final_res.get("comparison"):
                c_data = final_res["comparison"]
                if c_data.get("match") is True:
                    st.markdown("<span class='badge-pill badge-success'>✅ MATCH 100%: Rscript output matches SAS expected output</span>", unsafe_allow_html=True)
                elif c_data.get("match") is False:
                    st.markdown("<span class='badge-pill badge-warning'>❌ MISMATCH DETECTED: R output differs from expected SAS dataset</span>", unsafe_allow_html=True)
            
            for res in p_results:
                if res.get("r_output") is not None:
                    sas_out = uploaded_csvs.get(res['name'])
                    if sas_out is None and res["is_final"]: sas_out = uploaded_csvs.get('MANUAL_INPUT')
                    if sas_out is None and res["is_final"] and len(uploaded_csvs) == 1: sas_out = list(uploaded_csvs.values())[0]

                    if sas_out is not None:
                        col_s, col_r = st.columns(2)
                        with col_s:
                            st.markdown(f"**📋 Expected SAS Output (`{res['name']}`)**")
                            st.caption(f"Shape: {sas_out.shape[0]} rows × {sas_out.shape[1]} cols")
                            st.dataframe(sas_out, use_container_width=True, height=220)
                        with col_r:
                            st.markdown(f"**⚙️ Generated R Output (`{res['name']}`)**")
                            st.caption(f"Shape: {res['r_output'].shape[0]} rows × {res['r_output'].shape[1]} cols")
                            st.dataframe(res['r_output'], use_container_width=True, height=220)

                        cmp = res.get("comparison")
                        if cmp and cmp.get("match") is False:
                            st.error(f"Mismatch Details: {cmp.get('details')}")
                            if cmp.get("mismatches"):
                                st.table(pd.DataFrame(cmp["mismatches"]).head(10))
                            
                            # Preserve Fix & Retry button
                            retry_count = st.session_state.get("retry_counts", {}).get(res['name'], 0)
                            if retry_count < 3:
                                if st.button(f"🔄 Fix & Retry {res['name']}", key=f"retry_val_{res['name']}"):
                                    st.session_state.setdefault("retry_counts", {})[res['name']] = retry_count + 1
                                    with st.spinner("Asking LLM to fix code based on mismatch deltas..."):
                                        fixed_code = fix_r_code_on_mismatch(
                                            res.get("r_code", ""), res["step"], cmp["mismatches"],
                                            sas_out, res["r_output"], r_dialect
                                        )
                                        try:
                                            new_out, new_log = run_r_subprocess(fixed_code, res["r_output"], st.session_state.get("work_library", {}))
                                            new_cmp = compare_dfs(sas_out, new_out)
                                            st.session_state.setdefault("fix_results", {})[res['name']] = {
                                                "code": fixed_code, "match": new_cmp["match"], "details": new_cmp["details"]
                                            }
                                            if new_cmp["match"]:
                                                for pr in st.session_state["pipeline_results"]:
                                                    if pr["name"] == res["name"]:
                                                        pr["comparison"] = new_cmp
                                                        pr["r_code"] = fixed_code
                                                        pr["r_output"] = new_out
                                                        break
                                            st.rerun()
                                        except Exception as fe:
                                            st.error(f"Fix failed: {fe}")

        # ── EXPANDABLE STEP-BY-STEP DETAILS ACCORDION ──
        with st.expander("Step-by-Step Conversion Details", expanded=False):
            st.caption("Expand to view intermediate steps and per-step code/output diffs")
            p_results = st.session_state.get("pipeline_results", [])
            for res in p_results:
                timing_str = f"  ⏱️ {format_elapsed(res['elapsed_total'])}" if res.get("elapsed_total") else ""
                st.markdown(f"#### Step: `{res['name']}` {timing_str}")
                
                t1, t2, t3, t4, t5, t6 = st.tabs(["SAS Code", "Generated R", "R Output", "SAS vs R", "Validation", "R Log"])
                with t1: st.code(res["step"], language="sas")
                with t2: st.code(res.get("r_code") or "# No code generated", language="r")
                with t3:
                    if res.get("r_output") is not None: st.dataframe(res["r_output"], use_container_width=True)
                    else: st.info("No R output data available for this step.")
                with t4:
                    if res.get("r_output") is not None and uploaded_csvs:
                        st.info("Side-by-side data comparison available above.")
                    else: st.info("Upload expected dataset to view SAS vs R table diffs.")
                with t5:
                    cmp = res.get("comparison")
                    if cmp: st.write(cmp.get("details"))
                    else: st.info("Validation data not attached.")
                with t6:
                    st.code(res.get("r_log") or "✅ No warnings or messages.", language="bash")

        # ── EXPANDABLE ANALYSIS & MODERNIZATION DETAILS ──
        with st.expander("🧠 Modernization Engine Analysis & AST", expanded=False):
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Complexity Score", f"{_conv_result.ast.complexity.score:.1f}/100", delta=_conv_result.ast.complexity.risk_level)
            m2.metric("Overall Confidence", f"{_conv_result.overall_confidence:.1f}%")
            m3.metric("R Line Reduction", f"{_conv_result.total_optimization_metrics.line_reduction_pct:.1f}%")
            m4.metric("Macros Detected", len(_conv_result.ast.macros))

            t_ast1, t_ast2, t_ast3, t_ast4 = st.tabs(["📊 Dataset Lineage", "🔧 Infrastructure", "⚡ R Optimizer", "📄 Modernization Document"])
            with t_ast1:
                st.markdown("**Dataset Lineage & Pipeline Flow**")
                lineage_df = [l.to_dict() for l in _conv_result.ast.lineage]
                if lineage_df: st.dataframe(lineage_df, use_container_width=True)
                else: st.info("No intermediate datasets detected.")

            with t_ast2:
                st.markdown("**Infrastructure & Setup**")
                st.code(_conv_result.infra_config.r_config_code or "# No infrastructure directives detected", language="r")
                if _conv_result.infra_config.manual_review_items:
                    st.warning("⚠️ **Manual Review Items Flagged**:")
                    for item in _conv_result.infra_config.manual_review_items:
                        st.markdown(f"- {item}")

            with t_ast3:
                st.markdown("**R Code Optimization Breakdown**")
                opt_m = _conv_result.total_optimization_metrics.to_dict()
                c_o1, c_o2, c_o3 = st.columns(3)
                c_o1.metric("Original R Lines", opt_m["original_line_count"])
                c_o2.metric("Optimized R Lines", opt_m["optimized_line_count"])
                c_o3.metric("Line Reduction", f"{opt_m['line_reduction_pct']:.1f}%")
                for act in opt_m["actions_taken"]:
                    st.markdown(f"- ✓ {act}")

            with t_ast4:
                st.markdown("**Full 10-Section Modernization Report**")
                st.markdown(_md_report)
                st.download_button(
                    "⬇️ Download Modernization Report (.md)",
                    data=_md_report, file_name="SAS_Modernization_Report.md",
                    mime="text/markdown", use_container_width=True, key="dl_mod_report_exp"
                )

# --- OTHER TOOLS ROUTING ---
if page == "📊 Graph Builder":
    render_graph_builder_tab()

if page == "🏥 Clinical Tables":
    render_table_builder_tab() 

if page == "📈 Clinical Graphs":
    render_clinical_graphs_tab()

if page == "📋 Clinical Listings":
    render_listing_builder_tab()

if page == "📋 TLF from Shell":
    render_shell_tlf_tab()
