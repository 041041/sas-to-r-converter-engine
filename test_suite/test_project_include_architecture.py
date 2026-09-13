"""
test_suite/test_project_include_architecture.py
─────────────────────────────────────────────────
Automated tests for Phase 9.16 Enterprise SAS Project %INCLUDE & Unified Dependency Architecture.
Tests 12 distinct include, macro, cycle, normalization, report, and backward-compatibility scenarios.
"""

import os
import pytest
from project_engine import (
    ProjectAnalyzer,
    ProjectContext,
    ResolutionStatus,
    DependencyType,
    IncludeParser,
    ProjectValidator
)
from doc_generator import DocumentationGenerator


FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "project_dependency_cases")


def load_fixture_files(subfolder: str) -> list[tuple[str, str]]:
    dir_path = os.path.join(FIXTURE_DIR, subfolder)
    files = []
    for fname in sorted(os.listdir(dir_path)):
        if fname.endswith(".sas"):
            fpath = os.path.join(dir_path, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                files.append((fname, f.read()))
    return files


def test_01_simple_include():
    files = load_fixture_files("project_1_simple_include")
    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project(files, main_filename="main.sas")

    assert ctx.resolution_result.status == ResolutionStatus.RESOLVED
    assert "setup.sas" in ctx.dependency_order
    assert "main.sas" in ctx.dependency_order
    assert ctx.dependency_order.index("setup.sas") < ctx.dependency_order.index("main.sas")

    inc_edges = [e for e in ctx.dependency_graph.edges if e.dependency_type == DependencyType.INCLUDE]
    assert len(inc_edges) == 1
    assert inc_edges[0].caller == "main.sas"
    assert inc_edges[0].dependency == "setup.sas"


def test_02_include_plus_macro():
    files = load_fixture_files("project_2_include_plus_macro")
    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project(files, main_filename="main.sas")

    assert ctx.resolution_result.status == ResolutionStatus.RESOLVED
    dep_types = {e.dependency_type for e in ctx.dependency_graph.edges}
    assert DependencyType.INCLUDE in dep_types
    assert DependencyType.MACRO_CALL in dep_types

    edge_targets = {e.dependency for e in ctx.dependency_graph.edges if e.caller == "main.sas"}
    assert "setup.sas" in edge_targets
    assert "MACRO_A" in edge_targets


def test_03_nested_include():
    files = load_fixture_files("project_3_nested_include")
    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project(files, main_filename="main.sas")

    assert ctx.resolution_result.status == ResolutionStatus.RESOLVED
    assert ctx.dependency_order == ["common.sas", "setup.sas", "main.sas"]


def test_04_include_cycle():
    files = load_fixture_files("project_4_include_cycle")
    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project(files, main_filename="A.sas")

    assert ctx.resolution_result.status == ResolutionStatus.CIRCULAR_DEPENDENCY
    assert len(ctx.resolution_result.circular_paths) > 0
    cycle_path = ctx.resolution_result.circular_paths[0]
    assert "A.sas" in cycle_path
    assert "B.sas" in cycle_path
    assert "C.sas" in cycle_path


def test_05_missing_include():
    files = load_fixture_files("project_5_missing_include")
    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project(files, main_filename="main.sas")

    assert ctx.resolution_result.status == ResolutionStatus.UNRESOLVED
    assert len(ctx.resolution_result.missing_includes) == 1
    missing = ctx.resolution_result.missing_includes[0]
    assert missing.caller_file == "main.sas"
    assert missing.normalized_filename == "missing.sas"


def test_06_include_path_normalization():
    files = load_fixture_files("project_6_include_path_normalization")
    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project(files, main_filename="main.sas")

    assert ctx.resolution_result.status == ResolutionStatus.RESOLVED
    # Nodes should not contain duplicates
    nodes = ctx.dependency_graph.nodes
    assert "setup.sas" in nodes
    assert "./setup.sas" not in nodes
    assert "'. /setup.sas'" not in nodes

    inc_edges = [e for e in ctx.dependency_graph.edges if e.dependency == "setup.sas"]
    assert len(inc_edges) == 1


def test_07_include_macro_plus_executable_code():
    files = load_fixture_files("project_7_include_macro_executable")
    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project(files, main_filename="main.sas")

    assert ctx.resolution_result.status == ResolutionStatus.RESOLVED
    from project_engine.classifier import ProgramClassifier, ProgramType
    classifier = ProgramClassifier()
    p_type = classifier.classify_context(ctx)
    assert p_type == ProgramType.MIXED_PROGRAM

    node_names = set(ctx.dependency_graph.nodes)
    assert {"main.sas", "setup.sas", "MACRO_A", "MACRO_UTIL"}.issubset(node_names)


def test_08_dependency_type_classification():
    files = load_fixture_files("project_7_include_macro_executable")
    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project(files, main_filename="main.sas")

    inc_edges = [e for e in ctx.dependency_graph.edges if e.dependency_type == DependencyType.INCLUDE]
    macro_edges = [e for e in ctx.dependency_graph.edges if e.dependency_type == DependencyType.MACRO_CALL]

    assert len(inc_edges) >= 1
    assert len(macro_edges) >= 2


def test_09_deterministic_resolution():
    files = load_fixture_files("project_8_acceptance")
    analyzer = ProjectAnalyzer()

    first_order = None
    for _ in range(10):
        ctx = analyzer.analyze_project(files, main_filename="main.sas")
        order = ctx.dependency_order
        if first_order is None:
            first_order = order
        else:
            assert order == first_order, "Resolution order must be strictly deterministic"

    # Verify dependency correctness in deterministic order
    assert first_order.index("common.sas") < first_order.index("setup.sas")
    assert first_order.index("setup.sas") < first_order.index("main.sas")
    assert first_order.index("MACRO_UTIL") < first_order.index("MACRO_A")


def test_10_project_context_backward_compatibility():
    # Verify single-file and macro-library conversions still work seamlessly
    macro_lib_files = [
        ("BIG_MACRO.sas", "%macro BIG_MACRO; %MACRO_A; %mend;"),
        ("MACRO_A.sas", "%macro MACRO_A; data work.a; run; %mend;")
    ]
    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project(macro_lib_files, main_filename="BIG_MACRO.sas")

    assert ctx.resolution_result.status == ResolutionStatus.RESOLVED
    assert ctx.dependency_order == ["MACRO_A", "BIG_MACRO"]
    assert ctx.main_program_file == "BIG_MACRO.sas"
    assert len(ctx.macro_registry) == 2


def test_11_report_metrics():
    files = load_fixture_files("project_8_acceptance")
    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project(files, main_filename="main.sas")

    doc = DocumentationGenerator().generate_document(
        project_context=ctx,
        program_name="Main_Project"
    )

    pm = doc.project_metrics
    assert pm is not None
    assert pm["files_count"] == 5
    assert pm["macros_count"] == 2
    assert pm["macro_dependencies_count"] == 2
    assert pm["include_dependencies_count"] == 2


def test_12_acceptance_test():
    files = load_fixture_files("project_8_acceptance")
    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project(files, main_filename="main.sas")

    val_summary = ProjectValidator().validate(ctx)
    assert val_summary["is_valid"] is True
    assert val_summary["files_count"] == 5
    assert val_summary["macros_count"] == 2
    assert val_summary["include_dependencies_count"] == 2
    assert val_summary["macro_dependencies_count"] == 2

    # Check tree view formatting
    tree_view = ProjectValidator().format_tree_view(ctx)
    assert "📦 main.sas" in tree_view
    assert "📄 setup.sas" in tree_view
    assert "🧩 MACRO_A" in tree_view
