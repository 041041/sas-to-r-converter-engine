"""
test_sas_macro_path_architecture.py
───────────────────────────────────
Unit test suite for Phase 8.26 — Macro Path Architecture (Path A / Path B separation,
balanced macro extraction, scoped frames, %LOCAL/%GLOBAL, and classify_macro).
"""

import pytest
from macro_processor import SASMacroProcessor
from macro_converter import classify_macro, convert_macros_to_r, parse_sas_source
from sas_step_converter import SASStepConverter


def test_1_balanced_nested_macro_extraction():
    sas_code = """
    %let study=STUDY01;
    %let ds1=DM;
    %let ds2=AE;

    %macro prepare_data(domain=DM, suffix=FINAL);

        %if &domain=DM %then %do;
            %let source=DM;
            %let keepvars=USUBJID AGE SEX;
        %end;
        %else %do;
            %let source=AE;
            %let keepvars=USUBJID AEDECOD AESTDTC;
        %end;

        %macro build_output(prefix=STUDY);
            %do i=1 %to 2;

                data &prefix._&domain._&i._&suffix;
                    set &&ds&i;

                    keep &keepvars;

                    if not missing(USUBJID);

                run;

            %end;
        %mend;

        %build_output(prefix=&study);

    %mend;

    %prepare_data(domain=DM, suffix=FINAL);
    """
    proc = SASMacroProcessor()
    code, warnings, _ = proc.process(sas_code)
    # Verify inner macro was properly extracted and expanded without missing definition errors
    assert not any("called but not defined" in w.lower() for w in warnings)
    assert "data STUDY01_DM_1_FINAL;" in code
    assert "set DM;" in code
    assert "data STUDY01_DM_2_FINAL;" in code
    assert "set AE;" in code


def test_2_path_b_reusable_macro_conversion():
    sas_code = """
    %macro filter_dataset(data=, var=);
        data OUT;
            set &data;
            if not missing(&var);
        run;
    %mend;
    """
    macro_def = {"params": ["DATA", "VAR"], "body": "data OUT; set &data; if not missing(&var); run;"}
    path = classify_macro("FILTER_DATASET", macro_def)
    assert path == "PATH_B"

    parsed = parse_sas_source(sas_code)
    res = convert_macros_to_r(parsed["macro_definitions"], parsed["macro_calls"], dialect="Modern R (dplyr)")
    r_code = res["r_functions"]
    assert "filter_dataset <- function" in r_code
    assert "DM" not in r_code
    assert "AGE" not in r_code


def test_3_path_a_compile_time_macro_classification():
    macro_def = {"params": [], "body": "%do i=1 %to 2; data OUT&i; set &&ds&i; run; %end;"}
    path = classify_macro("GENERATE_TABLES", macro_def)
    assert path == "PATH_A"


def test_4_simple_path_a_regression():
    sas_code = """
    %let ds=DM;
    data OUT;
        set &ds;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    assert res.converted_steps[0].conversion_method != "ManualReviewRequired"
    assert "OUT <- DM" in res.converted_steps[0].optimized_r_code


def test_5_bounded_indirect_ampersand_regression():
    sas_code = """
    %let ds1=DM;
    %let ds2=AE;
    %do i=1 %to 2;
        data OUT&i;
            set &&ds&i;
        run;
    %end;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    assert len(res.converted_steps) == 2
    assert res.converted_steps[0].conversion_method != "ManualReviewRequired"
    assert res.converted_steps[1].conversion_method != "ManualReviewRequired"


def test_6_scoped_macro_frames_and_local_global():
    sas_code = """
    %let x=GLOBAL;

    %macro outer();
        %local x;
        %let x=OUTER;

        %macro inner();
            %local x;
            %let x=INNER;
            data OUT_INNER;
                set DM;
            run;
        %mend;

        %inner();

        data OUT_OUTER;
            set AE;
        run;

    %mend;

    %outer();
    """
    proc = SASMacroProcessor()
    code, warnings, _ = proc.process(sas_code)
    # Global frame should remain GLOBAL
    assert proc.global_frame.vars.get("X") == "GLOBAL"
    assert "data OUT_INNER;" in code
    assert "data OUT_OUTER;" in code


def test_7_unsafe_eval_safe_reject():
    macro_def = {"params": ["X"], "body": "%let val=%eval(&x + 1);"}
    path = classify_macro("EVAL_MACRO", macro_def)
    assert path == "SAFE_REJECT"


def test_8_unsafe_quad_ampersand_safe_reject():
    macro_def = {"params": ["I"], "body": "data OUT; set &&&&ds&i; run;"}
    path = classify_macro("QUAD_MACRO", macro_def)
    assert path == "SAFE_REJECT"


def test_9_unsafe_sysfunc_open_safe_reject():
    macro_def = {"params": ["DS"], "body": "%let h=%sysfunc(open(&ds));"}
    path = classify_macro("SYSFUNC_MACRO", macro_def)
    assert path == "SAFE_REJECT"


def test_10_p1_1_no_duplicate_data_parameter():
    # 1. macro(data=, var=)
    sas_code1 = """
    %macro filter_dataset(data=, var=);
        data OUT;
            set &data;
            if not missing(&var);
        run;
    %mend;
    """
    parsed1 = parse_sas_source(sas_code1)
    res1 = convert_macros_to_r(parsed1["macro_definitions"], parsed1["macro_calls"], dialect="Modern R (dplyr)")
    r1 = res1["r_functions"]
    assert "filter_dataset <- function(data =" in r1 or "filter_dataset <- function(data," in r1
    assert "function(data, data =" not in r1

    # 2. macro(DATA=, var=)
    sas_code2 = """
    %macro filter_dataset(DATA=DM, var=AGE);
        data OUT;
            set &data;
            if not missing(&var);
        run;
    %mend;
    """
    parsed2 = parse_sas_source(sas_code2)
    res2 = convert_macros_to_r(parsed2["macro_definitions"], parsed2["macro_calls"], dialect="Modern R (dplyr)")
    r2 = res2["r_functions"]
    assert "filter_dataset <- function(data =" in r2
    assert "function(data, data =" not in r2

    # 3. macro(out=, var=)
    sas_code3 = """
    %macro filter_dataset(out=, var=);
        data &out;
            set DM;
            if not missing(&var);
        run;
    %mend;
    """
    parsed3 = parse_sas_source(sas_code3)
    res3 = convert_macros_to_r(parsed3["macro_definitions"], parsed3["macro_calls"], dialect="Modern R (dplyr)")
    r3 = res3["r_functions"]
    assert "filter_dataset <- function(out, var)" in r3

    # 4. macro(data=)
    sas_code4 = """
    %macro process_data(data=);
        data OUT; set &data; run;
    %mend;
    """
    parsed4 = parse_sas_source(sas_code4)
    res4 = convert_macros_to_r(parsed4["macro_definitions"], parsed4["macro_calls"], dialect="Modern R (dplyr)")
    r4 = res4["r_functions"]
    assert "process_data <- function(data =" in r4 or "process_data <- function(data)" in r4
    assert "function(data, data" not in r4

    # 5. macro with no explicit data parameter
    sas_code5 = """
    %macro process_var(var=AGE);
        data OUT; set DM; run;
    %mend;
    """
    parsed5 = parse_sas_source(sas_code5)
    res5 = convert_macros_to_r(parsed5["macro_definitions"], parsed5["macro_calls"], dialect="Modern R (dplyr)")
    r5 = res5["r_functions"]
    assert 'process_var <- function(var = "AGE")' in r5


def test_11_p1_2_global_frame_synchronization():
    sas_code = """
    %let x=OLD;

    %macro update();
        %global x;
        %let x=NEW;
    %mend;

    %update;

    data OUT;
        set &x;
    run;
    """
    proc = SASMacroProcessor()
    code, warnings, _ = proc.process(sas_code)
    assert "set NEW;" in code
    assert "set OLD;" not in code


def test_12_p1_2_additional_global_synchronization():
    sas_code = """
    %let a=A;
    %let b=B;

    %macro update();
        %global a;
        %let a=NEW_A;
    %mend;

    %update;

    data OUT;
        set &a;
    run;
    """
    proc = SASMacroProcessor()
    code, warnings, _ = proc.process(sas_code)
    assert "set NEW_A;" in code
    assert proc.global_frame.vars.get("B") == "B"


def test_13_p1_2_local_regression():
    sas_code = """
    %let x=GLOBAL;

    %macro test();
        %local x;
        %let x=LOCAL;
    %mend;

    %test;

    data OUT;
        set &x;
    run;
    """
    proc = SASMacroProcessor()
    code, warnings, _ = proc.process(sas_code)
    assert "set GLOBAL;" in code
    assert "set LOCAL;" not in code

