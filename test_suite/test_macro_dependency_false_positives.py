"""
test_suite/test_macro_dependency_false_positives.py
────────────────────────────────────────────────────
Regression tests for Phase 9.22: Ignoring false SAS macro dependencies.
Ensures built-in SAS macro keywords, control constructs, and functions
(%TO, %WHILE, %QSCAN, %QUIT, etc.) are never inserted into the project dependency graph.
"""

import pytest
from project_engine.dependency_parser import DependencyParser
from project_engine.dependency_graph import DependencyGraphBuilder
from project_engine.macro_registry import MacroRegistry, MacroDefinition
from project_engine.file_registry import ProjectFileRegistry
from project_engine.resolver import DependencyResolver
from project_engine.models import ResolutionStatus, DependencyType

def test_1_to_is_not_dependency():
    parser = DependencyParser()
    code = "%macro test_to(); %do i=1 %to 10; %end; %mend;"
    refs = parser.parse_references("TEST_TO", code, "test.sas")
    ref_names = [r.referenced_macro for r in refs]
    assert "TO" not in ref_names
    assert "DO" not in ref_names
    assert "END" not in ref_names
    assert len(refs) == 0

def test_2_while_is_not_dependency():
    parser = DependencyParser()
    code = "%macro test_while(); %do %while(&x < 10); %end; %mend;"
    refs = parser.parse_references("TEST_WHILE", code, "test.sas")
    ref_names = [r.referenced_macro for r in refs]
    assert "WHILE" not in ref_names
    assert len(refs) == 0

def test_3_qscan_is_not_dependency():
    parser = DependencyParser()
    code = "%macro test_qscan(); %let val = %qscan(&str, 1, %str(,)); %mend;"
    refs = parser.parse_references("TEST_QSCAN", code, "test.sas")
    ref_names = [r.referenced_macro for r in refs]
    assert "QSCAN" not in ref_names
    assert "STR" not in ref_names
    assert "LET" not in ref_names
    assert len(refs) == 0

def test_4_quit_is_not_dependency():
    parser = DependencyParser()
    code = "%macro test_quit(); proc sql; quit; %quit; %mend;"
    refs = parser.parse_references("TEST_QUIT", code, "test.sas")
    ref_names = [r.referenced_macro for r in refs]
    assert "QUIT" not in ref_names
    assert len(refs) == 0

def test_5_all_four_false_dependencies_ignored():
    parser = DependencyParser()
    code = """
    %macro util_chkvars();
        %do i = 1 %to 10;
            %do %while(&i < 5);
                %let var = %qscan(&list, &i);
                %quit;
            %end;
        %end;
    %mend util_chkvars;
    """
    refs = parser.parse_references("UTIL_CHKVARS", code, "test.sas")
    assert len(refs) == 0

def test_6_real_nested_macro_call_still_produces_dependency():
    parser = DependencyParser()
    code = "%macro outer(); %inner() %mend outer;"
    refs = parser.parse_references("OUTER", code, "test.sas")
    assert len(refs) == 1
    assert refs[0].referenced_macro == "INNER"

    freg = ProjectFileRegistry()
    pf_a = freg.register_file("a.sas", code)
    pf_b = freg.register_file("b.sas", "%macro inner(); %mend;")

    mreg = MacroRegistry()
    mreg.scan_file(pf_a)
    mreg.scan_file(pf_b)

    builder = DependencyGraphBuilder()
    graph = builder.build_graph(freg.all_files(), mreg)
    edge_pairs = [(e.caller, e.dependency) for e in graph.edges if e.dependency_type == DependencyType.MACRO_CALL]
    assert ("OUTER", "INNER") in edge_pairs

def test_7_mixed_case_builtins_ignored():
    parser = DependencyParser()
    code = "%macro test_case(); %qscan() %QSCAN() %QScan() %to %TO %To %while %WHILE %Quit %QUIT %mend;"
    refs = parser.parse_references("TEST_CASE", code, "test.sas")
    assert len(refs) == 0

def test_8_user_defined_macro_resembling_tokens_detected():
    parser = DependencyParser()
    code = "%macro test_custom(); %my_to_func() %check_while() %custom_qscan() %mend;"
    refs = parser.parse_references("TEST_CUSTOM", code, "test.sas")
    ref_names = [r.referenced_macro for r in refs]
    assert "MY_TO_FUNC" in ref_names
    assert "CHECK_WHILE" in ref_names
    assert "CUSTOM_QSCAN" in ref_names

def test_9_include_dependency_behavior_unchanged():
    builder = DependencyGraphBuilder()
    freg = ProjectFileRegistry()
    freg.register_file("main.sas", '%include "sub.sas";')
    freg.register_file("sub.sas", "data test; run;")
    mreg = MacroRegistry()
    graph = builder.build_graph(freg.all_files(), mreg)
    inc_edges = [e for e in graph.edges if e.dependency_type == DependencyType.INCLUDE]
    assert len(inc_edges) == 1
    assert inc_edges[0].caller == "main.sas"
    assert inc_edges[0].dependency == "sub.sas"

def test_10_circular_dependency_detection_unchanged():
    freg = ProjectFileRegistry()
    pf1 = freg.register_file("a.sas", "%macro m1(); %m2() %mend;")
    pf2 = freg.register_file("b.sas", "%macro m2(); %m1() %mend;")
    mreg = MacroRegistry()
    mreg.scan_file(pf1)
    mreg.scan_file(pf2)

    builder = DependencyGraphBuilder()
    graph = builder.build_graph(freg.all_files(), mreg)
    resolver = DependencyResolver()
    res = resolver.resolve(graph, mreg, freg)
    assert res.status == ResolutionStatus.CIRCULAR_DEPENDENCY

def test_11_duplicate_definition_detection_unchanged():
    freg = ProjectFileRegistry()
    pf1 = freg.register_file("file1.sas", "%macro dup(); %mend;")
    pf2 = freg.register_file("file2.sas", "%macro dup(); %mend;")
    mreg = MacroRegistry()
    mreg.scan_file(pf1)
    mreg.scan_file(pf2)

    builder = DependencyGraphBuilder()
    graph = builder.build_graph(freg.all_files(), mreg)
    resolver = DependencyResolver()
    res = resolver.resolve(graph, mreg, freg)
    assert res.status == ResolutionStatus.DUPLICATE_DEFINITION

def test_12_missing_user_macro_detection_unchanged():
    freg = ProjectFileRegistry()
    pf1 = freg.register_file("file1.sas", "%macro caller(); %missing_macro() %mend;")
    mreg = MacroRegistry()
    mreg.scan_file(pf1)

    builder = DependencyGraphBuilder()
    graph = builder.build_graph(freg.all_files(), mreg)
    resolver = DependencyResolver()
    res = resolver.resolve(graph, mreg, freg)
    assert res.status == ResolutionStatus.UNRESOLVED
    assert any(ref.referenced_macro == "MISSING_MACRO" for ref in res.missing_dependencies)

def test_13_single_file_conversion_behavior_unchanged():
    from app import is_meaningful_sas_source
    sas_code = "data WORK.TEST; set SDTM.DM; run;"
    assert is_meaningful_sas_source(sas_code) is True

def test_14_macro_only_conversion_behavior_unchanged():
    from app import is_meaningful_sas_source
    from macro_converter import parse_sas_source
    sas_code = "%macro test(); proc print data=a; run; %mend;"
    parsed = parse_sas_source(sas_code)
    assert is_meaningful_sas_source(sas_code, parsed) is True

def test_15_real_large_macro_regression_phase_9_21():
    code1 = """
    %macro gen_tp_join_adsl();
        %do i = 1 %to 5;
            %let item = %qscan(&list, &i);
            %quit;
        %end;
    %mend gen_tp_join_adsl;
    """
    code2 = """
    %macro util_chkvars();
        %do %while(&x > 0);
            %gen_tp_join_adsl()
        %end;
    %mend util_chkvars;
    """
    freg = ProjectFileRegistry()
    pf1 = freg.register_file("macro1.sas", code1)
    pf2 = freg.register_file("macro2.sas", code2)
    mreg = MacroRegistry()
    mreg.scan_file(pf1)
    mreg.scan_file(pf2)

    builder = DependencyGraphBuilder()
    graph = builder.build_graph(freg.all_files(), mreg)
    resolver = DependencyResolver()
    res = resolver.resolve(graph, mreg, freg)

    # All dependencies should resolve cleanly with ZERO false dependencies
    assert res.status == ResolutionStatus.RESOLVED
    assert len(res.missing_dependencies) == 0
