# FORENSIC REPORT — REAL GEMINI 429 ROOT CAUSE ANALYSIS

**Date**: 2026-08-20  
**Target Workspace**: `/Users/sandeep/.gemini/antigravity/scratch/sas-to-r-converter-cleaned`  
**Master Original**: `/Users/sandeep/.gemini/antigravity/scratch/sas-to-r-converter` (**READ-ONLY / UNTOUCHED**)

---

## 🎯 ANSWER TO THE CORE FORENSIC QUESTION

> **"WHO is calling `gemini-2.5-flash`, FROM WHICH FILE, ON WHICH GIT COMMIT, AND WHY?"**

### 1. WHO is calling `gemini-2.5-flash`?
`safe_generate_gemini_content()` inside **`llm_helper.py`**.

### 2. FROM WHICH FILE & LINE?
- **`llm_helper.py`**:
  - Line 10: `GEMINI_MODELS = ["gemini-2.5-flash", "gemini-1.5-flash", ...]`
  - Line 28: `res = client.models.generate_content(model=model, contents=contents)`
- **`app.py`**:
  - Line 317: `from llm_helper import safe_generate_gemini_content, safe_generate_groq_content`
  - Line 325-326:
    ```python
    try:
        raw = safe_generate_groq_content(groq_client, prompt)
    except Exception:
        res = safe_generate_gemini_content(gemini_client, prompt)
    ```
  - Lines 428, 442, 552: Direct `safe_generate_gemini_content(gemini_client, fix_prompt)` calls for auto-fix repair.

### 3. ON WHICH GIT COMMIT & BRANCH?
- **Deployed GitHub Commit**: `503cdd0ec305a66947f50fe2669b5e5bc78be534` on branch **`main`** of repository `https://github.com/041041/sas-to-r-converter-engine.git`.
- **Local Development Branch**: `phase4-groq-primary` (Commit `02d16f645...`).

### 4. WHY is it happening at runtime on Streamlit Cloud?
1. **Deployment Mismatch**: Streamlit Cloud deploys from GitHub `origin/main` (`503cdd0`). On `origin/main`, `llm_helper.py` and the hardcoded Gemini fallback in `app.py` are active.
2. **Local Isolation**: Our Phase 6 Groq-only architecture (`llm_router.py`, `llm_provider.py`, updated `app.py`) was implemented locally on branch `phase4-groq-primary` and **has NEVER been merged to `main` or pushed to GitHub `origin/main`**.
3. **Groq Key / Client Failure on Streamlit Cloud**: On Streamlit Cloud, `safe_generate_groq_content` fails (due to missing/unconfigured `GROQ_API_KEY` in Streamlit Cloud Secrets), triggering the fallback block `safe_generate_gemini_content(gemini_client, prompt)`. This attempts to call `gemini-2.5-flash` via the Google GenAI SDK, hitting the Google Free Tier quota and throwing `429 RESOURCE_EXHAUSTED`.

---

## 📊 GIT IDENTITY & BRANCH COMPARISON MATRIX

| Attribute | Local Cleaned Workspace | GitHub Remote Repository |
| :--- | :--- | :--- |
| **Branch** | `phase4-groq-primary` | `main` (Default branch deployed by Streamlit) |
| **Commit Hash** | `02d16f6459a7215b1712583faf64114823e18878` | `503cdd0ec305a66947f50fe2669b5e5bc78be534` |
| **Contains `llm_helper.py`?** | **NO** (Replaced by `llm_router.py` & `llm_provider.py`) | **YES** (Legacy file calling `gemini-2.5-flash`) |
| **`app.py` Routing** | `LLMRouter` (Groq-Only, 0 Gemini calls) | `safe_generate_gemini_content` fallback |
| **Gemini Network Calls** | **0** (Proven via monkeypatch test) | **Active** (Hits Google Free Tier 429) |

---

## 🧪 LOCAL INSTRUMENTATION & TESTING RESULTS

| Scenario | Local Test Result | Gemini SDK Calls | Groq Provider Used |
| :--- | :--- | :--- | :--- |
| **Groq Success** | `RESULT <- ORDERS` | **0** | `Groq` (`llama-3.3-70b-versatile`) |
| **Groq Failure** | `RuntimeError("GROQ conversion failed...")` | **0** | `None` (Zero fallback to Gemini) |
| **Streamlit Import (`GEMINI_API_KEY` absent)** | PASS (`gemini_client = None`) | **0** | `None` |

---

## 💡 RECOMMENDED MINIMAL FIX (Awaiting User Action)

To stop Gemini `429 RESOURCE_EXHAUSTED` on the live Streamlit Cloud application:

1. **Configure `GROQ_API_KEY` in Streamlit Cloud Secrets**:
   Go to **Streamlit Cloud Dashboard** $\rightarrow$ **App Settings** $\rightarrow$ **Secrets**, and paste:
   ```toml
   GROQ_API_KEY = "gsk_your_actual_groq_key_here"
   LLM_PRIMARY_PROVIDER = "groq"
   DISABLE_GEMINI = "true"
   ```
2. **Merge & Push Phase 6 Branch to GitHub `main`**:
   Once approved by the user, merge the local `phase4-groq-primary` branch into `main` and push to `https://github.com/041041/sas-to-r-converter-engine.git`. This will update the code deployed on Streamlit Cloud to our Groq-Only Phase 6 architecture (`llm_router.py` & `llm_provider.py`) and eliminate `llm_helper.py`.
