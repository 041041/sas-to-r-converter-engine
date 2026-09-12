"""
test_suite/test_project_engine.py
──────────────────────────────────
Unit and integration tests for Enterprise SAS Project Dependency Architecture.
Tests 12 distinct dependency, resolution, and backward-compatibility scenarios.
"""

import pytest
from project_engine import (
    ProjectAnalyzer,
    ProjectContext,
    ResolutionStatus,
    ProjectFileRegistry,
    MacroRegistry,
    DependencyParser,
    DependencyGraphBuilder,
    DependencyResolver,
    ProjectValidator
)


def test_scenario_01_single_macro():
    sas_code = "%macro SINGLE_MAC; proc print data=sashelp.class; run; %mend;"
    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project([("single.sas", sas_code)], main_filename="single.sas")
    assert ctx.resolution_result.status == ResolutionStatus.RESOLVED
    assert "SINGLE_MAC" in ctx.macro_registry
    assert len(ctx.macro_registry) == 1


def test_scenario_02_big_macro_plus_macro_a():
    big_macro_sas = "%macro BIG_MACRO; %MACRO_A; proc sort; run; %mend;"
    macro_a_sas = "%macro MACRO_A; data work.a; set sashelp.class; run; %mend;"

    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project([
        ("BIG_MACRO.sas", big_macro_sas),
        ("MACRO_A.sas", macro_a_sas)
    ], main_filename="BIG_MACRO.sas")

    assert ctx.resolution_result.status == ResolutionStatus.RESOLVED
    assert ctx.dependency_order == ["MACRO_A", "BIG_MACRO"]
    assert len(ctx.ordered_supporting_content) == 1
    assert ctx.ordered_supporting_content[0] == macro_a_sas


def test_scenario_03_big_macro_plus_macro_a_b():
    big_macro_sas = "%macro BIG_MACRO; %MACRO_A; %MACRO_B; %mend;"
    macro_a_sas = "%macro MACRO_A; data a; run; %mend;"
    macro_b_sas = "%macro MACRO_B; data b; run; %mend;"

    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project([
        ("BIG_MACRO.sas", big_macro_sas),
        ("MACRO_A.sas", macro_a_sas),
        ("MACRO_B.sas", macro_b_sas)
    ], main_filename="BIG_MACRO.sas")

    assert ctx.resolution_result.status == ResolutionStatus.RESOLVED
    assert "MACRO_A" in ctx.dependency_order
    assert "MACRO_B" in ctx.dependency_order
    assert "BIG_MACRO" in ctx.dependency_order
    # MACRO_A and MACRO_B must come before BIG_MACRO
    assert ctx.dependency_order.index("MACRO_A") < ctx.dependency_order.index("BIG_MACRO")
    assert ctx.dependency_order.index("MACRO_B") < ctx.dependency_order.index("BIG_MACRO")


def test_scenario_04_nested_dependencies():
    big_macro_sas = "%macro BIG_MACRO; %MACRO_A; %mend;"
    macro_a_sas = "%macro MACRO_A; %MACRO_UTIL; %mend;"
    macro_util_sas = "%macro MACRO_UTIL; data util; run; %mend;"

    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project([
        ("BIG_MACRO.sas", big_macro_sas),
        ("MACRO_A.sas", macro_a_sas),
        ("utils.sas", macro_util_sas)
    ], main_filename="BIG_MACRO.sas")

    assert ctx.resolution_result.status == ResolutionStatus.RESOLVED
    assert ctx.dependency_order == ["MACRO_UTIL", "MACRO_A", "BIG_MACRO"]


def test_scenario_05_three_level_dependency():
    main_sas = "%MACRO_LEVEL1;"
    l1_sas = "%macro MACRO_LEVEL1; %MACRO_LEVEL2; %mend;"
    l2_sas = "%macro MACRO_LEVEL2; %MACRO_LEVEL3; %mend;"
    l3_sas = "%macro MACRO_LEVEL3; data final; run; %mend;"

    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project([
        ("main.sas", main_sas),
        ("l1.sas", l1_sas),
        ("l2.sas", l2_sas),
        ("l3.sas", l3_sas)
    ], main_filename="main.sas")

    assert ctx.resolution_result.status == ResolutionStatus.RESOLVED
    assert ctx.dependency_order == ["MACRO_LEVEL3", "MACRO_LEVEL2", "MACRO_LEVEL1"]


def test_scenario_06_missing_dependency():
    big_macro_sas = "%macro BIG_MACRO; %MACRO_A; %MACRO_MISSING; %mend;"
    macro_a_sas = "%macro MACRO_A; data a; run; %mend;"

    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project([
        ("BIG_MACRO.sas", big_macro_sas),
        ("MACRO_A.sas", macro_a_sas)
    ], main_filename="BIG_MACRO.sas")

    assert ctx.resolution_result.status == ResolutionStatus.UNRESOLVED
    assert len(ctx.resolution_result.missing_dependencies) == 1
    assert ctx.resolution_result.missing_dependencies[0].referenced_macro == "MACRO_MISSING"


def test_scenario_07_duplicate_definition():
    file1 = "%macro MACRO_A; data a1; run; %mend;"
    file2 = "%macro MACRO_A; data a2; run; %mend;"

    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project([
        ("file1.sas", file1),
        ("file2.sas", file2)
    ])

    assert ctx.resolution_result.status == ResolutionStatus.DUPLICATE_DEFINITION
    assert "MACRO_A" in ctx.resolution_result.duplicate_definitions
    assert set(ctx.resolution_result.duplicate_definitions["MACRO_A"]) == {"file1.sas", "file2.sas"}


def test_scenario_08_circular_dependency():
    file_a = "%macro MACRO_A; %MACRO_B; %mend;"
    file_b = "%macro MACRO_B; %MACRO_A; %mend;"

    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project([
        ("a.sas", file_a),
        ("b.sas", file_b)
    ])

    assert ctx.resolution_result.status == ResolutionStatus.CIRCULAR_DEPENDENCY
    assert len(ctx.resolution_result.circular_paths) > 0


def test_scenario_09_multiple_unrelated_macros():
    file_x = "%macro MACRO_X; data x; run; %mend;"
    file_y = "%macro MACRO_Y; data y; run; %mend;"
    file_z = "%macro MACRO_Z; data z; run; %mend;"

    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project([
        ("x.sas", file_x),
        ("y.sas", file_y),
        ("z.sas", file_z)
    ])

    assert ctx.resolution_result.status == ResolutionStatus.RESOLVED
    assert set(ctx.dependency_order) == {"MACRO_X", "MACRO_Y", "MACRO_Z"}


def test_scenario_10_macro_calls_with_parameters():
    sas_code = """
    %macro CALC_TOTAL(in_ds=, out_ds=work.out, factor=1.5);
        data &out_ds;
            set &in_ds;
            total = val * &factor;
        run;
    %mend;
    %macro CALLER;
        %CALC_TOTAL(in_ds=adam.adsl, factor=2.0);
    %mend;
    """
    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project([("params.sas", sas_code)])
    assert ctx.resolution_result.status == ResolutionStatus.RESOLVED
    assert ctx.dependency_order == ["CALC_TOTAL", "CALLER"]
    mdef = ctx.macro_registry["CALC_TOTAL"]
    assert len(mdef.parameters) == 3


def test_scenario_11_case_variation_handling():
    sas_code_1 = "%macro my_custom_util; data _null_; run; %mend;"
    sas_code_2 = "%macro MAIN_PROC; %MY_CUSTOM_UTIL; %mend;"

    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project([
        ("util.sas", sas_code_1),
        ("main.sas", sas_code_2)
    ], main_filename="main.sas")

    assert ctx.resolution_result.status == ResolutionStatus.RESOLVED
    assert "MY_CUSTOM_UTIL" in ctx.macro_registry
    assert ctx.dependency_order == ["MY_CUSTOM_UTIL", "MAIN_PROC"]


def test_scenario_12_single_file_backward_compatibility():
    sas_code = "data work.test; set sashelp.class; run;"
    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project([("single_file.sas", sas_code)], main_filename="single_file.sas")

    assert ctx.resolution_result.status == ResolutionStatus.RESOLVED
    assert len(ctx.macro_registry) == 0
    assert len(ctx.project_files) == 1
    assert ctx.main_program_file == "single_file.sas"
    assert ctx.main_program_content == sas_code

    # Test validator tree formatting
    validator = ProjectValidator()
    tree = validator.format_tree_view(ctx)
    assert "single_file.sas" in tree
