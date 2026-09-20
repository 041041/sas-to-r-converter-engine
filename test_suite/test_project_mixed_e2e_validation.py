"""
test_suite/test_project_mixed_e2e_validation.py
─────────────────────────────────────────────────
Automated end-to-end validation tests for Phase 9.18 Realistic Mixed SAS Project.
Verifies internal consistency across ProjectContext, DependencyGraph, Resolver,
AST, Lineage, R Conversion, Structural Validation, and Modernization Report.
"""

import os
import pytest
from project_engine import (
    ProjectAnalyzer,
    ProjectContext,
    ResolutionStatus,
    DependencyType,
    ProjectValidator,
    ProgramClassifier,
    ProgramType
)
from sas_step_converter import SASStepConverter
from doc_generator import DocumentationGenerator, validate_generated_r_code


FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "project_dependency_cases")


def load_project_9_files() -> list[tuple[str, str]]:
    dir_path = os.path.join(FIXTURE_DIR, "project_9_mixed_e2e")
    files = []
    for fname in sorted(os.listdir(dir_path)):
        if fname.endswith(".sas"):
            fpath = os.path.join(dir_path, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                files.append((fname, f.read()))
    return files


def test_e2e_mixed_project_analysis_and_graph():
    files = load_project_9_files()
    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project(files, main_filename="main.sas")

    # 1. Status and counts
    res = ctx.resolution_result
    assert res.status == ResolutionStatus.RESOLVED
    assert len(ctx.project_files) == 5
    assert len(ctx.macro_registry) == 2

    # 2. Dependency edges verification
    graph = ctx.dependency_graph
    inc_edges = [e for e in graph.edges if e.dependency_type == DependencyType.INCLUDE]
    macro_edges = [e for e in graph.edges if e.dependency_type == DependencyType.MACRO_CALL]

    assert len(inc_edges) == 2  # main -> setup.sas, main -> formats.sas
    assert len(macro_edges) >= 3 # main -> MACRO_A, setup.sas -> MACRO_UTIL, MACRO_A -> MACRO_UTIL

    # 3. Structural hierarchy
    main_deps = set(graph.adjacency.get("main.sas", []))
    assert {"setup.sas", "formats.sas", "MACRO_A"}.issubset(main_deps)

    setup_deps = set(graph.adjacency.get("setup.sas", []))
    assert "MACRO_UTIL" in setup_deps

    macro_a_deps = set(graph.adjacency.get("MACRO_A", []))
    assert "MACRO_UTIL" in macro_a_deps

    # 4. Topological order (dependencies visit before callers)
    order = ctx.dependency_order
    assert order.index("MACRO_UTIL") < order.index("setup.sas")
    assert order.index("MACRO_UTIL") < order.index("MACRO_A")
    assert order.index("setup.sas") < order.index("main.sas")
    assert order.index("formats.sas") < order.index("main.sas")
    assert order.index("MACRO_A") < order.index("main.sas")


def test_e2e_deterministic_ordering_ten_runs():
    files = load_project_9_files()
    analyzer = ProjectAnalyzer()
    first_order = None

    for _ in range(10):
        ctx = analyzer.analyze_project(files, main_filename="main.sas")
        order = ctx.dependency_order
        if first_order is None:
            first_order = order
        else:
            assert order == first_order, "Resolution order must be 100% deterministic"


def test_e2e_missing_include_detection():
    files = load_project_9_files()
    # Add a file with missing include
    files.append(("caller.sas", '%include "missing_file.sas";'))
    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project(files, main_filename="main.sas")

    assert ctx.resolution_result.status == ResolutionStatus.UNRESOLVED
    assert len(ctx.resolution_result.missing_includes) == 1
    inc = ctx.resolution_result.missing_includes[0]
    assert inc.caller_file == "caller.sas"
    assert inc.normalized_filename == "missing_file.sas"


def test_e2e_circular_dependency_detection():
    files = [
        ("A.sas", '%include "B.sas";'),
        ("B.sas", '%include "A.sas";')
    ]
    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project(files, main_filename="A.sas")

    assert ctx.resolution_result.status == ResolutionStatus.CIRCULAR_DEPENDENCY
    assert len(ctx.resolution_result.circular_paths) > 0


def test_e2e_duplicate_macro_detection():
    files = [
        ("f1.sas", "%macro DUP; data a; run; %mend;"),
        ("f2.sas", "%macro DUP; data b; run; %mend;")
    ]
    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project(files, main_filename="f1.sas")

    assert ctx.resolution_result.status == ResolutionStatus.DUPLICATE_DEFINITION
    assert "DUP" in ctx.resolution_result.duplicate_definitions


def test_e2e_project_classification():
    files = load_project_9_files()
    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project(files, main_filename="main.sas")

    classifier = ProgramClassifier()
    p_type = classifier.classify_context(ctx)
    assert p_type == ProgramType.MIXED_PROGRAM


def test_e2e_conversion_and_report_consistency():
    files = load_project_9_files()
    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project(files, main_filename="main.sas")

    # Combine supporting content + main content for full conversion
    converter = SASStepConverter()
    full_sas = "\n".join(ctx.ordered_supporting_content + [ctx.main_program_content])
    conv_result = converter.convert_program(full_sas)

    assert conv_result is not None
    assert len(conv_result.converted_steps) > 0

    # Structural R Validation
    r_code = conv_result.full_optimized_r
    r_status, r_issues = validate_generated_r_code(r_code)
    assert r_status == "VALID_R"
    assert len(r_issues) == 0

    # Modernization Document & Report Generation
    doc = DocumentationGenerator().generate_document(
        result=conv_result,
        program_name="Project_9_Mixed",
        project_context=ctx
    )

    assert doc.project_metrics is not None
    pm = doc.project_metrics
    assert pm["files_count"] == 5
    assert pm["macros_count"] == 2
    assert pm["macro_dependencies_count"] == 3
    assert pm["include_dependencies_count"] == 2
    assert pm["resolved_count"] == len(ctx.dependency_order)

    # Validator summary check
    val_summary = ProjectValidator().validate(ctx)
    assert val_summary["is_valid"] is True
    assert val_summary["macro_dependencies_count"] == 3
    assert val_summary["include_dependencies_count"] == 2

    # Tree view check
    tree_view = ProjectValidator().format_tree_view(ctx)
    assert "📦 main.sas" in tree_view
    assert "📄 setup.sas" in tree_view
    assert "📄 formats.sas" in tree_view
    assert "🧩 MACRO_A" in tree_view
    assert "🧩 MACRO_UTIL" in tree_view
