"""
test_sas_macro_integration.py
──────────────────────────────
Phase 8.10 Macro System Consolidation & Integration Audit Test Suite.
Tests the combined operation of Phase 8.6 (%LET & parameters), Phase 8.8 (dependencies & reusable functions),
and Phase 8.9 (macro-time %IF/%THEN/%ELSE) across 10 integration cases.
"""

import pytest
from macro_processor import SASMacroProcessor
from macro_converter import convert_macros_to_r, parse_sas_source
from sas_step_converter import SASStepConverter


def test_integration_case_1_let_param_if():
    sas_code = """
    %let threshold=65;

    %macro flag(ds=DM, limit=&threshold);
        %if &limit >= 65 %then %do;
            data ADSL;
                set &ds;
            run;
        %end;
        %else %do;
            data ADSL;
                set AE;
            run;
        %end;
    %mend;

    %flag(ds=DM);
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "Rule_DataStepFilter"
    assert "ADSL <- DM" in step.optimized_r_code


def test_integration_case_2_keyword_param_else():
    sas_code = """
    %macro utility(ds=DM, useae=N);
        %if &useae = Y %then %do;
            data OUT;
                set AE;
            run;
        %end;
        %else %do;
            data OUT;
                set &ds;
            run;
        %end;
    %mend;

    %utility(ds=DM, useae=N);
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "Rule_DataStepFilter"
    assert "OUT <- DM" in step.optimized_r_code
    assert "AE" not in step.optimized_r_code


def test_integration_case_3_nested_dependency_param():
    sas_code = """
    %macro filter_data(ds=DM);
        data FILTERED;
            set &ds;
        run;
    %mend;

    %macro utility(ds=DM);
        %filter_data(ds=&ds);
    %mend;
    """
    parsed = parse_sas_source(sas_code)
    res = convert_macros_to_r(parsed['macro_definitions'], parsed['macro_calls'], dialect="Modern R (dplyr)")
    funcs = res["r_functions"]
    
    assert "filter_data <- function" in funcs
    assert "utility <- function" in funcs
    assert "result <- filter_data(ds = ds)" in funcs


def test_integration_case_4_three_levels():
    sas_code = """
    %macro base(ds=DM);
        data BASE;
            set &ds;
        run;
    %mend;

    %macro middle(ds=DM);
        %base(ds=&ds);
    %mend;

    %macro utility(ds=DM);
        %middle(ds=&ds);
    %mend;
    """
    parsed = parse_sas_source(sas_code)
    res = convert_macros_to_r(parsed['macro_definitions'], parsed['macro_calls'], dialect="Modern R (dplyr)")
    funcs = res["r_functions"]
    
    idx_b = funcs.find("base <- function")
    idx_m = funcs.find("middle <- function")
    idx_u = funcs.find("utility <- function")
    
    assert idx_b != -1 and idx_m != -1 and idx_u != -1
    assert idx_b < idx_m < idx_u
    assert "result <- base(ds = ds)" in funcs
    assert "result <- middle(ds = ds)" in funcs


def test_integration_case_5_multiple_dependencies_if():
    sas_code = """
    %macro a(ds=DM);
        data A; set &ds; run;
    %mend;

    %macro b(ds=DM);
        data B; set &ds; run;
    %mend;

    %macro utility(ds=DM, use_b=Y);
        %a(ds=&ds);
        %if &use_b = Y %then %do;
            %b(ds=&ds);
        %end;
    %mend;
    """
    # Path A execution mode when use_b=Y
    converter = SASStepConverter()
    res_exec = converter.convert_program(sas_code + "\n%utility(ds=DM, use_b=Y);")
    assert len(res_exec.converted_steps) == 2

    # Path B reusable function mode
    parsed = parse_sas_source(sas_code)
    res = convert_macros_to_r(parsed['macro_definitions'], parsed['macro_calls'], dialect="Modern R (dplyr)")
    funcs = res["r_functions"]
    
    assert "a <- function" in funcs
    assert "b <- function" in funcs
    assert "utility" not in funcs


def test_integration_case_6_default_nested_call():
    sas_code = """
    %macro base(ds=DM);
        data OUT;
            set &ds;
        run;
    %mend;

    %macro utility(ds=DM);
        %base(ds=&ds);
    %mend;

    %utility(ds=DM);
    """
    # Path A: Program execution
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    assert len(res.converted_steps) == 1

    # Path B: Reusable macro definitions
    parsed = parse_sas_source(sas_code)
    res_macro = convert_macros_to_r(parsed['macro_definitions'], parsed['macro_calls'], dialect="Modern R (dplyr)")
    funcs = res_macro["r_functions"]

    assert "base <- function" in funcs


def test_integration_case_7_safety_combination():
    sas_code = """
    %macro utility(ds=DM);
        %if &&dynamic = Y %then %do;
            %unknown_macro(ds=&ds);
        %end;
    %mend;
    %utility();
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    # Safe reject: No valid DATA/PROC step converted due to unevaluable condition / indirect ref
    assert len(res.converted_steps) == 0 or res.converted_steps[0].conversion_method == "ManualReviewRequired"


def test_integration_case_8_cycle_parameters():
    sas_code = """
    %macro a(ds=DM);
        %b(ds=&ds);
    %mend;

    %macro b(ds=DM);
        %a(ds=&ds);
    %mend;
    """
    parsed = parse_sas_source(sas_code)
    res = convert_macros_to_r(parsed['macro_definitions'], parsed['macro_calls'], dialect="Modern R (dplyr)")
    assert any("cycle" in w.lower() for w in res["warnings"]) or res["r_functions"] == ""


def test_integration_case_9_unknown_macro_valid_if():
    sas_code = """
    %macro utility(ds=DM, flag=Y);
        %if &flag = Y %then %do;
            %unknown_macro(ds=&ds);
        %end;
    %mend;
    %utility(ds=DM, flag=Y);
    """
    # Path A execution mode: selected branch contains unknown_macro -> safe reject!
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    assert len(res.converted_steps) == 0 or res.converted_steps[0].conversion_method == "ManualReviewRequired"

    # Path B reusable function mode with standalone unknown macro:
    sas_code_b = """
    %macro utility(ds=DM);
        %unknown_macro(ds=&ds);
    %mend;
    """
    parsed = parse_sas_source(sas_code_b)
    res_b = convert_macros_to_r(parsed['macro_definitions'], parsed['macro_calls'], dialect="Modern R (dplyr)")
    assert any("calls unknown macro" in w.lower() for w in res_b["warnings"]) or res_b["r_functions"] == ""


def test_integration_case_10_full_realistic_utility():
    sas_code = """
    %let default_ds=DM;

    %macro prepare(ds=&default_ds, flag=Y);
        %if &flag = Y %then %do;
            data PREP;
                set &ds;
            run;
        %end;
        %else %do;
            data PREP;
                set AE;
            run;
        %end;
    %mend;

    %macro utility(ds=&default_ds, flag=Y);
        %prepare(ds=&ds, flag=&flag);
    %mend;

    %utility(ds=DM, flag=Y);
    """
    # Path A: Program execution
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "Rule_DataStepFilter"
    assert "PREP <- DM" in step.optimized_r_code

    # Path B: Reusable macro definitions (%prepare is PATH_A due to %if/%then/%do)
    parsed = parse_sas_source(sas_code)
    res_macro = convert_macros_to_r(parsed['macro_definitions'], parsed['macro_calls'], dialect="Modern R (dplyr)")
    funcs = res_macro["r_functions"]
    
    assert funcs == ""
