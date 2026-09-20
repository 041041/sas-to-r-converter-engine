"""
test_suite/test_phase9_25_runtime_macro_dataflow.py
────────────────────────────────────────────────────
Phase 9.25 Regression Test Suite:
- Runtime macro variable preservation (no empty string deletion)
- SQL INTO to downstream dataflow (G_PRDCNT > 0)
- Identifier sanitization (leading underscores stripped)
- Removal of spurious RESULT output lines
- Rscript parse validation integration
"""

import pytest
from rule_engine import RuleEngine
from sas_step_converter import SASStepConverter
from doc_generator import validate_generated_r_code


@pytest.fixture
def step_converter():
    return SASStepConverter()


@pytest.fixture
def rule_engine():
    return RuleEngine()


def test_runtime_macro_variable_preservation(step_converter):
    sas_code = """
    proc sql noprint;
        select count(distinct name) into :G_PRDCNT from ALLVARS;
    quit;
    data ADSL;
        set ADSL;
        if &G_PRDCNT > 0 then HAS_PERIOD_FL = "Y";
    run;
    """
    res = step_converter.convert_program(sas_code)
    r_code = res.full_optimized_r or res.full_initial_r

    assert "case_when(> 0" not in r_code
    assert "1 > 0" in r_code or "G_PRDCNT > 0" in r_code
    assert "RESULT" not in r_code.splitlines()


def test_select_into_leading_underscore_sanitization(rule_engine):
    sas_code = "proc sql noprint; select 'Y' into :_trt_time from ALLVARS; quit;"
    r_code, confidence, rule_name = rule_engine.translate_step(
        type("Step", (), {"source_code": sas_code, "step_type": "PROC_SQL"})()
    )
    assert r_code is not None
    assert "trt_time <-" in r_code
    assert "_trt_time <-" not in r_code
    assert "RESULT" not in r_code.splitlines()


def test_select_name_into_leading_underscore_sanitization(rule_engine):
    sas_code = "proc sql noprint; select name into :_anal_time from ALLVARS; quit;"
    r_code, confidence, rule_name = rule_engine.translate_step(
        type("Step", (), {"source_code": sas_code, "step_type": "PROC_SQL"})()
    )
    assert r_code is not None
    assert "anal_time <-" in r_code
    assert "_anal_time <-" not in r_code


def test_statically_known_let_variable(step_converter):
    sas_code = """
    %let known = 5;
    data ADSL;
        set ADSL;
        if &known > 0 then FLAG = "Y";
    run;
    """
    res = step_converter.convert_program(sas_code)
    r_code = res.full_optimized_r or res.full_initial_r

    assert "5 > 0" in r_code


def test_no_standalone_result_lines(step_converter):
    sas_code = """
    proc sql noprint;
        select count(*) into :n_obs from ADSL;
    quit;
    """
    res = step_converter.convert_program(sas_code)
    r_code = res.full_optimized_r or res.full_initial_r

    lines = [line.strip() for line in r_code.splitlines()]
    assert "RESULT" not in lines


def test_rscript_parse_validation_valid():
    r_code = """
    G_PRDCNT <- ALLVARS %>%
      dplyr::filter(grepl("^TR..SDT$", toupper(name))) %>%
      dplyr::pull(1)

    ADSL_TP <- ADSL %>%
      dplyr::mutate(
        HAS_PERIOD_FL = dplyr::case_when(G_PRDCNT > 0 ~ "Y")
      )
    """
    status, issues = validate_generated_r_code(r_code)
    assert status in ("VALID_R_SYNTAX", "VALID_R")
    assert len(issues) == 0


def test_rscript_parse_validation_invalid():
    r_code = "HAS_PERIOD_FL = case_when(> 0 ~ 'Y')"
    status, issues = validate_generated_r_code(r_code)
    assert status == "INVALID_R_SYNTAX"
    assert len(issues) > 0


def test_select_string_literal_into(rule_engine):
    sas_code = "proc sql noprint; select 'Y' into :x from ALLVARS; quit;"
    r_code, _, _ = rule_engine.translate_step(
        type("Step", (), {"source_code": sas_code, "step_type": "PROC_SQL"})()
    )
    assert "dplyr::select('Y')" not in r_code
    assert "transmute(val = 'Y')" in r_code or "transmute(val = \"Y\")" in r_code


def test_select_string_literal_n_into(rule_engine):
    sas_code = "proc sql noprint; select 'N' into :flag from ALLVARS; quit;"
    r_code, _, _ = rule_engine.translate_step(
        type("Step", (), {"source_code": sas_code, "step_type": "PROC_SQL"})()
    )
    assert "dplyr::select('N')" not in r_code
    assert "transmute(val = 'N')" in r_code or "transmute(val = \"N\")" in r_code


def test_select_numeric_literal_into(rule_engine):
    sas_code = "proc sql noprint; select 123 into :n from ALLVARS; quit;"
    r_code, _, _ = rule_engine.translate_step(
        type("Step", (), {"source_code": sas_code, "step_type": "PROC_SQL"})()
    )
    assert "dplyr::select(123)" not in r_code
    assert "transmute(val = 123)" in r_code


def test_select_column_name_into(rule_engine):
    sas_code = "proc sql noprint; select name into :x from ALLVARS; quit;"
    r_code, _, _ = rule_engine.translate_step(
        type("Step", (), {"source_code": sas_code, "step_type": "PROC_SQL"})()
    )
    assert "dplyr::select(name)" in r_code

