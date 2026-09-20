"""
test_suite/test_phase9_24_clinical_macro_project_dataflow.py
─────────────────────────────────────────────────────────────
Phase 9.24 Regression Test Suite for Clinical Macro Project Dataflow:
- Project Macro Dataflow & extra_files propagation
- SELECT ... INTO :macrovar scalar & vector formatting
- PROC DATASETS statement conversion
- Full Real Clinical Macro Chain (gen_tp_join_adsl -> util_num_periods -> util_chkvars)
"""

import pytest
from rule_engine import RuleEngine
from sas_step_converter import SASStepConverter
from project_engine.analyzer import ProjectAnalyzer
from doc_generator import validate_generated_r_code


@pytest.fixture
def rule_engine():
    return RuleEngine()


@pytest.fixture
def step_converter():
    return SASStepConverter()


# ─────────────────────────────────────────────────────────────────
# 1. SELECT INTO REGRESSION TESTS
# ─────────────────────────────────────────────────────────────────

def test_select_literal_into(rule_engine):
    sas_code = "proc sql noprint; select 'Y' into :_trt_time from ALLVARS where upcase(name) like 'TR__STM'; quit;"
    r_code, confidence, rule_name = rule_engine.translate_step(
        type("Step", (), {"source_code": sas_code, "step_type": "PROC_SQL"})()
    )
    assert r_code is not None
    assert "into :" not in r_code
    assert "trt_time <- ALLVARS" in r_code
    assert "dplyr::pull(1)" in r_code
    assert 'grepl("^TR..STM$", toupper(name))' in r_code


def test_select_column_into(rule_engine):
    sas_code = "proc sql noprint; select name into :first_var from ALLVARS; quit;"
    r_code, confidence, rule_name = rule_engine.translate_step(
        type("Step", (), {"source_code": sas_code, "step_type": "PROC_SQL"})()
    )
    assert r_code is not None
    assert "into :" not in r_code
    assert "first_var <- ALLVARS %>%" in r_code
    assert "dplyr::pull(1)" in r_code


def test_select_count_into(rule_engine):
    sas_code = "proc sql noprint; select count(*) into :n_obs from ADSL; quit;"
    r_code, confidence, rule_name = rule_engine.translate_step(
        type("Step", (), {"source_code": sas_code, "step_type": "PROC_SQL"})()
    )
    assert r_code is not None
    assert "into :" not in r_code
    assert "n_obs <- ADSL %>%" in r_code
    assert "dplyr::pull(1)" in r_code


def test_select_distinct_into(rule_engine):
    sas_code = "proc sql noprint; select count(distinct name) into :G_PRDCNT from ALLVARS where upcase(name) like 'TR__SDT'; quit;"
    r_code, confidence, rule_name = rule_engine.translate_step(
        type("Step", (), {"source_code": sas_code, "step_type": "PROC_SQL"})()
    )
    assert r_code is not None
    assert "into :" not in r_code
    assert "G_PRDCNT <- ALLVARS %>%" in r_code
    assert "dplyr::pull(1)" in r_code


def test_select_into_separated_by(rule_engine):
    sas_code = "proc sql noprint; select name into :varlist separated by ' ' from ALLVARS; quit;"
    r_code, confidence, rule_name = rule_engine.translate_step(
        type("Step", (), {"source_code": sas_code, "step_type": "PROC_SQL"})()
    )
    assert r_code is not None
    assert "into :" not in r_code
    assert "varlist <- ALLVARS %>%" in r_code
    assert "paste(collapse = ' ')" in r_code


# ─────────────────────────────────────────────────────────────────
# 2. PROC DATASETS REGRESSION TESTS
# ─────────────────────────────────────────────────────────────────

def test_proc_datasets_kill(rule_engine):
    sas_code = "proc datasets lib=work kill; run;"
    r_code, confidence, rule_name = rule_engine.translate_step(
        type("Step", (), {"source_code": sas_code, "step_type": "PROC_DATASETS"})()
    )
    assert r_code is not None
    assert "Rule_ProcDatasets" in rule_name
    assert "rm(list = ls(envir = .GlobalEnv))" in r_code


def test_proc_datasets_delete(rule_engine):
    sas_code = "proc datasets lib=work; delete TEMP_DS1 TEMP_DS2; run;"
    r_code, confidence, rule_name = rule_engine.translate_step(
        type("Step", (), {"source_code": sas_code, "step_type": "PROC_DATASETS"})()
    )
    assert r_code is not None
    assert "Rule_ProcDatasets" in rule_name
    assert "rm(TEMP_DS1, TEMP_DS2, errors = FALSE)" in r_code


# ─────────────────────────────────────────────────────────────────
# 3. REAL CLINICAL MACRO PROJECT E2E DATAFLOW TEST
# ─────────────────────────────────────────────────────────────────

def test_real_clinical_macro_project_e2e(step_converter):
    file3_code = """
    %macro util_chkvars(ds=WORK.ADSL, varlist=USUBJID TRT01P);
        %local dsid vnum i var_item;
        %let dsid = %sysfunc(open(&ds));
        %do i = 1 %to %sysfunc(countw(&varlist));
            %let var_item = %scan(&varlist, &i);
            %let vnum = %sysfunc(varnum(&dsid, &var_item));
            %if &vnum = 0 %then %put WARNING: Variable &var_item missing in &ds;
        %end;
        %let rc = %sysfunc(close(&dsid));
    %mend util_chkvars;
    """

    file2_code = """
    %macro util_num_periods(in_ds=WORK.ADSL);
        %global G_PRDCNT;
        proc contents data=&in_ds out=WORK.ALLVARS noprint; run;
        proc sql noprint;
            select count(distinct name) into :G_PRDCNT from ALLVARS where upcase(name) like 'TR__SDT';
        quit;
    %mend util_num_periods;
    """

    file1_code = """
    %macro gen_tp_join_adsl(in_ds=WORK.ADSL, out_ds=WORK.ADSL_TP);
        %global _trt_time G_PRDCNT;
        %util_chkvars(ds=&in_ds, varlist=USUBJID TRT01P TRT01SDT);
        %util_num_periods(in_ds=&in_ds);
        proc sql noprint;
            select 'Y' into :_trt_time from ALLVARS where upcase(name) like 'TR__STM';
        quit;
        data &out_ds;
            set &in_ds;
            %do _i = 1 %to &G_PRDCNT;
                %let num = %sysfunc(putn(&_i, z2.));
                AP&num.SDT = TRT&num.SDT;
            %end;
            if &G_PRDCNT > 0 then HAS_PERIOD_FL = "Y";
        run;
    %mend gen_tp_join_adsl;

    %gen_tp_join_adsl(in_ds=WORK.ADSL, out_ds=WORK.ADSL_TP);
    """

    extra_files = [file3_code, file2_code]

    res = step_converter.convert_program(file1_code, extra_files=extra_files)
    r_code = res.full_optimized_r or res.full_initial_r

    # Structural & Quality Checks
    assert "into :" not in r_code, "Unstripped into :"
    assert "like '" not in r_code.lower(), "Unconverted SQL LIKE"
    assert "manual review required for step: proc contents" not in r_code.lower(), "Unconverted PROC CONTENTS"
    assert "%sysfunc" not in r_code.lower(), "Unexpanded %SYSFUNC"
    assert "&_analstarttmvar" not in r_code, "Unresolved macro variable"
    assert "AP01SDT = TRT01SDT" in r_code or "AP01SDT" in r_code, "Dynamic variable expansion"

    # Validation check
    val_status, issues = validate_generated_r_code(r_code)
    assert val_status == "VALID_R"
    assert len(issues) == 0
