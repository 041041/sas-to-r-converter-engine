"""
project_engine/quality.py
───────────────────────────
Conversion Quality Evaluator and Presentation Engine for Enterprise SAS Modernization Engine.
Produces structured, user-friendly QualitySummary objects for UI rendering and report alignment.
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class QualityStatus(str, Enum):
    SUCCESS = "SUCCESS"
    SUCCESS_WITH_REVIEW = "SUCCESS_WITH_REVIEW"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"

    @property
    def label(self) -> str:
        if self == QualityStatus.SUCCESS:
            return "✅ Conversion Complete"
        elif self == QualityStatus.SUCCESS_WITH_REVIEW:
            return "⚠ Review Required"
        elif self == QualityStatus.PARTIAL:
            return "⚡ Partial Conversion"
        else:
            return "❌ Conversion Failed"


class ConfidenceBand(str, Enum):
    HIGH = "High Confidence"
    MODERATE = "Moderate Confidence"
    REVIEW_RECOMMENDED = "Review Recommended"
    LOW = "Low Confidence"

    @classmethod
    def classify(cls, score: float) -> tuple[ConfidenceBand, str]:
        # score is 0.0 to 1.0 or 0 to 100
        pct = score * 100.0 if score <= 1.0 else score
        if pct >= 90.0:
            return cls.HIGH, "Most SAS logic was converted automatically with no unresolved structural issues."
        elif pct >= 70.0:
            return cls.MODERATE, "Most logic was converted, but some items should be reviewed."
        elif pct >= 50.0:
            return cls.REVIEW_RECOMMENDED, "Part of the logic was converted, but several constructs need review."
        else:
            return cls.LOW, "Significant parts of the SAS program require manual conversion or review."


@dataclass
class QualitySummary:
    status: QualityStatus
    status_label: str
    confidence_score: float
    confidence_percentage: int
    confidence_band: ConfidenceBand
    confidence_explanation: str
    r_validation_status: str
    r_validation_label: str
    r_validation_message: str
    r_issues: list[str] = field(default_factory=list)

    # Project metrics
    is_project: bool = False
    files_count: int = 1
    main_program: Optional[str] = None
    macros_count: int = 0
    macro_deps_count: int = 0
    include_deps_count: int = 0
    resolved_count: int = 0
    total_dependencies: int = 0
    project_resolution_label: str = "✅ Fully Resolved"

    # Converted items breakdown
    converted_counts: dict[str, int] = field(default_factory=dict)
    review_items: list[str] = field(default_factory=list)
    unsupported_items: list[str] = field(default_factory=list)

    failure_reason: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "status_label": self.status_label,
            "confidence_score": self.confidence_score,
            "confidence_percentage": self.confidence_percentage,
            "confidence_band": self.confidence_band.value,
            "confidence_explanation": self.confidence_explanation,
            "r_validation_status": self.r_validation_status,
            "r_validation_label": self.r_validation_label,
            "r_validation_message": self.r_validation_message,
            "r_issues": self.r_issues,
            "is_project": self.is_project,
            "files_count": self.files_count,
            "main_program": self.main_program,
            "macros_count": self.macros_count,
            "macro_deps_count": self.macro_deps_count,
            "include_deps_count": self.include_deps_count,
            "resolved_count": self.resolved_count,
            "total_dependencies": self.total_dependencies,
            "project_resolution_label": self.project_resolution_label,
            "converted_counts": self.converted_counts,
            "review_items": self.review_items,
            "unsupported_items": self.unsupported_items,
            "failure_reason": self.failure_reason,
        }


def evaluate_quality_summary(
    conversion_result: Optional[Any] = None,
    project_context: Optional[Any] = None,
    r_code: Optional[str] = None,
    conversion_error: Optional[str] = None
) -> QualitySummary:
    """
    Evaluates pipeline conversion results, project context, and R validation status
    to produce a unified, user-friendly QualitySummary object.
    """
    from doc_generator import validate_generated_r_code

    # 1. R Code Validation
    r_text = r_code or ""
    if not r_text and conversion_result and hasattr(conversion_result, "full_optimized_r"):
        r_text = conversion_result.full_optimized_r or ""

    if conversion_error or not r_text.strip():
        r_val_status = "R_INVALID"
        r_issues = [conversion_error] if conversion_error else ["No generated R code available."]
    else:
        r_val_status, r_issues = validate_generated_r_code(r_text)

    # 2. Project Metrics
    is_project = False
    files_count = 1
    main_prog = None
    macros_cnt = 0
    macro_deps_cnt = 0
    inc_deps_cnt = 0
    resolved_cnt = 0
    total_deps = 0
    proj_label = "✅ Fully Resolved"

    if project_context:
        p_files = getattr(project_context, "project_files", {})
        m_reg = getattr(project_context, "macro_registry", {})
        files_count = len(p_files) or 1
        main_prog = getattr(project_context, "main_program_file", None)
        macros_cnt = len(m_reg)

        graph = getattr(project_context, "dependency_graph", None)
        if graph and hasattr(graph, "edges"):
            edges = graph.edges
            total_deps = len(edges)
            macro_deps_cnt = len([e for e in edges if str(getattr(e, "dependency_type", "")).upper().endswith("MACRO_CALL")])
            inc_deps_cnt = len([e for e in edges if str(getattr(e, "dependency_type", "")).upper().endswith("INCLUDE")])

        is_project = len(p_files) > 1 or len(m_reg) > 0 or total_deps > 0

        res_res = getattr(project_context, "resolution_result", None)
        if res_res:
            res_order = getattr(res_res, "resolution_order", [])
            resolved_cnt = len(res_order)
            res_status = getattr(res_res, "status", None)
            status_str = res_status.value if hasattr(res_status, "value") else str(res_status or "")
            if status_str == "RESOLVED":
                proj_label = f"✅ Fully Resolved ({resolved_cnt}/{resolved_cnt})"
            else:
                proj_label = f"⚠ {resolved_cnt}/{total_deps if total_deps > 0 else resolved_cnt} Dependencies Resolved"

    elif conversion_result and hasattr(conversion_result, "ast") and conversion_result.ast:
        ast = conversion_result.ast
        macros_cnt = len(getattr(ast, "macros", {}))
        files_count = 1
        resolved_cnt = macros_cnt

    # 3. Confidence Evaluation
    if conversion_result and hasattr(conversion_result, "overall_confidence"):
        raw_conf = conversion_result.overall_confidence
    else:
        raw_conf = 0.95 if (project_context and getattr(project_context, "resolution_result", None) and getattr(project_context.resolution_result, "status", "") == "RESOLVED") else 0.0

    conf_pct = int(raw_conf * 100) if raw_conf <= 1.0 else int(raw_conf)
    conf_band, conf_exp = ConfidenceBand.classify(raw_conf)

    # 4. Review Items & Unsupported Items Collection
    raw_reviews = []
    unsupported = []

    if r_issues:
        raw_reviews.extend(r_issues)

    if conversion_result:
        if hasattr(conversion_result, "converted_steps") and conversion_result.converted_steps:
            for step in conversion_result.converted_steps:
                if hasattr(step, "review_items") and step.review_items:
                    raw_reviews.extend(step.review_items)
                if hasattr(step, "conversion_method") and step.conversion_method == "ManualReview":
                    raw_reviews.append(f"{step.step_name} requires manual review")

        if hasattr(conversion_result, "ast") and conversion_result.ast:
            infra = getattr(conversion_result.ast, "infrastructure", None)
            if infra and hasattr(infra, "review_items") and infra.review_items:
                raw_reviews.extend(infra.review_items)

    if project_context:
        proj_errs = getattr(project_context, "errors", [])
        if proj_errs:
            raw_reviews.extend(proj_errs)

    clean_reviews = []
    seen_rev = set()
    for item in raw_reviews:
        item_str = str(item).strip()
        if not item_str:
            continue
        if item_str.startswith("⚠️"):
            item_str = item_str.lstrip("⚠️").strip()
        if item_str.startswith("💡"):
            item_str = item_str.lstrip("💡").strip()
        if item_str.lower() in seen_rev:
            continue
        seen_rev.add(item_str.lower())
        clean_reviews.append(item_str)

    # 5. Converted Items Breakdown
    converted_counts = {}
    if conversion_result and hasattr(conversion_result, "converted_steps") and conversion_result.converted_steps:
        data_cnt = 0
        proc_cnt = 0
        macro_call_cnt = 0
        for s in conversion_result.converted_steps:
            stype = getattr(s, "step_type", "").upper()
            if stype == "DATA_STEP" or s.step_name.startswith("STEP_") or "DATA " in s.source_sas.upper():
                data_cnt += 1
            elif stype == "PROC_STEP" or "PROC " in s.source_sas.upper():
                proc_cnt += 1
            elif stype == "MACRO_CALL" or "%" in s.step_name:
                macro_call_cnt += 1
            else:
                data_cnt += 1

        if data_cnt > 0:
            converted_counts["DATA Steps"] = data_cnt
        if proc_cnt > 0:
            converted_counts["PROC Steps"] = proc_cnt
        if macro_call_cnt > 0:
            converted_counts["Macro Calls"] = macro_call_cnt

    if macros_cnt > 0:
        converted_counts["Macro Definitions"] = macros_cnt
    if inc_deps_cnt > 0:
        converted_counts["%INCLUDE Directives"] = inc_deps_cnt

    # 6. Overall Status Determination
    if r_val_status == "R_INVALID" or conversion_error or not r_text.strip():
        final_status = QualityStatus.FAILED
        r_val_label = "❌ Failed"
        r_val_msg = "Generated R output is invalid or incomplete."
    elif r_val_status == "R_REVIEW_REQUIRED" or len(clean_reviews) > 0 or (project_context and getattr(project_context.resolution_result, "status", "") != "RESOLVED") or conf_pct < 60:
        if conf_pct >= 60 and r_val_status != "R_INVALID":
            final_status = QualityStatus.SUCCESS_WITH_REVIEW
        else:
            final_status = QualityStatus.PARTIAL

        if r_val_status == "R_REVIEW_REQUIRED":
            r_val_label = "⚠ Requires Review"
            r_val_msg = f"{len(r_issues)} unresolved SAS construct(s) detected in generated R."
        else:
            r_val_label = "✅ Passed"
            r_val_msg = "No unresolved SAS macro variables or unsupported macro syntax detected."
    else:
        final_status = QualityStatus.SUCCESS
        r_val_label = "✅ Passed"
        r_val_msg = "No unresolved SAS macro variables or unsupported macro syntax detected."

    return QualitySummary(
        status=final_status,
        status_label=final_status.label,
        confidence_score=raw_conf,
        confidence_percentage=conf_pct,
        confidence_band=conf_band,
        confidence_explanation=conf_exp,
        r_validation_status=r_val_status,
        r_validation_label=r_val_label,
        r_validation_message=r_val_msg,
        r_issues=r_issues,
        is_project=is_project,
        files_count=files_count,
        main_program=main_prog,
        macros_count=macros_cnt,
        macro_deps_count=macro_deps_cnt,
        include_deps_count=inc_deps_cnt,
        resolved_count=resolved_cnt,
        total_dependencies=total_deps,
        project_resolution_label=proj_label,
        converted_counts=converted_counts,
        review_items=clean_reviews,
        unsupported_items=unsupported,
        failure_reason=conversion_error if final_status == QualityStatus.FAILED else None
    )
