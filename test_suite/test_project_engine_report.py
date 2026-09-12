"""
test_suite/test_project_engine_report.py
───────────────────────────────────────────
Tests for Phase 9.12 Project Engine & Modernization Report Alignment.
"""

import pytest
from project_engine import ProjectAnalyzer, ProgramClassifier, ProgramType
from doc_generator import DocumentationGenerator, validate_generated_r_code
from doc_renderers import md_renderer


def test_01_macro_only_modernization_report():
    """Verify macro-only program report shows Macro Library and 0 execution steps."""
    sas_code = """
    %macro SIMPLE_MAC(in_ds=, out_ds=);
        data &out_ds;
            set &in_ds;
        run;
    %mend;
    """
    file_tuples = [("SIMPLE_MAC.sas", sas_code)]
    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project(file_tuples, main_filename="SIMPLE_MAC.sas")

    valid_r = """
    simple_mac <- function(in_ds, out_ds) {
        out_ds <- in_ds
        return(out_ds)
    }
    """

    doc_gen = DocumentationGenerator()
    doc = doc_gen.generate_document(
        project_context=ctx,
        final_optimized_r=valid_r,
        program_name="SIMPLE_MAC.sas"
    )

    assert "Macro Library" in doc.program_type or doc.program_type == "MACRO_LIBRARY"
    assert len(doc.step_descriptions) == 0
    assert doc.project_metrics["macros_count"] == 1
    assert doc.overall_confidence == 95.0
    assert doc.r_validation_status == "VALID_R"

    md = md_renderer.render_markdown(doc)
    assert "Program Type**: `Macro Library`" in md or "Program Type**: `MACRO_LIBRARY`" in md
    assert "Discovered Macros**: `1`" in md


def test_02_three_file_macro_project_report():
    """Verify 3-file project report computes all macros across files, dependencies, and resolution status."""
    big_macro = """
    %macro BIG_MACRO(in=, out=);
        %MACRO_A(in=&in, out=WORK.STEP_A);
        %MACRO_B(in=WORK.STEP_A, out=&out);
    %mend;
    """
    macro_a = """
    %macro MACRO_A(in=, out=);
        data &out; set &in; run;
    %mend;
    """
    macro_b = """
    %macro MACRO_B(in=, out=);
        data &out; set &in; run;
    %mend;
    """

    file_tuples = [
        ("BIG_MACRO.sas", big_macro),
        ("MACRO_A.sas", macro_a),
        ("MACRO_B.sas", macro_b)
    ]
    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project(file_tuples, main_filename="BIG_MACRO.sas")

    valid_r = """
    macro_a <- function(in_ds, out_ds) {
        return(in_ds)
    }
    macro_b <- function(in_ds, out_ds) {
        return(in_ds)
    }
    big_macro <- function(in_ds, out_ds) {
        step_a <- macro_a(in_ds = in_ds, out_ds = "WORK.STEP_A")
        res <- macro_b(in_ds = step_a, out_ds = out_ds)
        return(res)
    }
    """

    doc_gen = DocumentationGenerator()
    doc = doc_gen.generate_document(
        project_context=ctx,
        final_optimized_r=valid_r,
        program_name="BIG_MACRO.sas"
    )

    assert "Macro Library" in doc.program_type or doc.program_type == "MACRO_LIBRARY"
    assert doc.project_metrics["macros_count"] == 3
    assert doc.project_metrics["dependencies_count"] == 2
    assert doc.project_metrics["resolved_count"] == 3
    assert len(doc.step_descriptions) == 0
    assert doc.overall_confidence == 95.0
    assert doc.r_validation_status == "VALID_R"

    md = md_renderer.render_markdown(doc)
    assert "Discovered Macros**: `3`" in md
    assert "Dependencies**: `2`" in md
    assert "Resolved Dependencies**: `3/3`" in md
    assert "macro_a" in doc.final_optimized_r
    assert "macro_b" in doc.final_optimized_r
    assert "big_macro" in doc.final_optimized_r


def test_03_macro_count_includes_all_project_macros():
    """Verify macro count includes macros from all files in ProjectContext, not just main file."""
    main_code = "%macro MAIN_M(); %SUPP_M(); %mend;"
    supp_code = "%macro SUPP_M(); data test; set in; run; %mend;"

    file_tuples = [("main.sas", main_code), ("supp.sas", supp_code)]
    ctx = ProjectAnalyzer().analyze_project(file_tuples, main_filename="main.sas")

    doc = DocumentationGenerator().generate_document(
        project_context=ctx,
        final_optimized_r="main_m <- function() {}\nsupp_m <- function() {}",
        program_name="main.sas"
    )
    assert doc.project_metrics["macros_count"] == 2
    assert len(doc.macro_summaries) == 2


def test_04_execution_step_count_zero_for_macro_only():
    """Verify execution steps count is 0 for macro-only library."""
    sas_code = "%macro M1(); data a; set b; run; %mend;"
    ctx = ProjectAnalyzer().analyze_project([("m1.sas", sas_code)], main_filename="m1.sas")

    doc = DocumentationGenerator().generate_document(
        project_context=ctx,
        final_optimized_r="m1 <- function() {}",
        program_name="m1.sas"
    )
    assert len(doc.step_descriptions) == 0
    assert "Macro Library" in doc.program_type or doc.program_type == "MACRO_LIBRARY"


def test_05_final_report_r_matches_main_r_output():
    """Verify section 7 final optimized R matches the provided single source of truth."""
    custom_r = "library(tidyverse)\n# Final R Source of Truth\nmy_df <- tibble(a = 1)"
    doc = DocumentationGenerator().generate_document(
        final_optimized_r=custom_r,
        program_name="test.sas"
    )
    assert doc.final_optimized_r == custom_r
    md = md_renderer.render_markdown(doc)
    assert "# Final R Source of Truth" in md


def test_06_unresolved_sas_syntax_detection():
    """Verify validate_generated_r_code detects &var and %macro keywords in generated R."""
    bad_r_code = """
    WORK.STEP_A <- macro_a(&in)
    &out <- macro_b(WORK.STEP_A)
    %macro invalid_in_r;
    """
    status, issues = validate_generated_r_code(bad_r_code)
    assert status == "R_REVIEW_REQUIRED"
    assert any("&in" in iss or "&out" in iss for iss in issues)
    assert any("%MACRO" in iss for iss in issues)


def test_07_confidence_reduction_when_final_r_invalid():
    """Verify confidence drops to <=45% and manual review item is added when generated R has unresolved SAS syntax."""
    bad_r_code = "df <- filter(data, col == &unresolved_var)"
    doc = DocumentationGenerator().generate_document(
        final_optimized_r=bad_r_code,
        program_name="test.sas"
    )
    assert doc.r_validation_status == "R_REVIEW_REQUIRED"
    assert doc.overall_confidence <= 45.0
    assert any("Unresolved SAS macro variable reference" in item for item in doc.manual_review_items)


def test_08_mixed_program_report():
    """Verify mixed program reports EXECUTABLE_PROGRAM or MIXED_PROGRAM with step descriptions and macros."""
    sas_code = """
    %macro UTIL(in=);
        data work.u; set &in; run;
    %mend;
    data work.main;
        set work.raw;
    run;
    """
    ctx = ProjectAnalyzer().analyze_project([("mixed.sas", sas_code)], main_filename="mixed.sas")
    doc = DocumentationGenerator().generate_document(
        project_context=ctx,
        final_optimized_r="util <- function(in) {}\nmain <- raw",
        program_name="mixed.sas",
        pipeline_results=[{"name": "MAIN", "step": "data work.main; set work.raw; run;", "r_code": "main <- raw"}]
    )
    assert "Mixed Program" in doc.program_type or doc.program_type == "MIXED_PROGRAM"
    assert len(doc.step_descriptions) == 1
    assert doc.project_metrics["macros_count"] == 1


def test_09_project_lineage_for_macro_library():
    """Verify project lineage provides clear non-empty dataset markers for macro library."""
    doc = DocumentationGenerator().generate_document(
        program_type=ProgramType.MACRO_LIBRARY,
        final_optimized_r="m <- function() {}",
        program_name="lib.sas"
    )
    assert doc.input_datasets == ["Unknown / Macro Input"]
    assert doc.output_datasets == ["Modernized R Functions"]


def test_10_dependency_metrics_in_rendered_markdown():
    """Verify dependency metrics are cleanly rendered in markdown output."""
    file_tuples = [
        ("MAIN.sas", "%macro MAIN(); %SUB(); %mend;"),
        ("SUB.sas", "%macro SUB(); %mend;")
    ]
    ctx = ProjectAnalyzer().analyze_project(file_tuples, main_filename="MAIN.sas")
    doc = DocumentationGenerator().generate_document(
        project_context=ctx,
        final_optimized_r="sub <- function() {}\nmain <- function() { sub() }",
        program_name="MAIN.sas"
    )
    md = md_renderer.render_markdown(doc)
    assert "## 4. Macro Analysis" in md
    assert "Total Discovered Macros**: `2`" in md
    assert "Total Dependency Edges**: `1`" in md
    assert "Dependency Resolution**: `2/2`" in md
