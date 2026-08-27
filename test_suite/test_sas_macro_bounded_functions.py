"""
test_sas_macro_bounded_functions.py
──────────────────────────────────
Unit test suite for Phase 8.21 — Bounded SAS Macro String Functions & Date SYSFUNC.
"""

import pytest
from macro_processor import SASMacroProcessor, expand_sas_macros
from sas_step_converter import SASStepConverter


def test_1_sysfunc_today():
    sas_code = """
    %let run_date=%sysfunc(today());
    data ADSL;
        set DM;
    run;
    """
    proc = SASMacroProcessor()
    code, warnings, _ = proc.process(sas_code)
    assert proc.let_vars.get("RUN_DATE") == "Sys.Date()"


def test_2_sysfunc_date():
    sas_code = """
    %let run_date=%sysfunc(date());
    data ADSL;
        set DM;
    run;
    """
    proc = SASMacroProcessor()
    code, warnings, _ = proc.process(sas_code)
    assert proc.let_vars.get("RUN_DATE") == "Sys.Date()"


def test_3_unsupported_sysfunc_mean_safe_reject():
    sas_code = """
    %let avg=%sysfunc(mean(10, 20));
    data ADSL;
        set DM;
    run;
    """
    proc = SASMacroProcessor()
    code, warnings, _ = proc.process(sas_code)
    assert any("unsupported" in w.lower() for w in warnings)
    assert proc.let_vars.get("AVG") == "%sysfunc(mean(10, 20))"


def test_4_substr_static():
    sas_code = """
    %let prefix=%substr(ADSL, 1, 2);
    """
    proc = SASMacroProcessor()
    proc.process(sas_code)
    assert proc.let_vars.get("PREFIX") == "AD"


def test_5_substr_with_macro_variable():
    sas_code = """
    %let ds=ADSL;
    %let prefix=%substr(&ds, 1, 2);
    """
    proc = SASMacroProcessor()
    proc.process(sas_code)
    assert proc.let_vars.get("PREFIX") == "AD"


def test_6_substr_invalid_dynamic_safe_reject():
    sas_code = """
    %let ds=ADSL;
    %let prefix=%substr(&ds, &start, 2);
    """
    proc = SASMacroProcessor()
    code, warnings, _ = proc.process(sas_code)
    assert any("unsupported" in w.lower() for w in warnings)


def test_7_scan_static():
    sas_code = """
    %let part=%scan(STUDY_ADSL_FINAL, 2, %str(_));
    """
    proc = SASMacroProcessor()
    proc.process(sas_code)
    assert proc.let_vars.get("PART") == "ADSL"


def test_8_scan_with_macro_variable():
    sas_code = """
    %let name=STUDY_ADSL_FINAL;
    %let part=%scan(&name, 2, %str(_));
    """
    proc = SASMacroProcessor()
    proc.process(sas_code)
    assert proc.let_vars.get("PART") == "ADSL"


def test_9_index_found():
    sas_code = """
    %let pos=%index(SAFETY_AE, AE);
    """
    proc = SASMacroProcessor()
    proc.process(sas_code)
    assert proc.let_vars.get("POS") == "8"


def test_10_index_not_found():
    sas_code = """
    %let pos=%index(SAFETY_AE, XYZ);
    """
    proc = SASMacroProcessor()
    proc.process(sas_code)
    assert proc.let_vars.get("POS") == "0"


def test_11_length():
    sas_code = """
    %let len=%length(ADSL);
    """
    proc = SASMacroProcessor()
    proc.process(sas_code)
    assert proc.let_vars.get("LEN") == "4"


def test_12_nested_deterministic_functions():
    sas_code = """
    %let ds=STUDY_ADSL;
    %let prefix=%substr(%scan(&ds, 2, %str(_)), 1, 2);
    """
    proc = SASMacroProcessor()
    proc.process(sas_code)
    assert proc.let_vars.get("PREFIX") == "AD"


def test_13_indirect_reference_safe_reject():
    sas_code = """
    %let name1=DM;
    %let i=1;
    %let val=&&name&i;
    """
    proc = SASMacroProcessor()
    code, warnings, _ = proc.process(sas_code)
    assert any("indirect" in w.lower() for w in warnings)


def test_14_eval_inside_bounded_function_safe_reject():
    sas_code = """
    %let res=%length(%eval(1 + 2));
    """
    proc = SASMacroProcessor()
    code, warnings, _ = proc.process(sas_code)
    assert any("unsupported" in w.lower() for w in warnings)


def test_15_sysevalf_safe_reject():
    sas_code = """
    %let res=%sysevalf(1.5 + 2.5);
    """
    proc = SASMacroProcessor()
    code, warnings, _ = proc.process(sas_code)
    assert any("unsupported" in w.lower() for w in warnings)


def test_16_macro_quoting_functions_safe_reject():
    sas_code = """
    %let res=%nrstr(%let a=b;);
    """
    proc = SASMacroProcessor()
    code, warnings, _ = proc.process(sas_code)
    assert any("unsupported" in w.lower() for w in warnings)


def test_17_runtime_dependent_sysfunc_safe_reject():
    sas_code = """
    %let handle=%sysfunc(open(work.adsl));
    """
    proc = SASMacroProcessor()
    code, warnings, _ = proc.process(sas_code)
    assert any("unsupported" in w.lower() for w in warnings)


def test_18_reference_test_case():
    sas_code = """
    %let ds=STUDY_ADSL_FINAL;
    %let prefix=%substr(&ds, 7, 4);
    %let part=%scan(&ds, 2, %str(_));
    %let pos=%index(&ds, ADSL);
    %let len=%length(&ds);
    """
    proc = SASMacroProcessor()
    proc.process(sas_code)
    assert proc.let_vars.get("PREFIX") == "ADSL"
    assert proc.let_vars.get("PART") == "ADSL"
    assert proc.let_vars.get("POS") == "7"
    assert proc.let_vars.get("LEN") == "16"


def test_19_five_level_nested_deterministic_functions():
    sas_code = """
    %let ds=PREFIX_STUDY_ADSL_FINAL_SUBSET;
    %let res=%substr(%scan(%substr(%scan(%length(&ds), 1), 1, 2), 1), 1, 1);
    """
    proc = SASMacroProcessor()
    proc.process(sas_code)
    assert proc.let_vars.get("RES") == "3"


def test_20_five_level_string_nesting():
    sas_code = """
    %let raw=CLINICAL_STUDY_ADSL_SAFETY_FINAL;
    %let res=%substr(%scan(%substr(%scan(%substr(&raw, 10, 15), 1, %str(_)), 1, 4), 1, %str(_)), 1, 2);
    """
    proc = SASMacroProcessor()
    proc.process(sas_code)
    assert proc.let_vars.get("RES") == "ST"


def test_21_six_level_nested_functions():
    sas_code = """
    %let text=CLINICAL_STUDY_ADSL_SAFETY_FINAL;
    %let res=%length(%substr(%scan(%substr(%scan(%substr(&text, 1, 20), 2, %str(_)), 1, 4), 1, %str(_)), 1, 2));
    """
    proc = SASMacroProcessor()
    proc.process(sas_code)
    assert proc.let_vars.get("RES") == "2"


def test_22_nested_scan_substr_combination():
    sas_code = """
    %let text=PROJECT_ADSL_V01;
    %let res=%substr(%scan(&text, 2, %str(_)), 1, 4);
    """
    proc = SASMacroProcessor()
    proc.process(sas_code)
    assert proc.let_vars.get("RES") == "ADSL"


def test_23_nested_index_length_combination():
    sas_code = """
    %let text=PHASE3_ADSL_DATA;
    %let res=%index(%substr(&text, 1, %length(&text)), ADSL);
    """
    proc = SASMacroProcessor()
    proc.process(sas_code)
    assert proc.let_vars.get("RES") == "8"


def test_24_malformed_nested_expression_safe_reject():
    sas_code = """
    %let text=PHASE3_ADSL_DATA;
    %let res=%substr(%scan(&text, 2, %str(_)), 1, &invalid_var);
    """
    proc = SASMacroProcessor()
    code, warnings, _ = proc.process(sas_code)
    assert any("unsupported" in w.lower() for w in warnings)
