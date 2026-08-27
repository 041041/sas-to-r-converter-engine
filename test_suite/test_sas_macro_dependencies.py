"""
test_sas_macro_dependencies.py
──────────────────────────────
Focused unit tests for Phase 8.8 SAS Macro Dependency Linking & Reusable R Functions.
"""

import pytest
from macro_converter import convert_macros_to_r, parse_sas_source
from sas_step_converter import SASStepConverter


def test_1_independent_macros():
    sas_code = """
    %macro macro_a(ds=DM);
        data A;
            set &ds;
        run;
    %mend macro_a;

    %macro macro_b(ds=AE);
        data B;
            set &ds;
        run;
    %mend macro_b;
    """
    parsed = parse_sas_source(sas_code)
    res = convert_macros_to_r(parsed['macro_definitions'], parsed['macro_calls'], dialect="Modern R (dplyr)")
    
    assert "macro_a <- function" in res["r_functions"]
    assert "macro_b <- function" in res["r_functions"]
    assert len(res["warnings"]) == 0


def test_2_direct_dependency():
    sas_code = """
    %macro macro_a(ds=DM);
        data A;
            set &ds;
        run;
    %mend macro_a;

    %macro macro_b(ds=DM);
        %macro_a(ds=&ds);
    %mend macro_b;
    """
    parsed = parse_sas_source(sas_code)
    res = convert_macros_to_r(parsed['macro_definitions'], parsed['macro_calls'], dialect="Modern R (dplyr)")
    
    funcs = res["r_functions"]
    assert "macro_a <- function" in funcs
    assert "macro_b <- function" in funcs
    # macro_a definition must appear BEFORE macro_b
    assert funcs.find("macro_a <- function") < funcs.find("macro_b <- function")
    assert "result <- macro_a(ds = ds)" in funcs


def test_3_keyword_argument_dependency():
    sas_code = """
    %macro macro_a(ds=DM, out=ADSL);
        data &out;
            set &ds;
        run;
    %mend macro_a;

    %macro macro_b(source=DM, target=ADSL);
        %macro_a(ds=&source, out=&target);
    %mend macro_b;
    """
    parsed = parse_sas_source(sas_code)
    res = convert_macros_to_r(parsed['macro_definitions'], parsed['macro_calls'], dialect="Modern R (dplyr)")
    
    funcs = res["r_functions"]
    assert "macro_a(ds = source, out = target)" in funcs


def test_4_positional_argument_dependency():
    sas_code = """
    %macro macro_a(ds, out);
        data &out;
            set &ds;
        run;
    %mend macro_a;

    %macro macro_b(input, output);
        %macro_a(&input, &output);
    %mend macro_b;
    """
    parsed = parse_sas_source(sas_code)
    res = convert_macros_to_r(parsed['macro_definitions'], parsed['macro_calls'], dialect="Modern R (dplyr)")
    
    funcs = res["r_functions"]
    assert "macro_a(input, output)" in funcs


def test_5_multiple_dependencies():
    sas_code = """
    %macro macro_a(ds=DM);
        data A; set &ds; run;
    %mend;

    %macro macro_b(ds=AE);
        data B; set &ds; run;
    %mend;

    %macro utility(ds=DM);
        %macro_a(ds=&ds);
        %macro_b(ds=&ds);
    %mend;
    """
    parsed = parse_sas_source(sas_code)
    res = convert_macros_to_r(parsed['macro_definitions'], parsed['macro_calls'], dialect="Modern R (dplyr)")
    
    funcs = res["r_functions"]
    assert funcs.find("macro_a <- function") < funcs.find("utility <- function")
    assert funcs.find("macro_b <- function") < funcs.find("utility <- function")
    assert "result <- macro_a(ds = ds)" in funcs
    assert "result <- macro_b(ds = ds)" in funcs


def test_6_three_level_dependency():
    sas_code = """
    %macro macro_a(ds=DM);
        data A; set &ds; run;
    %mend;

    %macro macro_b(ds=DM);
        %macro_a(ds=&ds);
    %mend;

    %macro utility(ds=DM);
        %macro_b(ds=&ds);
    %mend;
    """
    parsed = parse_sas_source(sas_code)
    res = convert_macros_to_r(parsed['macro_definitions'], parsed['macro_calls'], dialect="Modern R (dplyr)")
    
    funcs = res["r_functions"]
    idx_a = funcs.find("macro_a <- function")
    idx_b = funcs.find("macro_b <- function")
    idx_u = funcs.find("utility <- function")
    
    assert idx_a != -1 and idx_b != -1 and idx_u != -1
    assert idx_a < idx_b < idx_u


def test_7_cycle_detection_safe_reject():
    sas_code = """
    %macro macro_a();
        %macro_b();
    %mend;

    %macro macro_b();
        %macro_a();
    %mend;
    """
    parsed = parse_sas_source(sas_code)
    res = convert_macros_to_r(parsed['macro_definitions'], parsed['macro_calls'], dialect="Modern R (dplyr)")
    
    assert any("dependency cycle detected" in w.lower() for w in res["warnings"])
    assert "Manual review required" in res["r_functions"] or res["r_functions"] == ""


def test_8_unknown_dependency_safe_reject():
    sas_code = """
    %macro utility(ds=DM);
        %unknown_macro(ds=&ds);
    %mend;
    """
    parsed = parse_sas_source(sas_code)
    res = convert_macros_to_r(parsed['macro_definitions'], parsed['macro_calls'], dialect="Modern R (dplyr)")
    
    assert any("calls unknown macro" in w.lower() for w in res["warnings"])
    assert "Manual review required" in res["r_functions"] or res["r_functions"] == ""


def test_9_parameter_mapping_unquoted_identifier():
    sas_code = """
    %macro child(ds=DM);
        data C; set &ds; run;
    %mend;

    %macro parent(ds=DM);
        %child(ds=&ds);
    %mend;
    """
    parsed = parse_sas_source(sas_code)
    res = convert_macros_to_r(parsed['macro_definitions'], parsed['macro_calls'], dialect="Modern R (dplyr)")
    
    funcs = res["r_functions"]
    # Must map &ds to parameter identifier ds, NOT string "&ds"
    assert 'child(ds = ds)' in funcs
    assert 'child(ds = "&ds")' not in funcs


def test_10_phase8_6_macro_expansion_remains_unchanged():
    sas_code = """
    %let min_age = 18;
    %macro filter_adsl(ds=DM, out=ADSL);
        data &out;
            set &ds;
            if AGE >= &min_age then FLAG='Y';
        run;
    %mend;

    %filter_adsl(ds=DM, out=ADSL);
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    
    assert step.conversion_method == "Rule_DataStepFilter"
    assert "ADSL <- DM" in step.optimized_r_code
