"""
test_suite/test_phase9_19_conversion_quality.py
──────────────────────────────────────────────────
Phase 9.19 — Conversion Quality & User-Friendly Validation Test Suite.
Verifies all 13 quality summary scenarios and metric consistency.
"""

import pytest
from project_engine.quality import (
    QualityStatus,
    ConfidenceBand,
    QualitySummary,
    evaluate_quality_summary
)
from project_engine.analyzer import ProjectAnalyzer
from project_engine.validation import ProjectValidator
from doc_generator import DocumentationGenerator, validate_generated_r_code
from sas_step_converter import SASStepConverter, ConvertedStepResult, ProgramConversionResult


def test_scenario_1_successful_simple_conversion():
    """1. Successful simple conversion -> SUCCESS status, high/moderate confidence, valid R."""
    sas_code = "data target; set source; where age > 30; run;"
    converter = SASStepConverter()
    result = converter.convert_program(sas_code)

    summary = evaluate_quality_summary(conversion_result=result, r_code=result.full_optimized_r)
    assert summary.status == QualityStatus.SUCCESS
    assert summary.status_label == "✅ Conversion Complete"
    assert summary.confidence_band in (ConfidenceBand.HIGH, ConfidenceBand.MODERATE)
    assert summary.confidence_percentage >= 80
    assert summary.r_validation_status == "VALID_R"
    assert summary.r_validation_label == "✅ Passed"
    assert len(summary.review_items) == 0


def test_scenario_2_successful_macro_conversion():
    """2. Successful macro conversion -> SUCCESS status."""
    sas_code = "%macro calc(in=, out=); data &out; set &in; run; %mend calc; %calc(in=a, out=b);"
    converter = SASStepConverter()
    result = converter.convert_program(sas_code)

    summary = evaluate_quality_summary(conversion_result=result, r_code=result.full_optimized_r)
    assert summary.status in (QualityStatus.SUCCESS, QualityStatus.SUCCESS_WITH_REVIEW)
    assert summary.confidence_percentage >= 70
    assert "Macro Definitions" in summary.converted_counts or "DATA Steps" in summary.converted_counts


def test_scenario_3_successful_multi_file_project():
    """3. Successful multi-file project -> Fully Resolved status."""
    files = [
        ("main.sas", "%include 'setup.sas'; %util;"),
        ("setup.sas", "%macro util; proc sort data=a; by id; run; %mend util;"),
    ]
    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project(files, main_filename="main.sas")
    ProjectValidator().validate(ctx)

    converter = SASStepConverter()
    result = converter.convert_program(ctx.main_program_content)

    summary = evaluate_quality_summary(conversion_result=result, project_context=ctx, r_code=result.full_optimized_r)
    assert summary.is_project is True
    assert summary.files_count == 2
    assert "Fully Resolved" in summary.project_resolution_label
    assert summary.status in (QualityStatus.SUCCESS, QualityStatus.SUCCESS_WITH_REVIEW)


def test_scenario_4_project_with_manual_review_items():
    """4. Project with manual review items -> SUCCESS_WITH_REVIEW status."""
    sas_code = "proc format; value agefmt 18-30='Young'; run;"
    converter = SASStepConverter()
    result = converter.convert_program(sas_code)
    result.overall_confidence = 0.85
    # Inject a manual review item
    result.converted_steps[0].review_items.append("PROC FORMAT requires manual review")

    summary = evaluate_quality_summary(conversion_result=result, r_code=result.full_optimized_r)
    assert summary.status == QualityStatus.SUCCESS_WITH_REVIEW
    assert summary.status_label == "⚠ Review Required"
    assert "PROC FORMAT requires manual review" in summary.review_items


def test_scenario_5_invalid_generated_r():
    """5. Invalid generated R code -> R_REVIEW_REQUIRED/R_INVALID, status not SUCCESS."""
    invalid_r = "b <- &unresolved_var + 1"
    status, issues = validate_generated_r_code(invalid_r)
    assert status == "R_REVIEW_REQUIRED"
    assert len(issues) > 0

    summary = evaluate_quality_summary(r_code=invalid_r)
    assert summary.status != QualityStatus.SUCCESS
    assert summary.r_validation_status == "R_REVIEW_REQUIRED"
    assert len(summary.r_issues) > 0


def test_scenario_6_partial_conversion():
    """6. Partial conversion when confidence is lower or unresolved constructs exist."""
    sas_code = "data out; set in; run;"
    converter = SASStepConverter()
    result = converter.convert_program(sas_code)
    result.overall_confidence = 0.55  # 55% confidence

    summary = evaluate_quality_summary(conversion_result=result, r_code=result.full_optimized_r)
    assert summary.status == QualityStatus.PARTIAL
    assert summary.status_label == "⚡ Partial Conversion"
    assert summary.confidence_band == ConfidenceBand.REVIEW_RECOMMENDED


def test_scenario_7_failed_conversion():
    """7. Failed conversion -> FAILED status and failure reason present."""
    summary = evaluate_quality_summary(conversion_error="Syntax error in SAS script: unexpected token 'END'")
    assert summary.status == QualityStatus.FAILED
    assert summary.status_label == "❌ Conversion Failed"
    assert summary.failure_reason == "Syntax error in SAS script: unexpected token 'END'"
    assert summary.r_validation_status == "R_INVALID"


def test_scenario_8_zero_manual_review_items():
    """8. Zero manual review items -> empty review_items list."""
    r_code = "df <- read_csv('data.csv') %>% filter(age > 30)"
    summary = evaluate_quality_summary(r_code=r_code)
    assert len(summary.review_items) == 0


def test_scenario_9_multiple_manual_review_items():
    """9. Multiple manual review items are deduplicated and summarized."""
    sas_code = "proc format; run; proc print data=a; run;"
    converter = SASStepConverter()
    result = converter.convert_program(sas_code)
    result.overall_confidence = 0.85
    result.converted_steps[0].review_items.extend(["PROC FORMAT requires manual review", "PROC PRINT requires manual review"])

    summary = evaluate_quality_summary(conversion_result=result, r_code=result.full_optimized_r)
    assert len(summary.review_items) >= 2
    assert summary.status == QualityStatus.SUCCESS_WITH_REVIEW


def test_scenario_10_confidence_band_classification():
    """10. Test all confidence band thresholds."""
    b95, e95 = ConfidenceBand.classify(0.95)
    assert b95 == ConfidenceBand.HIGH

    b80, e80 = ConfidenceBand.classify(0.80)
    assert b80 == ConfidenceBand.MODERATE

    b60, e60 = ConfidenceBand.classify(0.60)
    assert b60 == ConfidenceBand.REVIEW_RECOMMENDED

    b30, e30 = ConfidenceBand.classify(0.30)
    assert b30 == ConfidenceBand.LOW


def test_scenario_11_project_resolution_status():
    """11. Unresolved project dependency reflects missing count."""
    files = [
        ("main.sas", "%include 'missing.sas';"),
    ]
    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project(files, main_filename="main.sas")
    ProjectValidator().validate(ctx)

    summary = evaluate_quality_summary(project_context=ctx, r_code="cat('test')")
    assert summary.is_project is True
    assert "Dependencies Resolved" in summary.project_resolution_label


def test_scenario_12_ui_report_metric_consistency():
    """12. UI QualitySummary and Modernization Report use identical metrics."""
    sas_code = "data target; set source; run;"
    converter = SASStepConverter()
    result = converter.convert_program(sas_code)

    summary = evaluate_quality_summary(conversion_result=result, r_code=result.full_optimized_r)
    doc_gen = DocumentationGenerator()
    doc = doc_gen.generate_document(result, final_optimized_r=result.full_optimized_r)

    assert doc.quality_summary is not None
    assert doc.quality_summary.status == summary.status
    assert doc.quality_summary.confidence_percentage == summary.confidence_percentage
    assert doc.overall_confidence == float(summary.confidence_percentage)
    assert doc.quality_summary.r_validation_status == summary.r_validation_status


def test_scenario_13_no_false_success_for_invalid_r():
    """13. Invalid generated R code NEVER returns SUCCESS or SUCCESS_WITH_REVIEW."""
    invalid_r = "data <- &unresolved_var"
    summary = evaluate_quality_summary(r_code=invalid_r)
    assert summary.status not in (QualityStatus.SUCCESS, QualityStatus.SUCCESS_WITH_REVIEW)
    assert summary.status in (QualityStatus.PARTIAL, QualityStatus.FAILED)
