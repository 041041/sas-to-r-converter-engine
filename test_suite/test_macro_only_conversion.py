"""
test_suite/test_macro_only_conversion.py
──────────────────────────────────────────
Unit and integration tests for Phase 9.09 Macro-Only Conversion & Program Classification.
"""

import pytest
from project_engine import ProjectAnalyzer, ProgramClassifier, ProgramType, ResolutionStatus
from macro_converter import parse_sas_source, convert_macros_to_r


def test_01_macro_definition_only():
    sas_code = """
    %macro SIMPLE_MAC(in_ds=, out_ds=);
        data &out_ds;
            set &in_ds;
        run;
    %mend;
    """
    classifier = ProgramClassifier()
    ptype = classifier.classify_source(sas_code)
    assert ptype == ProgramType.MACRO_LIBRARY

    parsed = parse_sas_source(sas_code)
    assert "SIMPLE_MAC" in parsed["macro_definitions"]

    macro_res = convert_macros_to_r(parsed["macro_definitions"], parsed["macro_calls"], dialect="Modern R (tidyverse)")
    assert "simple_mac <- function" in macro_res["r_functions"]


def test_02_macro_definition_with_dependency():
    sas_code = """
    %macro CALLING_MAC(in_ds=);
        %UTIL_MAC(in=&in_ds);
    %mend;
    %macro UTIL_MAC(in=);
        data work.util; set &in; run;
    %mend;
    """
    classifier = ProgramClassifier()
    ptype = classifier.classify_source(sas_code)
    assert ptype == ProgramType.MACRO_LIBRARY

    parsed = parse_sas_source(sas_code)
    macro_res = convert_macros_to_r(parsed["macro_definitions"], parsed["macro_calls"], dialect="Modern R (tidyverse)")
    assert "calling_mac <- function" in macro_res["r_functions"]
    assert "util_mac <- function" in macro_res["r_functions"]


def test_03_big_macro_plus_macro_a_b():
    big_macro = "%macro BIG_MACRO(in=, out=); %MACRO_A; %MACRO_B; %mend;"
    macro_a = "%macro MACRO_A; data a; run; %mend;"
    macro_b = "%macro MACRO_B; data b; run; %mend;"

    files = [
        ("BIG_MACRO.sas", big_macro),
        ("MACRO_A.sas", macro_a),
        ("MACRO_B.sas", macro_b)
    ]
    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project(files, main_filename="BIG_MACRO.sas")

    assert ctx.resolution_result.status == ResolutionStatus.RESOLVED
    assert ctx.dependency_order == ["MACRO_A", "MACRO_B", "BIG_MACRO"]


def test_04_nested_macro_library():
    l1 = "%macro L1; %L2; %mend;"
    l2 = "%macro L2; %L3; %mend;"
    l3 = "%macro L3; data l3; run; %mend;"

    files = [("L1.sas", l1), ("L2.sas", l2), ("L3.sas", l3)]
    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project(files, main_filename="L1.sas")

    assert ctx.dependency_order == ["L3", "L2", "L1"]


def test_05_macro_library_plus_data_step():
    sas_code = """
    %macro MAC1; data a; run; %mend;
    data work.final; set work.a; run;
    """
    classifier = ProgramClassifier()
    ptype = classifier.classify_source(sas_code)
    assert ptype == ProgramType.MIXED_PROGRAM


def test_06_macro_library_plus_proc_step():
    sas_code = """
    %macro MAC1; data a; run; %mend;
    proc sort data=work.final; by usubjid; run;
    """
    classifier = ProgramClassifier()
    ptype = classifier.classify_source(sas_code)
    assert ptype == ProgramType.MIXED_PROGRAM


def test_07_invalid_empty_source():
    classifier = ProgramClassifier()
    assert classifier.classify_source("") == ProgramType.INVALID_SOURCE
    assert classifier.classify_source("   \n  ") == ProgramType.INVALID_SOURCE


def test_08_ordinary_executable_sas():
    sas_code = "data work.test; set sashelp.class; run;"
    classifier = ProgramClassifier()
    assert classifier.classify_source(sas_code) == ProgramType.EXECUTABLE_PROGRAM


def test_09_single_file_macro_library():
    sas_code = "%macro M1; data _null_; run; %mend;"
    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project([("m1.sas", sas_code)], main_filename="m1.sas")
    assert ctx.resolution_result.status == ResolutionStatus.RESOLVED
    assert "M1" in ctx.macro_registry


def test_10_multi_file_macro_library():
    f1 = "%macro M1; %M2; %mend;"
    f2 = "%macro M2; data _null_; run; %mend;"

    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project([("f1.sas", f1), ("f2.sas", f2)], main_filename="f1.sas")
    assert ctx.resolution_result.status == ResolutionStatus.RESOLVED
    assert len(ctx.macro_registry) == 2
