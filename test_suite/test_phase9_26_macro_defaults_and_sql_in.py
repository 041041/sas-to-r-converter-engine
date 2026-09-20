"""
test_suite/test_phase9_26_macro_defaults_and_sql_in.py
──────────────────────────────────────────────────────────
Regression & Acceptance tests for Phase 9.26:
1. Macro default parameter binding
2. Explicit parameter overriding default
3. Positional parameter + default parameter
4. %upcase() after default binding
5. SAS SQL IN → R %in%
6. SAS SQL NOT IN
7. Numeric IN values
8. Macro variables inside IN lists
9. PATH_B keyword invocation
10. PATH_B positional invocation
11. PATH_B macro variable arguments
12. Real clinical three-file project
"""

import pytest
from macro_processor import SASMacroProcessor
from rule_engine import RuleEngine
from sas_step_converter import SASStepConverter
from doc_generator import validate_generated_r_code


@pytest.fixture
def macro_processor():
    return SASMacroProcessor()


@pytest.fixture
def rule_engine():
    return RuleEngine()


@pytest.fixture
def step_converter():
    return SASStepConverter()


# 1. Macro default parameter binding
def test_macro_default_parameter_binding(macro_processor):
    sas = """
    %macro test_m(a=ABC, b=123);
        data OUT; set IN; A="&a"; B=&b; run;
    %mend test_m;
    %test_m();
    """
    res, _, _ = macro_processor.process(sas)
    assert 'A="ABC"' in res
    assert 'B=123' in res


# 2. Explicit parameter overriding default
def test_explicit_parameter_overriding_default(macro_processor):
    sas = """
    %macro test_m(a=ABC, b=123);
        data OUT; set IN; A="&a"; B=&b; run;
    %mend test_m;
    %test_m(a=XYZ);
    """
    res, _, _ = macro_processor.process(sas)
    assert 'A="XYZ"' in res
    assert 'B=123' in res


# 3. Positional parameter + default parameter
def test_positional_plus_default_parameter(macro_processor):
    sas = """
    %macro test_m(pos_var, default_var=DEF_VAL);
        data OUT; set &pos_var; FLAG="&default_var"; run;
    %mend test_m;
    %test_m(MY_INPUT);
    """
    res, _, _ = macro_processor.process(sas)
    assert 'set MY_INPUT;' in res
    assert 'FLAG="DEF_VAL";' in res


# 4. %upcase() after default binding
def test_upcase_after_default_binding(macro_processor):
    sas = """
    %macro test_up(val=lower_str);
        %let res = %upcase(&val);
        data OUT; X="&res"; run;
    %mend test_up;
    %test_up();
    """
    res, _, _ = macro_processor.process(sas)
    assert 'X="LOWER_STR"' in res


# 5. SAS SQL IN → R %in%
def test_sas_sql_in_to_r_percent_in(rule_engine):
    sas = "proc sql noprint; select 'Y' into :flag from ALLVARS where upcase(name) in ('TR01SDT', 'TR02SDT'); quit;"
    r_code, _, _ = rule_engine.translate_step(type("Step", (), {"source_code": sas, "step_type": "PROC_SQL"})())
    assert "%in%" in r_code
    assert "toupper(name) %in% c('TR01SDT', 'TR02SDT')" in r_code


# 6. SAS SQL NOT IN
def test_sas_sql_not_in(rule_engine):
    sas = "proc sql noprint; select 'Y' into :flag from ALLVARS where name not in ('A', 'B'); quit;"
    r_code, _, _ = rule_engine.translate_step(type("Step", (), {"source_code": sas, "step_type": "PROC_SQL"})())
    assert "!(name %in% c('A', 'B'))" in r_code


# 7. Numeric IN values
def test_numeric_in_values(rule_engine):
    sas = "proc sql noprint; select 'Y' into :flag from ALLVARS where age in (18, 65, 80); quit;"
    r_code, _, _ = rule_engine.translate_step(type("Step", (), {"source_code": sas, "step_type": "PROC_SQL"})())
    assert "age %in% c(18, 65, 80)" in r_code


# 8. Macro variables inside IN lists
def test_macro_vars_inside_in_lists(rule_engine):
    sas = "proc sql noprint; select 'Y' into :flag from ALLVARS where code in (VAL1, VAL2); quit;"
    r_code, _, _ = rule_engine.translate_step(type("Step", (), {"source_code": sas, "step_type": "PROC_SQL"})())
    assert 'code %in% c("VAL1", "VAL2")' in r_code


# 9. PATH_B keyword invocation
def test_path_b_keyword_invocation(rule_engine):
    sas = "%util_chkvars(ds=WORK.ADSL, varlist=USUBJID TRT01P, drop=APERSDY APEREDY);"
    r_code, _, _ = rule_engine.translate_step(type("Step", (), {"source_code": sas, "step_type": "MACRO_CALL"})())
    assert "util_chkvars(" in r_code
    assert "ds = ADSL" in r_code
    assert 'varlist = c("USUBJID", "TRT01P")' in r_code
    assert 'drop = c("APERSDY", "APEREDY")' in r_code


# 10. PATH_B positional invocation
def test_path_b_positional_invocation(rule_engine):
    sas = "%util_chkvars(WORK.ADSL, USUBJID TRT01P);"
    r_code, _, _ = rule_engine.translate_step(type("Step", (), {"source_code": sas, "step_type": "MACRO_CALL"})())
    assert "util_chkvars(" in r_code
    assert "ADSL" in r_code
    assert 'c("USUBJID", "TRT01P")' in r_code


# 11. PATH_B macro variable arguments
def test_path_b_macro_var_arguments(rule_engine):
    sas = "%util_chkvars(ds=&_dsnin, varlist=&varlist, drop=&_dropvars);"
    r_code, _, _ = rule_engine.translate_step(type("Step", (), {"source_code": sas, "step_type": "MACRO_CALL"})())
    assert "&" not in r_code
    assert "ds = _DSNIN" in r_code or "ds = _dsnin" in r_code.lower()


# 12. Real clinical three-file project
def test_real_clinical_three_file_project(step_converter):
    file3_code = """
    %macro util_chkvars(ds=WORK.ADSL, varlist=USUBJID TRT01P, drop=);
        %local dsid vnum i var_item _dsnin _dropvars;
        %let _dsnin = &ds;
        %let _dropvars = &drop;
        %let dsid = %sysfunc(open(&_dsnin));
        %do i = 1 %to %sysfunc(countw(&varlist));
            %let var_item = %scan(&varlist, &i);
            %let vnum = %sysfunc(varnum(&dsid, &var_item));
            %if &vnum = 0 %then %put WARNING: Variable &var_item missing in &_dsnin;
        %end;
        %let rc = %sysfunc(close(&dsid));
    %mend util_chkvars;
    """

    file2_code = """
    %macro util_num_periods(in_ds=WORK.ADSL);
        %global G_PRDCNT;
        proc contents data=&in_ds out=WORK.ALLVARS noprint; run;
        proc sql noprint;
            select count(distinct name) into :G_PRDCNT from ALLVARS where upcase(name) in ('TR01SDT', 'TR02SDT');
        quit;
    %mend util_num_periods;
    """

    file1_code = """
    %macro gen_tp_join_adsl(
        in_ds=WORK.ADSL,
        out_ds=WORK.ADSL_TP,
        analstarttmvar=TRT01STM,
        analstartdtmvar=TRT01SDTM,
        analendtmvar=TRT02STM,
        analenddtmvar=TRT02SDTM,
        dropvars=APERSDY APEREDY
    );
        %local _analstarttmvar _analstartdtmvar _analendtmvar _analenddtmvar _dropvars;
        %let _analstarttmvar = &analstarttmvar;
        %let _analstartdtmvar = &analstartdtmvar;
        %let _analendtmvar = &analendtmvar;
        %let _analenddtmvar = &analenddtmvar;
        %let _dropvars = &dropvars;

        %util_chkvars(ds=&in_ds, varlist=USUBJID TRT01P TRT01SDT, drop=&_dropvars);
        %util_num_periods(in_ds=&in_ds);

        proc sql noprint;
            select 'Y' into :_trt_time from ALLVARS where upcase(name) in (%upcase(&_analstarttmvar), %upcase(&_analendtmvar));
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

    # Assertions
    assert "%upcase" not in r_code
    assert "&_analstarttmvar" not in r_code
    assert "toupper(name) in" not in r_code
    assert "DATA_STEP_" not in r_code
    assert "util_chkvars(_dsnin" not in r_code

    val_status, issues = validate_generated_r_code(r_code)
    assert val_status == "VALID_R"
    assert len(issues) == 0
