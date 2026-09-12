"""
doc_generator.py
────────────────
Modernization Documentation Core Engine for Enterprise SAS Modernization Engine.
Generates the structured 10-section Modernization Document model.
Consumes ProjectContext, ProgramClassifier, and final generated R code.
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from sas_step_converter import ProgramConversionResult
from project_engine.models import ProjectContext
from project_engine.classifier import ProgramClassifier, ProgramType
from r_optimizer import ROptimizer, OptimizationMetrics


def validate_generated_r_code(r_code: str) -> tuple[str, list[str]]:
    """
    Validates generated R code for unresolved SAS macro syntax or invalid constructs.
    Returns (status, list_of_issues).
    Statuses: "VALID_R", "R_REVIEW_REQUIRED", "R_INVALID"
    """
    issues = []
    if not r_code or not r_code.strip():
        return "R_INVALID", ["Generated R code is empty."]

    lines = r_code.splitlines()
    for idx, line in enumerate(lines, 1):
        code_part = line.split('#')[0]
        # Match unresolved &var or &&var
        unresolved_vars = re.findall(r'&+([a-zA-Z_]\w*)', code_part)
        if unresolved_vars:
            for uv in set(unresolved_vars):
                issues.append(f"Unresolved SAS macro variable reference: &{uv} (line {idx})")

        # Match unresolved SAS macro statement keywords
        unresolved_statements = re.findall(r'%(macro|mend|let|put|include)\b', code_part, re.I)
        if unresolved_statements:
            for us in set(unresolved_statements):
                issues.append(f"Unresolved SAS macro statement: %{us.upper()} (line {idx})")

    if issues:
        return "R_REVIEW_REQUIRED", issues
    return "VALID_R", []


@dataclass
class MappingRow:
    sas_construct: str
    r_equivalent: str
    confidence: str  # High, Medium, Low
    method: str      # RuleEngine, LLMFallback, ManualReview, MacroLibraryConverter


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
    # Extended Project Engine Metadata
    program_type: str = "Executable Program"
    project_metrics: Optional[dict[str, Any]] = None
    r_validation_status: str = "VALID_R"

    def to_dict(self) -> dict[str, Any]:
        return {
            "executive_summary": self.executive_summary,
            "program_name": self.program_name,
            "program_type": self.program_type,
            "project_metrics": self.project_metrics,
            "r_validation_status": self.r_validation_status,
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
    Constructs a ModernizationDocument consuming ProgramConversionResult and ProjectContext.
    """

    def generate_document(
        self,
        result: Optional[ProgramConversionResult] = None,
        program_name: str = "SAS_Program_Modernization",
        validation_res: Optional[dict[str, Any]] = None,
        project_context: Optional[ProjectContext] = None,
        final_optimized_r: Optional[str] = None,
        program_type: Optional[Any] = None,
        pipeline_results: Optional[list[dict[str, Any]]] = None
    ) -> ModernizationDocument:

        # 1. Classify Program Type
        if program_type:
            prog_type_str = program_type.value if hasattr(program_type, "value") else str(program_type)
        elif project_context and project_context.main_program_content:
            prog_type = ProgramClassifier().classify_source(project_context.main_program_content)
            prog_type_str = prog_type.value
        else:
            prog_type_str = "Executable Program"

        is_macro_lib = ("macro" in prog_type_str.lower() and "library" in prog_type_str.lower()) or prog_type_str == "MACRO_LIBRARY"

        # 2. Extract AST / Infra if result is present
        ast = result.ast if result else None
        infra = result.infra_config if result else None

        # 3. Macro Metrics & Summaries from ProjectContext or AST
        macro_sums = []
        project_metrics = None

        if project_context:
            all_macros = project_context.macro_registry
            macros_count = len(all_macros)
            dep_edges = len(project_context.dependency_graph.edges)
            res_count = len(project_context.resolution_result.resolution_order)

            project_metrics = {
                "files_count": len(project_context.project_files),
                "macros_count": macros_count,
                "dependencies_count": dep_edges,
                "resolved_count": res_count
            }

            for m_name, m_def in all_macros.items():
                params = [p.name if hasattr(p, "name") else str(p) for p in getattr(m_def, "parameters", [])]
                nested = getattr(m_def, "nested_calls", [])
                macro_sums.append({
                    "name": m_name,
                    "params": params,
                    "source_file": getattr(m_def, "source_file", "Main Program"),
                    "nested_calls": nested,
                    "complexity_score": getattr(m_def, "complexity_score", 30.0),
                    "has_dynamic_naming": False
                })
        elif ast and ast.macros:
            macros_count = len(ast.macros)
            dep_edges = 0
            res_count = macros_count

            project_metrics = {
                "files_count": 1,
                "macros_count": macros_count,
                "dependencies_count": dep_edges,
                "resolved_count": res_count
            }

            for m_name, m_ir in ast.macros.items():
                macro_sums.append({
                    "name": m_name,
                    "params": [p.name for p in m_ir.parameters],
                    "source_file": "Main Program",
                    "nested_calls": m_ir.nested_macros,
                    "complexity_score": m_ir.complexity_score,
                    "has_dynamic_naming": m_ir.has_dynamic_naming
                })
        else:
            macros_count = 0
            dep_edges = 0
            res_count = 0

        # 4. Final R Code Selection & Structural Validation
        if final_optimized_r and final_optimized_r.strip():
            final_r_code = final_optimized_r
        elif result:
            final_r_code = result.full_optimized_r
        else:
            final_r_code = "# No generated R code available."

        r_val_status, r_issues = validate_generated_r_code(final_r_code)

        # 5. Optimize Final R Code to ensure consistent optimization metrics
        optimizer = ROptimizer()
        _, opt_metrics = optimizer.optimize(final_r_code)
        opt_summary = opt_metrics.to_dict()

        # 6. Step Descriptions & Construct Mapping
        step_descs = []
        mapping = []

        if is_macro_lib:
            execution_steps_count = 0
            for m in macro_sums:
                mapping.append(MappingRow(
                    sas_construct=f"%{m['name']}",
                    r_equivalent=f"{m['name'].lower()} <- function(...)",
                    confidence="High",
                    method="MacroLibraryConverter"
                ))
        else:
            if result and result.converted_steps:
                for s in result.converted_steps:
                    step_descs.append({
                        "step_index": s.step_index,
                        "name": s.step_name,
                        "type": s.step_type,
                        "sas_snippet": s.source_sas[:150] + "..." if len(s.source_sas) > 150 else s.source_sas,
                        "method": s.conversion_method,
                        "confidence": f"{s.confidence_score*100:.0f}%"
                    })
                    conf_str = "High" if s.confidence_score >= 0.85 else ("Medium" if s.confidence_score >= 0.60 else "Low")
                    mapping.append(MappingRow(
                        sas_construct=s.step_name,
                        r_equivalent=s.optimized_r_code[:100].replace('\n', ' ') + "...",
                        confidence=conf_str,
                        method=s.conversion_method
                    ))
            elif pipeline_results:
                for idx, pr in enumerate(pipeline_results, 1):
                    s_name = pr.get("name", f"Step_{idx}")
                    step_descs.append({
                        "step_index": idx,
                        "name": s_name,
                        "type": "EXECUTION_STEP",
                        "sas_snippet": pr.get("step", "")[:150],
                        "method": "PipelineConverter",
                        "confidence": "90%"
                    })
                    mapping.append(MappingRow(
                        sas_construct=s_name,
                        r_equivalent=pr.get("r_code", "")[:100].replace('\n', ' ') + "...",
                        confidence="High",
                        method="PipelineConverter"
                    ))
            execution_steps_count = len(step_descs)

        # 7. Lineage
        if is_macro_lib:
            all_inputs = ["Unknown / Macro Input"]
            all_outputs = ["Modernized R Functions"]
        else:
            all_inputs = list(set([ds for s in ast.steps for ds in s.input_datasets])) if ast and hasattr(ast, "steps") else []
            all_outputs = list(set([ds for s in ast.steps for ds in s.output_datasets])) if ast and hasattr(ast, "steps") else []

        # 8. Libraries & External Dependencies
        libs = infra.lib_mappings if infra else {}
        manual_items = list(infra.manual_review_items) if infra else []
        for r_issue in r_issues:
            if r_issue not in manual_items:
                manual_items.append(r_issue)

        # 9. Confidence Calculation & Rationale
        base_confidence = result.overall_confidence if result else 95.0

        if r_val_status in ("R_REVIEW_REQUIRED", "R_INVALID"):
            overall_confidence = min(base_confidence, 45.0)
            rationale = (
                f"Confidence reduced to {overall_confidence:.1f}% due to unresolved SAS syntax "
                f"in generated R output ({len(r_issues)} issue(s) flagged for manual review)."
            )
        elif is_macro_lib:
            overall_confidence = 95.0
            rationale = (
                f"High confidence (95.0%) for SAS Macro Library modernization. All {macros_count} macro "
                f"definitions converted into valid, reusable R functions with 0 unresolved SAS constructs."
            )
        else:
            overall_confidence = base_confidence
            rationale = (
                f"High confidence for standard SAS steps and macro definitions. "
                f"Flagged {len(manual_items)} item(s) for manual review."
            )

        # 10. Executive Summary
        if is_macro_lib:
            exec_summary = (
                f"Automated modernization analysis for '{program_name}' (Program Type: {prog_type_str}). "
                f"The project contains {macros_count} macro definition(s) across project files "
                f"with {dep_edges} dependency edge(s) ({res_count}/{macros_count} resolved). "
                f"Generated {macros_count} modernized R function(s) with 0 execution steps. "
                f"Achieved overall conversion confidence of {overall_confidence:.1f}%."
            )
        else:
            exec_summary = (
                f"Automated modernization analysis for '{program_name}' (Program Type: {prog_type_str}). "
                f"The project contains {execution_steps_count} execution step(s) and {macros_count} macro definition(s). "
                f"Achieved overall conversion confidence of {overall_confidence:.1f}% with "
                f"{opt_summary.get('line_reduction_pct', 0.0):.1f}% R code line reduction."
            )

        # 11. Validation Status
        if validation_res:
            val_status = "PASSED ✅" if validation_res.get("match") else "MISMATCH ❌"
            val_details = str(validation_res.get("details", "No detailed diff available."))
        else:
            val_status = "PENDING EXECUTION ⚪"
            val_details = "R code generated and optimized. Upload expected CSV/Excel to run full numerical validation."

        return ModernizationDocument(
            executive_summary=exec_summary,
            program_name=program_name,
            program_type=prog_type_str,
            project_metrics=project_metrics,
            r_validation_status=r_val_status,
            input_datasets=all_inputs,
            output_datasets=all_outputs,
            libraries=libs,
            external_dependencies=manual_items,
            step_descriptions=step_descs,
            macro_summaries=macro_sums,
            mapping_table=mapping,
            optimization_summary=opt_summary,
            final_optimized_r=final_r_code,
            validation_status=val_status,
            validation_details=val_details,
            manual_review_items=manual_items,
            overall_confidence=overall_confidence,
            confidence_rationale=rationale
        )
