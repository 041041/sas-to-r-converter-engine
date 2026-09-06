import os, sys, re, tempfile, subprocess
import pandas as pd
import streamlit as st

# Ensure root directory is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

CHART_TYPES = [
    "Bar Chart",
    "Line Chart",
    "Scatter Plot",
    "Histogram",
    "Box Plot",
    "Pie Chart",
    "Area Chart",
]

CLINICAL_CHART_TYPES = [
    "Kaplan-Meier Survival Curve",
    "Forest Plot (Subgroup Analysis)",
    "Waterfall Plot (Tumor Response)",
    "Box Plot by Visit (Lab Values)",
    "Spaghetti Plot (Patient Trajectories)",
    "Mean ± SD Plot by Visit",
    "Dot Plot (Biomarker)",
    "Swimmer Plot (Patient Timeline)",
]

THEMES = ["minimal", "classic", "bw", "light", "dark"]
PALETTES = ["default", "Set1", "Set2", "Dark2", "Viridis"]


def ensure_clinical_packages():
    rscript = shutil.which("Rscript") if 'shutil' in sys.modules else None
    if not rscript:
        import shutil
        rscript = shutil.which("Rscript")
    if not rscript:
        return False, "Rscript not found in system PATH"
    
    script = """
pkgs <- c("ggplot2", "dplyr", "survival", "survminer", "gridExtra")
missing <- pkgs[!sapply(pkgs, requireNamespace, quietly=TRUE)]
if (length(missing) > 0) {
    install.packages(missing, repos="https://cloud.r-project.org/", quiet=TRUE)
}
"""
    try:
        res = subprocess.run([rscript, "-e", script], capture_output=True, text=True, timeout=120)
        return (res.returncode == 0), res.stderr
    except Exception as e:
        return False, str(e)


def execute_graph(r_code: str, df: pd.DataFrame) -> tuple[bytes, str]:
    import shutil
    rscript = shutil.which("Rscript")
    if not rscript:
        raise RuntimeError("Rscript not found in system PATH.")

    with tempfile.TemporaryDirectory() as d:
        inp_path = os.path.join(d, "data.csv")
        out_path = os.path.join(d, "graph.png")
        script_path = os.path.join(d, "script.R")

        df.to_csv(inp_path, index=False)

        full_script = f"""
options(warn=1)
suppressPackageStartupMessages({{
  library(ggplot2)
  library(dplyr)
  library(readr)
}})

df <- read.csv("{inp_path}", stringsAsFactors=FALSE, check.names=FALSE)

{r_code}

ggsave("{out_path}", plot=last_plot(), width=8, height=5, dpi=150)
"""
        with open(script_path, "w") as f:
            f.write(full_script)

        res = subprocess.run([rscript, script_path], capture_output=True, text=True, timeout=30)
        log = res.stderr.strip() or "✅ Execution successful"

        if res.returncode != 0:
            raise RuntimeError(f"R execution failed:\n{res.stderr}\nCode:\n{r_code}")

        if not os.path.exists(out_path):
            raise RuntimeError(f"Chart PNG was not generated.\nLog:\n{res.stderr}")

        with open(out_path, "rb") as f:
            png_bytes = f.read()

        return png_bytes, log


def execute_clinical_graph(r_code: str, df: pd.DataFrame) -> tuple[bytes, str]:
    import shutil
    rscript = shutil.which("Rscript")
    if not rscript:
        raise RuntimeError("Rscript not found in system PATH.")

    with tempfile.TemporaryDirectory() as d:
        inp_path = os.path.join(d, "data.csv")
        out_path = os.path.join(d, "clinical_graph.png")
        script_path = os.path.join(d, "script.R")

        df.to_csv(inp_path, index=False)

        full_script = f"""
options(warn=1)
suppressPackageStartupMessages({{
  library(ggplot2)
  library(dplyr)
  library(readr)
  if (requireNamespace("survival", quietly=TRUE)) library(survival)
  if (requireNamespace("survminer", quietly=TRUE)) library(survminer)
  if (requireNamespace("gridExtra", quietly=TRUE)) library(gridExtra)
}})

df <- read.csv("{inp_path}", stringsAsFactors=FALSE, check.names=FALSE)

{r_code}

if (exists("p_surv")) {{
  ggsave("{out_path}", plot=p_surv$plot, width=9, height=6, dpi=150)
}} else {{
  ggsave("{out_path}", plot=last_plot(), width=9, height=6, dpi=150)
}}
"""
        with open(script_path, "w") as f:
            f.write(full_script)

        res = subprocess.run([rscript, script_path], capture_output=True, text=True, timeout=45)
        log = res.stderr.strip() or "✅ Execution successful"

        if res.returncode != 0:
            raise RuntimeError(f"Clinical graph execution failed:\n{res.stderr}\nCode:\n{r_code}")

        if not os.path.exists(out_path):
            raise RuntimeError(f"Chart PNG was not generated.\nLog:\n{res.stderr}")

        with open(out_path, "rb") as f:
            png_bytes = f.read()

        return png_bytes, log


def generate_graph_code(selections: dict, df_preview: str, col_types: dict) -> str:
    from llm_router import get_llm_router
    prompt = f"""
Generate standalone R ggplot2 code for a dataframe named 'df'.
Selections: {selections}
Data columns: {col_types}
Preview: {df_preview}

Rules:
- DO NOT include library() calls or read.csv(). Dataframe 'df' is already loaded.
- DO NOT call ggsave().
- Assign plot to last statement (e.g. ggplot(...) + ...).
- Return ONLY valid R code. No explanations, no markdown fences.
"""
    resp = get_llm_router().generate(prompt)
    code = resp.text.strip()
    code = re.sub(r'```[rR]?\n?', '', code)
    code = re.sub(r'```', '', code)
    return code.strip()


def generate_clinical_code(chart_type: str, selections: dict) -> str:
    from llm_router import get_llm_router
    prompt = f"""
Generate standalone R ggplot2 code for a clinical graph: '{chart_type}'.
Dataframe 'df' is already in memory.
User Selections: {selections}

Rules:
- If Kaplan-Meier: use survfit(Surv({selections.get('time_col')}, {selections.get('event_col')}) ~ {selections.get('group_col', 1)}, data=df) and ggsurvplot(..., data=df). Assign result to 'p_surv'.
- If Forest plot: use ggplot() with geom_point() and geom_errorbarh().
- If Waterfall plot: arrange response descending, add rank column, use geom_bar(stat="identity").
- Return ONLY valid R code. No explanations, no markdown fences.
"""
    resp = get_llm_router().generate(prompt)
    code = resp.text.strip()
    code = re.sub(r'```[rR]?\n?', '', code)
    code = re.sub(r'```', '', code)
    return code.strip()


def show_code_diff(old_code: str, new_code: str):
    import difflib
    old_lines = old_code.splitlines(keepends=True)
    new_lines = new_code.splitlines(keepends=True)
    diff = list(difflib.unified_diff(old_lines, new_lines, fromfile="Original", tofile="Enhanced"))
    
    formatted = []
    for line in diff:
        if line.startswith('+') and not line.startswith('+++'):
            formatted.append(f"<span style='color:#059669; font-weight:bold;'>{line}</span>")
        elif line.startswith('-') and not line.startswith('---'):
            formatted.append(f"<span style='color:#DC2626; font-weight:bold;'>{line}</span>")
        else:
            formatted.append(f"<span style='color:#64748B;'>{line}</span>")
    
    st.markdown(f"<pre style='background:#0F172A; color:#E2E8F0; padding:12px; border-radius:6px; font-size:0.84rem; line-height:1.5;'>{''.join(formatted)}</pre>", unsafe_allow_html=True)


def clear_graph():
    for key in ["graph_df", "graph_r_code", "graph_png", "graph_png_accepted",
                "graph_log", "graph_error", "graph_preview_png",
                "graph_r_code_pending", "graph_r_code_original"]:
        st.session_state[key] = None
    st.session_state["graph_r_code"] = ""


def render_graph_builder_tab():
    st.title("📊 R Graph Builder")
    st.caption("Upload data → Configure chart options → Generate ggplot2 code → Preview & Download")
    st.divider()

    # --- SESSION STATE INIT ---
    for key, default in {
        "graph_df": None,
        "graph_r_code": "",
        "graph_png": None,
        "graph_png_accepted": None,
        "graph_png_before_preview": None,
        "graph_log": "",
        "graph_error": None,
        "graph_preview_png": None,
        "graph_r_code_pending": None,
        "graph_r_code_original": None,
        "custom_request_text": "",
        "_run_r_now": False,
        "graph_chart_type": "Bar Chart",
        "graph_x_col": None,
        "graph_y_col": None,
        "graph_color_col": None,
        "graph_orientation": "vertical",
        "graph_title": "",
        "graph_theme": "minimal",
        "graph_palette": "default",
        "graph_sort_order": "none",
        "graph_show_values": False,
    }.items():
        if key not in st.session_state:
            st.session_state[key] = default

    # --- DATA UPLOAD ---
    with st.container():
        st.markdown("### 📁 Upload Input Data")
        uploaded = st.file_uploader(
            "Upload CSV or Excel file",
            type=["csv", "xlsx", "xls"],
            key="graph_upload"
        )

        df = st.session_state.get("graph_df", None)

        if uploaded:
            try:
                ext = os.path.splitext(uploaded.name)[1].lower()
                df = pd.read_excel(uploaded) if ext in (".xlsx", ".xls") else pd.read_csv(uploaded)
                df.columns = df.columns.str.strip()
                st.session_state["graph_df"] = df
                st.success(f"✅ Data loaded successfully — {df.shape[0]} rows × {df.shape[1]} columns")
                st.dataframe(df.head(5), use_container_width=True)
            except Exception as e:
                st.error(f"Failed to load file: {e}")
                return

        with st.expander("📋 Or paste CSV text manually"):
            manual_csv = st.text_area("Paste CSV here", height=100, key="graph_manual_csv")
            if manual_csv:
                try:
                    import io
                    df = pd.read_csv(io.StringIO(manual_csv))
                    df.columns = df.columns.str.strip()
                    st.session_state["graph_df"] = df
                    st.success(f"✅ Data loaded — {df.shape[0]} rows × {df.shape[1]} cols")
                    st.dataframe(df.head(5), use_container_width=True)
                except Exception as e:
                    st.error(f"Parse error: {e}")

    if df is None:
        st.info("👆 Upload a CSV or Excel file or paste CSV text to configure your chart.")
        return
    st.divider()

    # --- CONFIGURE CHART ---
    st.markdown("### ⚙️ Configure Chart Parameters")
    cols = df.columns.tolist()
    numeric_cols = df.select_dtypes(include='number').columns.tolist()
    all_cols_with_none = ["None"] + cols
    
    saved_x = st.session_state.get("graph_x_col")
    saved_y = st.session_state.get("graph_y_col") 
    saved_color = st.session_state.get("graph_color_col")
    
    x_default = cols.index(saved_x) if saved_x in cols else 0
    y_default = all_cols_with_none.index(saved_y) if saved_y in all_cols_with_none else (
        next((all_cols_with_none.index(c) for c in numeric_cols if c in all_cols_with_none), 0)
    )
    color_default = all_cols_with_none.index(saved_color) if saved_color in all_cols_with_none else 0

    r1a, r1b, r1c, r1d, r1e = st.columns(5)
    with r1a:
        chart_type = st.selectbox("📊 Chart Type", CHART_TYPES, key="graph_chart_type")
    with r1b:
        x_col = st.selectbox("📋 X Axis", cols, index=x_default)
        st.session_state["graph_x_col"] = x_col
    with r1c:
        y_col = st.selectbox("📈 Y Axis", all_cols_with_none, index=y_default)
        st.session_state["graph_y_col"] = y_col
    with r1d:
        color_col = st.selectbox("🎨 Color By", all_cols_with_none, index=color_default, key="graph_color_col_widget")
        st.session_state["graph_color_col"] = color_col
    with r1e:
        orientation = st.selectbox("📐 Orientation", ["vertical", "horizontal"], key="graph_orientation")

    r2a, r2b, r2c, r2d, r2e = st.columns(5)
    with r2a:
        default_title = st.session_state.get("graph_title") or f"{chart_type} of {x_col}"
        title = st.text_input("📝 Title", value=default_title)
        st.session_state["graph_title"] = title
    with r2b:
        theme = st.selectbox("🎨 Theme", THEMES, key="graph_theme")
    with r2c:
        palette = st.selectbox("🖌️ Palette", PALETTES, key="graph_palette")
    with r2d:
        sort_order = st.selectbox("📏 Sort Bars", ["none", "asc", "desc"], key="graph_sort_order")
    with r2e:
        st.write("")
        show_values = st.checkbox("🔢 Show Values", value=False, key="graph_show_values")

    selections = {
        "chart_type":   chart_type,
        "x_col":        x_col,
        "y_col":        y_col if y_col != "None" else None,
        "color_col":    color_col if color_col != "None" else None,
        "title":        title,
        "theme":        theme,
        "orientation":  orientation,
        "palette":      palette,
        "show_values":  show_values,
        "sort_order":   sort_order,
    }

    col_types  = {c: str(df[c].dtype) for c in cols}
    df_preview = df.head(3).to_string()

    st.divider()

    # --- OUTPUT DISPLAY ---
    if st.session_state.get("graph_r_code"):
        st.markdown("### 📤 Output Preview & Code")
        out1, out2 = st.tabs(["📊 Rendered Chart Preview", "💻 Editable R Code"])
        with out1:
            img_to_show = st.session_state.get("graph_png_accepted") or st.session_state.get("graph_png")
            if img_to_show:
                st.image(img_to_show, use_container_width=True)
                st.download_button(
                    "⬇️ Download Chart PNG",
                    data=img_to_show,
                    file_name="graph.png",
                    mime="image/png"
                )
            elif st.session_state.get("graph_error"):
                st.error(st.session_state["graph_error"])

        with out2:
            edited_code = st.text_area(
                "Edit ggplot2 R Code",
                value=st.session_state.get("graph_r_code", ""),
                height=280,
                key=f"edited_r_code_{hash(st.session_state.get('graph_r_code', ''))}"
            )
            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                run_edit = st.button("▶️ Run Edited Code", type="primary", use_container_width=True)
            with btn_col2:
                st.download_button(
                    "⬇️ Download .R Script",
                    data=edited_code,
                    file_name="graph.R",
                    mime="text/plain",
                    use_container_width=True
                )
            if run_edit:
                with st.spinner("Running updated R script..."):
                    try:
                        png_bytes, r_log = execute_graph(edited_code, st.session_state.get("graph_df"))
                        st.session_state["graph_png"] = png_bytes
                        st.session_state["graph_png_accepted"] = png_bytes
                        st.session_state["graph_log"] = r_log
                        st.session_state["graph_r_code"] = edited_code
                        st.rerun()
                    except RuntimeError as e:
                        st.error(str(e))
            log = st.session_state.get("graph_log", "")
            if log:
                with st.expander("📋 R Console Log"):
                    st.code(log, language="bash")

    # --- CUSTOM ENHANCEMENT ---
    custom_request = st.text_area(
        "✨ AI Custom Enhancement Prompt (optional)",
        placeholder="e.g. Add trend line, move legend to bottom, use dark theme, add subtitle...",
        height=80,
        key="custom_request_text",
    )

    # --- GENERATE BUTTONS ---
    btn1, btn2 = st.columns([4, 1])
    with btn1:
        generate = st.button("🎨 Generate Graph", type="primary", use_container_width=True)
    with btn2:
        st.button("🗑️ Clear Workspace", on_click=clear_graph, use_container_width=True)

    if generate:
        if chart_type in ["Bar Chart", "Line Chart", "Scatter Plot", "Area Chart"] and not selections.get("y_col"):
            st.error("⚠️ Please select a Y axis column for this chart type!")
            st.stop()

        with st.spinner("🤖 Generating ggplot2 R code..."):
            try:
                r_code = generate_graph_code(selections, df_preview, col_types)

                r_code_for_enhancement = st.session_state["graph_r_code"] if st.session_state.get("graph_r_code") else r_code

                if custom_request.strip():
                    enhance_prompt = (
                        f"You are a ggplot2 code editor. Apply ONLY the requested change to the existing code.\n\n"
                        f"EXISTING CODE:\n```r\n{r_code_for_enhancement}\n```\n\n"
                        f"REQUEST: {custom_request}\n\n"
                        f"RULES:\n"
                        f"- Touch ONLY what the request asks. Preserve everything else exactly as in EXISTING CODE.\n"
                        f"- MERGE new settings into existing theme() block — never rewrite or replace the whole theme().\n"
                        f"- Keep all aes(), geom type, labs(), legend, colors and style from EXISTING CODE unless request explicitly changes them.\n"
                        f"- Return ONLY complete R code. No explanations, no markdown fences.\n"
                    )
                    raw = None
                    try:
                        from llm_router import get_llm_router
                        resp = get_llm_router().generate(enhance_prompt)
                        raw = resp.text
                    except Exception:
                        st.warning("⚠️ Enhancement failed, using base code.")

                    if raw:
                        raw = re.sub(r'```[rR]?\n?', '', raw)
                        raw = re.sub(r'```', '', raw)
                        raw = re.sub(r'\+?\s*ggsave\s*\(.*?\)', '', raw, flags=re.DOTALL)
                        enhanced_code = raw.strip()
                        st.session_state["graph_r_code_pending"]  = enhanced_code
                        st.session_state["graph_r_code_original"] = r_code_for_enhancement
                        st.session_state["graph_r_code"]          = r_code
                        st.session_state["graph_df"]              = df
                        st.session_state["graph_preview_png"]     = None
                        if st.session_state.get("graph_png") and not st.session_state.get("graph_png_accepted"):
                            st.session_state["graph_png_accepted"] = st.session_state["graph_png"]
                        st.rerun()

                st.session_state["graph_r_code_pending"] = None
                st.session_state["graph_r_code"]         = r_code
                st.session_state["graph_df"]             = df
                st.session_state["_run_r_now"]           = True

            except Exception as e:
                st.error(f"Code generation error: {e}")
                st.stop()

    if st.session_state.get("_run_r_now") and not st.session_state.get("graph_r_code_pending"):
        st.session_state["_run_r_now"] = False
        with st.spinner("⚙️ Executing Rscript..."):
            try:
                png_bytes, r_log = execute_graph(
                    st.session_state["graph_r_code"],
                    st.session_state["graph_df"]
                )
                st.session_state["graph_png"] = png_bytes
                st.session_state["graph_png_accepted"] = png_bytes
                st.session_state["graph_log"] = r_log
                st.session_state["graph_error"] = None
            except RuntimeError as e:
                st.session_state["graph_error"] = str(e)
                st.session_state["graph_png"] = None
        st.rerun()

    if st.session_state.get("graph_r_code_pending"):
        st.warning("⚠️ AI suggests modifications to your code. Review diff and confirm:")
        show_code_diff(
            st.session_state["graph_r_code_original"],
            st.session_state["graph_r_code_pending"]
        )

        c1, c2 = st.columns(2)
        with c1:
            if st.button("✅ Apply Changes", use_container_width=True):
                st.session_state["graph_r_code"]          = st.session_state["graph_r_code_pending"]
                st.session_state["graph_r_code_original"] = None
                st.session_state["graph_r_code_pending"]  = None
                st.session_state["graph_preview_png"]     = None
                st.session_state["_run_r_now"]            = True
                st.rerun()
        with c2:
            if st.button("👁️ Preview Changes", use_container_width=True):
                with st.spinner("Generating preview..."):
                    try:
                        preview_png, _ = execute_graph(
                            st.session_state["graph_r_code_pending"],
                            st.session_state["graph_df"]
                        )
                        st.session_state["graph_preview_png"] = preview_png
                        st.rerun()
                    except RuntimeError as e:
                        st.error(f"Preview failed: {e}")


def render_clinical_graphs_tab():
    st.title("🏥 Clinical Graphs")
    st.caption("Upload data → Select clinical plot preset → Generate ggplot2 R code → Preview & Download")
    st.divider()

    if "cg_initialized" not in st.session_state:
        st.session_state["cg_r_code_pending"]  = None
        st.session_state["cg_r_code_original"] = None
        st.session_state["cg_preview_png"]     = None
        st.session_state["_cg_run_now"]        = False
        st.session_state["cg_initialized"]     = True

    for key, default in {
        "cg_df":              None,
        "cg_r_code":          "",
        "cg_png":             None,
        "cg_png_accepted":    None,
        "cg_log":             "",
        "cg_error":           None,
        "cg_r_code_pending":  None,
        "cg_r_code_original": None,
        "cg_preview_png":     None,
        "cg_custom_text":     "",
        "_cg_run_now":        False,
    }.items():
        if key not in st.session_state:
            st.session_state[key] = default

    with st.container():
        st.markdown("### 📁 Upload Input Data")
        uploaded = st.file_uploader(
            "Upload CSV or Excel file",
            type=["csv", "xlsx", "xls"],
            key="cg_upload"
        )
        df = st.session_state.get("cg_df")
        if uploaded:
            try:
                ext = os.path.splitext(uploaded.name)[1].lower()
                df = pd.read_excel(uploaded) if ext in (".xlsx", ".xls") else pd.read_csv(uploaded)
                st.session_state["cg_df"] = df
                st.success(f"✅ Data loaded successfully — {df.shape[0]} rows × {df.shape[1]} cols")
                st.dataframe(df.head(5), use_container_width=True)
            except Exception as e:
                st.error(f"Failed to load file: {e}")
                return

        with st.expander("📋 Or paste CSV text manually"):
            manual_csv = st.text_area("Paste CSV here", height=100, key="cg_manual_csv")
            if manual_csv:
                try:
                    import io
                    df = pd.read_csv(io.StringIO(manual_csv))
                    st.session_state["cg_df"] = df
                    st.success(f"✅ Data loaded — {df.shape[0]} rows × {df.shape[1]} cols")
                    st.dataframe(df.head(5), use_container_width=True)
                except Exception as e:
                    st.error(f"Parse error: {e}")

    if df is None:
        st.info("👆 Upload a CSV or Excel file or paste CSV text to configure your clinical graph.")
        return

    st.divider()

    st.markdown("### ⚙️ Configure Clinical Chart Preset")
    cols          = df.columns.tolist()
    numeric_cols  = df.select_dtypes(include="number").columns.tolist()
    all_with_none = ["None"] + cols

    r1a, r1b, r1c = st.columns([2, 1, 2])
    with r1a:
        chart_type = st.selectbox("📊 Clinical Preset", CLINICAL_CHART_TYPES, key="cg_chart_type")
    with r1b:
        theme = st.selectbox("🎨 Theme", THEMES, key="cg_theme")
    with r1c:
        title = st.text_input("📝 Title", value=chart_type, key="cg_title")

    selections = {"title": title, "theme": theme}

    if chart_type == "Kaplan-Meier Survival Curve":
        c1, c2, c3 = st.columns(3)
        with c1: selections["time_col"]  = st.selectbox("⏱️ Time Column", cols, key="cg_time")
        with c2: selections["event_col"] = st.selectbox("💀 Event Column (0/1)", cols, key="cg_event")
        with c3:
            selections["group_col"] = st.selectbox("👥 Group Column", all_with_none, key="cg_group")
            if selections["group_col"] == "None": selections["group_col"] = None

    elif chart_type == "Forest Plot (Subgroup Analysis)":
        c1, c2, c3, c4 = st.columns(4)
        with c1: selections["label_col"] = st.selectbox("🏷️ Label Column", cols, key="cg_label")
        with c2: selections["est_col"]   = st.selectbox("📍 Estimate Column", cols, key="cg_est")
        with c3:
            selections["low_col"]   = st.selectbox("⬇️ CI Lower", all_with_none, key="cg_low")
            if selections["low_col"] == "None": selections["low_col"] = None
        with c4:
            selections["high_col"]  = st.selectbox("⬆️ CI Upper", all_with_none, key="cg_high")
            if selections["high_col"] == "None": selections["high_col"] = None

    elif chart_type == "Waterfall Plot (Tumor Response)":
        c1, c2 = st.columns(2)
        with c1: selections["response_col"] = st.selectbox("📊 Response % Column", numeric_cols or cols, key="cg_response")
        with c2:
            selections["group_col"] = st.selectbox("👥 Group Column", all_with_none, key="cg_group")
            if selections["group_col"] == "None": selections["group_col"] = None

    elif chart_type in ["Box Plot by Visit (Lab Values)", "Spaghetti Plot (Patient Trajectories)", "Mean ± SD Plot by Visit"]:
        c1, c2, c3, c4 = st.columns(4)
        with c1: selections["visit_col"] = st.selectbox("📅 Visit Column", cols, key="cg_visit")
        with c2: selections["value_col"] = st.selectbox("🔢 Value Column", numeric_cols or cols, key="cg_value")
        with c3:
            selections["group_col"] = st.selectbox("👥 Group Column", all_with_none, key="cg_group")
            if selections["group_col"] == "None": selections["group_col"] = None
        with c4:
            selections["subj_col"]  = st.selectbox("🔑 Subject ID", all_with_none, key="cg_subj")
            if selections["subj_col"] == "None": selections["subj_col"] = "USUBJID"

    elif chart_type == "Dot Plot (Biomarker)":
        c1, c2 = st.columns(2)
        with c1: selections["value_col"] = st.selectbox("🔢 Value Column", numeric_cols or cols, key="cg_value")
        with c2:
            selections["group_col"] = st.selectbox("👥 Group Column", all_with_none, key="cg_group")
            if selections["group_col"] == "None": selections["group_col"] = None

    elif chart_type == "Swimmer Plot (Patient Timeline)":
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1: selections["subj_col"]   = st.selectbox("🔑 Subject ID", cols, key="cg_subj")
        with c2: selections["start_col"]  = st.selectbox("▶️ Start", cols, key="cg_start")
        with c3: selections["end_col"]    = st.selectbox("⏹️ End", cols, key="cg_end")
        with c4:
            selections["group_col"]  = st.selectbox("👥 Group", all_with_none, key="cg_group")
            if selections["group_col"] == "None": selections["group_col"] = None
        with c5:
            selections["event2_col"] = st.selectbox("💊 Event Marker", all_with_none, key="cg_event2")
            if selections["event2_col"] == "None": selections["event2_col"] = None

    st.divider()

    if st.session_state.get("cg_r_code"):
        st.markdown("### 📤 Output Preview & Code")
        out1, out2 = st.tabs(["📊 Rendered Clinical Graph", "💻 Editable R Code"])

        with out1:
            img = st.session_state.get("cg_png_accepted") or st.session_state.get("cg_png")
            if img:
                st.image(img, use_container_width=True)
                st.download_button(
                    "⬇️ Download Graph PNG", data=img,
                    file_name="clinical_graph.png", mime="image/png"
                )
            elif st.session_state.get("cg_error"):
                st.error(st.session_state["cg_error"])

        with out2:
            edited = st.text_area(
                "Edit R Code",
                value=st.session_state.get("cg_r_code", ""),
                height=280,
                key=f"cg_edited_{hash(st.session_state.get('cg_r_code', ''))}"
            )
            b1, b2 = st.columns(2)
            with b1:
                run_edit = st.button("▶️ Run Edited Code", type="primary", use_container_width=True, key="cg_run_edit")
            with b2:
                st.download_button(
                    "⬇️ Download .R Script", data=edited,
                    file_name="clinical_graph.R", mime="text/plain",
                    use_container_width=True
                )
            if run_edit:
                with st.spinner("Executing updated script..."):
                    try:
                        png, log = execute_clinical_graph(edited, st.session_state["cg_df"])
                        st.session_state["cg_png"]          = png
                        st.session_state["cg_png_accepted"] = png
                        st.session_state["cg_log"]          = log
                        st.session_state["cg_r_code"]       = edited
                        st.session_state["cg_error"]        = None
                        st.rerun()
                    except RuntimeError as e:
                        st.error(str(e))

            if st.session_state.get("cg_log"):
                with st.expander("📋 R Console Log"):
                    st.code(st.session_state["cg_log"], language="bash")

    custom_request = st.text_area(
        "✨ AI Custom Enhancement Prompt (optional)",
        placeholder="e.g. Add confidence interval, change color palette, add risk table...",
        height=80,
        key="cg_custom_text",
    )

    def clear_clinical_graph():
        for key in ["cg_df", "cg_r_code", "cg_png", "cg_png_accepted",
                    "cg_log", "cg_error", "cg_preview_png",
                    "cg_r_code_pending", "cg_r_code_original"]:
            st.session_state[key] = None
        st.session_state["cg_r_code"] = ""

    btn1, btn2 = st.columns([4, 1])
    with btn1:
        generate_cg = st.button("🏥 Generate Clinical Graph", type="primary", use_container_width=True)
    with btn2:
        st.button("🗑️ Clear Workspace", on_click=clear_clinical_graph, use_container_width=True, key="cg_clear")

    if generate_cg:
        with st.spinner("🤖 Generating R code..."):
            try:
                r_code = generate_clinical_code(chart_type, selections)
                existing = st.session_state.get("cg_r_code", "")
                r_code_for_enhancement = existing if existing.strip() else r_code

                if custom_request.strip():
                    enhance_prompt = (
                        f"You are a ggplot2 clinical graph code editor. Apply ONLY the requested change.\n\n"
                        f"EXISTING CODE:\n```r\n{r_code_for_enhancement}\n```\n\n"
                        f"REQUEST: {custom_request}\n\n"
                        f"RULES:\n"
                        f"- Touch ONLY what the request asks. Preserve everything else exactly.\n"
                        f"- Return ONLY complete R code. No explanations, no markdown fences.\n"
                    )
                    raw = None
                    try:
                        from llm_router import get_llm_router
                        resp = get_llm_router().generate(enhance_prompt)
                        raw = resp.text
                    except Exception:
                        st.warning("⚠️ Enhancement failed, using base code.")

                    if raw:
                        raw = re.sub(r'```[rR]?\n?', '', raw)
                        raw = re.sub(r'```', '', raw)
                        enhanced_code = raw.strip()
                        st.session_state["cg_r_code_pending"]  = enhanced_code
                        st.session_state["cg_r_code_original"] = r_code_for_enhancement
                        st.session_state["cg_r_code"]          = r_code
                        st.session_state["cg_df"]              = df
                        st.session_state["cg_preview_png"]     = None
                        if st.session_state.get("cg_png") and not st.session_state.get("cg_png_accepted"):
                            st.session_state["cg_png_accepted"] = st.session_state["cg_png"]
                        st.rerun()

                st.session_state["cg_r_code_pending"] = None
                st.session_state["cg_r_code"]         = r_code
                st.session_state["cg_df"]             = df
                st.session_state["_cg_run_now"]        = True

            except Exception as e:
                st.error(f"Code generation error: {e}")
                st.stop()

    if st.session_state.get("_cg_run_now") and not st.session_state.get("cg_r_code_pending"):
        st.session_state["_cg_run_now"] = False
        with st.spinner("⚙️ Executing Rscript..."):
            try:
                png, log = execute_clinical_graph(
                    st.session_state["cg_r_code"],
                    st.session_state["cg_df"]
                )
                st.session_state["cg_png"]          = png
                st.session_state["cg_png_accepted"] = png
                st.session_state["cg_log"]          = log
                st.session_state["cg_error"]        = None
            except RuntimeError as e:
                st.session_state["cg_error"] = str(e)
                st.session_state["cg_png"]   = None
        st.rerun()
