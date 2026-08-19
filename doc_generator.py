"""
doc_generator.py
────────────────
Modernization Documentation Core Engine for Enterprise SAS Modernization Engine.
Generates the structured 10-section Modernization Document model.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional
from sas_step_converter import ProgramConversionResult


@dataclass
class MappingRow:
    sas_construct: str
    r_equivalent: str
    confidence: str  # High, Medium, Low
    method: str      # RuleEngine, LLMFallback, ManualReview


@dataclass
class ModernizationDocument:
    # 1. Executive Summary
    executive_summary: str
    # 2. Original SAS Metadata
    program_name: str
    input_datasets: list[str]
    output_datasets: list[str]
    libraries: dict[str, str]
    external_dependencies: list[str]
    # 3. SAS Logic Analysis
    step_descriptions: list[dict[str, Any]]
    # 4. Macro Analysis
    macro_summaries: list[dict[str, Any]]
    # 5. SAS -> R Mapping Table
    mapping_table: list[MappingRow]
    # 6. Generated R Architecture & Optimization Metrics
    optimization_summary: dict[str, Any]
    # 7. Generated R Code
    final_optimized_r: str
    # 8. Validation Results
    validation_status: str
    validation_details: str
    # 9. Manual Review Items
    manual_review_items: list[str]
    # 10. Conversion Confidence
    overall_confidence: float
    confidence_rationale: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "executive_summary": self.executive_summary,
            "program_name": self.program_name,
            "input_datasets": self.input_datasets,
            "output_datasets": self.output_datasets,
            "libraries": self.libraries,
            "external_dependencies": self.external_dependencies,
            "step_descriptions": self.step_descriptions,
            "macro_summaries": self.macro_summaries,
            "mapping_table": [
                {
                    "sas_construct": r.sas_construct,
                    "r_equivalent": r.r_equivalent,
                    "confidence": r.confidence,
                    "method": r.method
                } for r in self.mapping_table
            ],
            "optimization_summary": self.optimization_summary,
            "final_optimized_r": self.final_optimized_r,
            "validation_status": self.validation_status,
            "validation_details": self.validation_details,
            "manual_review_items": self.manual_review_items,
            "overall_confidence": self.overall_confidence,
            "confidence_rationale": self.confidence_rationale,
        }


class DocumentationGenerator:
    """
    Constructs a ModernizationDocument from a ProgramConversionResult.
    """

    def generate_document(
        self,
        result: ProgramConversionResult,
        program_name: str = "SAS_Program_Modernization",
        validation_res: Optional[dict[str, Any]] = None
    ) -> ModernizationDocument:

        ast = result.ast
        graph = result.dependency_graph
        infra = result.infra_config

        # 1. Executive Summary
        exec_summary = (
            f"Automated modernization analysis for '{program_name}'. "
            f"The program contains {len(ast.steps)} execution step(s) and {len(ast.macros)} macro definition(s). "
            f"Achieved an overall conversion confidence of {result.overall_confidence}% with a "
            f"{result.total_optimization_metrics.line_reduction_pct:.1f}% reduction in R code line count."
        )

        # 2. Metadata
        all_inputs = list(set([ds for s in ast.steps for ds in s.input_datasets]))
        all_outputs = list(set([ds for s in ast.steps for ds in s.output_datasets]))

        # 3. Logic Analysis
        step_descs = []
        for s in result.converted_steps:
            step_descs.append({
                "step_index": s.step_index,
                "name": s.step_name,
                "type": s.step_type,
                "sas_snippet": s.source_sas[:150] + "..." if len(s.source_sas) > 150 else s.source_sas,
                "method": s.conversion_method,
                "confidence": f"{s.confidence_score*100:.0f}%"
            })

        # 4. Macro Summaries
        macro_sums = []
        for m_name, m_ir in ast.macros.items():
            macro_sums.append({
                "name": m_name,
                "params": [p.name for p in m_ir.parameters],
                "nested_calls": m_ir.nested_macros,
                "complexity_score": m_ir.complexity_score,
                "has_dynamic_naming": m_ir.has_dynamic_naming
            })

        # 5. Mapping Table
        mapping = []
        for s in result.converted_steps:
            conf_str = "High" if s.confidence_score >= 0.85 else ("Medium" if s.confidence_score >= 0.60 else "Low")
            mapping.append(MappingRow(
                sas_construct=s.step_name,
                r_equivalent=s.optimized_r_code[:100].replace('\n', ' ') + "...",
                confidence=conf_str,
                method=s.conversion_method
            ))

        # 6. Optimization Summary
        opt_summary = result.total_optimization_metrics.to_dict()

        # 8. Validation Status
        if validation_res:
            val_status = "PASSED ✅" if validation_res.get("match") else "MISMATCH ❌"
            val_details = str(validation_res.get("details", "No detailed diff available."))
        else:
            val_status = "PENDING EXECUTION ⚪"
            val_details = "R code generated and optimized. Upload expected CSV/Excel to run full numerical validation."

        # 9. Manual Review Items
        manual_items = list(infra.manual_review_items)
        for s in result.converted_steps:
            if s.conversion_method == "ManualReviewRequired":
                manual_items.append(f"Unresolved step requires manual translation: {s.step_name}")

        # 10. Rationale
        rationale = (
            f"High confidence for standard DATA steps, PROC SORT, PROC FREQ, and %LET statements. "
            f"Flagged {len(manual_items)} infrastructure/connection item(s) for manual review."
        )

        return ModernizationDocument(
            executive_summary=exec_summary,
            program_name=program_name,
            input_datasets=all_inputs,
            output_datasets=all_outputs,
            libraries=infra.lib_mappings,
            external_dependencies=infra.manual_review_items,
            step_descriptions=step_descs,
            macro_summaries=macro_sums,
            mapping_table=mapping,
            optimization_summary=opt_summary,
            final_optimized_r=result.full_optimized_r,
            validation_status=val_status,
            validation_details=val_details,
            manual_review_items=manual_items,
            overall_confidence=result.overall_confidence,
            confidence_rationale=rationale
        )
