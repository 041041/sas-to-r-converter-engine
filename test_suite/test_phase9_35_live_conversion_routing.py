"""
test_suite/test_phase9_35_live_conversion_routing.py
──────────────────────────────────────────────────────
Phase 9.35 Regression Test:
Verifies that HybridMacroConverter properly prioritizes high-confidence
rule-based conversion over LLM fallback even when LLM clients (groq_client/gemini_client)
are initialized in live deployment environments.
"""

import os
import subprocess
import tempfile
import pytest

from macro_converter import parse_sas_source, HybridMacroConverter


def load_clinical_sources():
    sas1_path = "/Users/sandeep/Downloads/test1macro.sas"
    sas2_path = "/Users/sandeep/Downloads/test2macro.sas"
    sas3_path = "/Users/sandeep/Downloads/test3macro.sas"

    if os.path.exists(sas1_path) and os.path.exists(sas2_path) and os.path.exists(sas3_path):
        with open(sas1_path, "r", encoding="utf-8") as f:
            s1 = f.read()
        with open(sas2_path, "r", encoding="utf-8") as f:
            s2 = f.read()
        with open(sas3_path, "r", encoding="utf-8") as f:
            s3 = f.read()
        return s3 + "\n\n" + s2 + "\n\n" + s1

    # Fallback to fixture files if Downloads directory files are unavailable
    fixture_dir = os.path.join(os.path.dirname(__file__), "fixtures", "clinical_project_e2e")
    texts = []
    for fname in ["util_chkvars.sas", "util_num_periods.sas", "gen_tp_join_adsl.sas"]:
        fpath = os.path.join(fixture_dir, fname)
        if os.path.exists(fpath):
            with open(fpath, "r", encoding="utf-8") as f:
                texts.append(f.read())
    return "\n\n".join(texts)


def test_live_deployment_llm_client_routing():
    """
    Simulates live deployment mode where groq_client and gemini_client are initialized.
    Verifies that clinical macros (UTIL_CHKVARS, UTIL_NUM_PERIODS, GEN_TP_JOIN_ADSL)
    are routed to 95% confidence rule-based conversion rather than failing via LLM fallback.
    """
    combined_sas = load_clinical_sources()
    parsed = parse_sas_source(combined_sas)

    # Initialize converter with non-None clients (simulating live deployment)
    converter = HybridMacroConverter(groq_client="live_groq_client", gemini_client="live_gemini_client")
    res = converter.convert_all(parsed["macro_definitions"], parsed["macro_calls"], "Modern R (dplyr)")

    r_functions = res.get("r_functions", "")

    # 1. No "Could not convert macro" error messages
    assert "Could not convert macro" not in r_functions

    # 2. Rule-based method header with 95% confidence
    assert "Method: rule-based" in r_functions
    assert "Confidence: 95%" in r_functions

    # 3. All 3 macro functions defined
    assert "util_chkvars <- function" in r_functions
    assert "util_num_periods <- function" in r_functions
    assert "gen_tp_join_adsl <- function" in r_functions

    # 4. R syntax validation
    with tempfile.NamedTemporaryFile(suffix=".R", mode="w", delete=False) as f:
        f.write(r_functions)
        fpath = f.name

    try:
        proc = subprocess.run(
            ["Rscript", "-e", f"parse('{fpath}')"],
            capture_output=True,
            text=True
        )
        assert proc.returncode == 0, f"Rscript parse error: {proc.stderr}"
    finally:
        if os.path.exists(fpath):
            os.remove(fpath)
