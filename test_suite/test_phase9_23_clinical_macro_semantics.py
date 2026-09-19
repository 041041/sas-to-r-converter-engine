"""
test_suite/test_phase9_23_clinical_macro_semantics.py
───────────────────────────────────────────────────────
Regression tests for Phase 9.23: Clinical Macro Semantic Conversion.
Covers PROC CONTENTS, SELECT INTO :macro_variable, SQL LIKE wildcards,
and DatasetSchemaRegistry (%sysfunc open/varnum/close).
"""

import pytest
from rule_engine import RuleEngine
from macro_processor import SASMacroProcessor
from project_engine.schema_registry import DatasetSchemaRegistry
from sas_ast import ProgramStep

def test_1_proc_contents_rule():
    re_engine = RuleEngine()
    step = ProgramStep(step_index=1, step_type="PROC_STEP", name="PROC CONTENTS", source_code="proc contents data=WORK.ADSL out=WORK.ALLVARS noprint; run;")
    r_code, conf, rule_name = re_engine.translate_step(step)
    assert r_code is not None
    assert rule_name == "Rule_ProcContents"
    assert "ALLVARS <- tibble::tibble(" in r_code
    assert "name = names(ADSL)" in r_code
    assert "TODO" not in r_code

def test_2_proc_contents_metadata_fields():
    re_engine = RuleEngine()
    step = ProgramStep(step_index=1, step_type="PROC_STEP", name="PROC CONTENTS", source_code="proc contents data=SDTM.DM out=META_DM; run;")
    r_code, _, _ = re_engine.translate_step(step)
    assert "META_DM <- tibble::tibble(" in r_code
    assert "name = names(DM)" in r_code

def test_3_select_into_scalar():
    re_engine = RuleEngine()
    step = ProgramStep(step_index=1, step_type="PROC_STEP", name="PROC SQL", source_code="proc sql; select 'Y' into :_trt_time from ALLVARS; quit;")
    r_code, _, rule = re_engine.translate_step(step)
    assert r_code is not None
    assert rule == "Rule_ProcSQL"
    assert "dplyr::select('Y' into" not in r_code
    assert "_trt_time <-" in r_code

def test_4_select_count_into():
    re_engine = RuleEngine()
    step = ProgramStep(step_index=1, step_type="PROC_STEP", name="PROC SQL", source_code="proc sql noprint; select count(*) into :N_PAT from WORK.ADSL; quit;")
    r_code, _, _ = re_engine.translate_step(step)
    assert r_code is not None
    assert "N_PAT <- ADSL" in r_code
    assert "dplyr::pull(1)" in r_code

def test_5_select_count_distinct_into():
    re_engine = RuleEngine()
    step = ProgramStep(step_index=1, step_type="PROC_STEP", name="PROC SQL", source_code="proc sql; select count(distinct USUBJID) into :N_SUBJ from ADSL; quit;")
    r_code, _, _ = re_engine.translate_step(step)
    assert r_code is not None
    assert "N_SUBJ <- ADSL" in r_code
    assert "dplyr::n_distinct(USUBJID)" in r_code
    assert "dplyr::pull(1)" in r_code

def test_6_sql_like_percent_wildcard():
    re_engine = RuleEngine()
    step = ProgramStep(step_index=1, step_type="PROC_STEP", name="PROC SQL", source_code="proc sql; create table OUT as select * from ADSL where USUBJID like 'STUDY-101-%'; quit;")
    r_code, _, _ = re_engine.translate_step(step)
    assert r_code is not None
    assert "like" not in r_code
    assert 'grepl("^STUDY\\-101\\-.*$", USUBJID)' in r_code

def test_7_sql_like_underscore_wildcard():
    re_engine = RuleEngine()
    step = ProgramStep(step_index=1, step_type="PROC_STEP", name="PROC SQL", source_code="proc sql; create table OUT as select * from ALLVARS where toupper(name) like 'TR__STM'; quit;")
    r_code, _, _ = re_engine.translate_step(step)
    assert r_code is not None
    assert "like" not in r_code
    assert 'grepl("^TR..STM$", toupper(name))' in r_code

def test_8_sql_like_with_upcase():
    re_engine = RuleEngine()
    step = ProgramStep(step_index=1, step_type="PROC_STEP", name="PROC SQL", source_code="proc sql; create table OUT as select * from ALLVARS where upcase(name) like '%SDT'; quit;")
    r_code, _, _ = re_engine.translate_step(step)
    assert r_code is not None
    assert 'grepl("^.*SDT$", toupper(name))' in r_code

def test_9_sysfunc_open():
    schema_reg = DatasetSchemaRegistry()
    schema_reg.register_schema("ADSL", ["USUBJID", "TRT01P", "AGE"])
    proc = SASMacroProcessor(schema_registry=schema_reg)
    res = proc._evaluate_bounded_macro_functions("%sysfunc(open(WORK.ADSL))")
    assert res == "1"

def test_10_sysfunc_varnum_existing_column():
    schema_reg = DatasetSchemaRegistry()
    schema_reg.register_schema("ADSL", ["USUBJID", "TRT01P", "AGE"])
    proc = SASMacroProcessor(schema_registry=schema_reg)
    h = proc.schema_registry.open("ADSL")
    vpos = proc._evaluate_bounded_macro_functions(f"%sysfunc(varnum({h}, TRT01P))")
    assert vpos == "2"

def test_11_sysfunc_varnum_missing_column():
    schema_reg = DatasetSchemaRegistry()
    schema_reg.register_schema("ADSL", ["USUBJID", "TRT01P", "AGE"])
    proc = SASMacroProcessor(schema_registry=schema_reg)
    h = proc.schema_registry.open("ADSL")
    vpos = proc._evaluate_bounded_macro_functions(f"%sysfunc(varnum({h}, MISSING_VAR))")
    assert vpos == "0"

def test_12_sysfunc_close():
    schema_reg = DatasetSchemaRegistry()
    schema_reg.register_schema("ADSL", ["USUBJID", "TRT01P"])
    proc = SASMacroProcessor(schema_registry=schema_reg)
    h = proc.schema_registry.open("ADSL")
    res = proc._evaluate_bounded_macro_functions(f"%sysfunc(close({h}))")
    assert res == "0"

def test_13_macro_loop_consuming_select_into_result():
    proc = SASMacroProcessor()
    proc._detect_sql_macro_vars("select count(*) into :G_PRDCNT from ALLVARS")
    assert proc.let_vars.get("G_PRDCNT") == "1"

def test_14_util_num_periods_scenario():
    proc = SASMacroProcessor()
    code = """
    %macro util_num_periods(in_ds=ADSL);
        proc contents data=&in_ds out=WORK.ALLVARS noprint; run;
        proc sql noprint;
            select count(distinct name) into :G_PRDCNT from ALLVARS where upcase(name) like 'TR__SDT';
        quit;
    %mend util_num_periods;
    """
    expanded = proc.process(code)
    assert "into :" not in expanded or "G_PRDCNT" in proc.let_vars

def test_15_util_chkvars_scenario():
    proc = SASMacroProcessor()
    code = """
    %macro util_chkvars(ds=WORK.ADSL, varlist=USUBJID TRT01P);
        %local dsid vnum;
        %let dsid = %sysfunc(open(&ds));
        %let vnum = %sysfunc(varnum(&dsid, TRT01P));
        %let rc = %sysfunc(close(&dsid));
    %mend util_chkvars;
    """
    expanded = proc.process(code)
    assert "%sysfunc(open" not in expanded

def test_16_gen_tp_join_adsl_integration_subset():
    re_engine = RuleEngine()
    step = ProgramStep(step_index=1, step_type="PROC_STEP", name="PROC SQL", source_code="proc sql; select 'Y' into :_trt_time from ALLVARS where upcase(name) like 'TR__STM'; quit;")
    r_code, _, _ = re_engine.translate_step(step)
    assert r_code is not None
    assert "into :" not in r_code
    assert "like '" not in r_code
    assert 'grepl("^TR..STM$", toupper(name))' in r_code

def test_17_existing_phase9_22_false_dependency_tests():
    from project_engine.dependency_parser import DependencyParser
    dp = DependencyParser()
    refs = dp.parse_references("TEST", "%macro test(); %do i=1 %to 5; %quit; %end; %mend;", "test.sas")
    assert len(refs) == 0

def test_18_existing_macro_only_routing_tests():
    from app import is_meaningful_sas_source
    sas_code = "%macro library(); proc print data=a; run; %mend;"
    assert is_meaningful_sas_source(sas_code) is True
