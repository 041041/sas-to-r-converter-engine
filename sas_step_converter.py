"""
sas_step_converter.py
─────────────────────
Unified Step Converter & Pipeline Coordinator for Enterprise SAS Modernization Engine.
Orchestrates AST parsing, infrastructure analysis, rule-based conversion, LLM fallback,
and R code optimization.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Any

from sas_ast import ProgramAST, ProgramStep
from sas_parser import parse_sas_program
from dependency_graph import build_dependency_graph, DependencyGraph
from rule_engine import RuleEngine
from r_optimizer import ROptimizer, OptimizationMetrics
from infra_analyzer import InfrastructureAnalyzer, InfraRConfig


@dataclass
class ConvertedStepResult:
    step_index: int
    step_name: str
    step_type: str
    source_sas: str
    initial_r_code: str
    optimized_r_code: str
    confidence_score: float
    conversion_method: str  # "RuleEngine" or "LLM"
    optimization_metrics: OptimizationMetrics
    review_items: list[str] = field(default_factory=list)


@dataclass
class ProgramConversionResult:
    ast: ProgramAST
    dependency_graph: DependencyGraph
    infra_config: InfraRConfig
    converted_steps: list[ConvertedStepResult]
    full_initial_r: str
    full_optimized_r: str
    overall_confidence: float
    total_optimization_metrics: OptimizationMetrics


class SASStepConverter:
    """
    Main conversion coordinator.
    """

    def __init__(self, dialect: str = "Modern R (tidyverse)"):
        self.dialect = dialect
        self.rule_engine = RuleEngine(dialect=dialect)
        self.optimizer = ROptimizer(dialect=dialect)
        self.infra_analyzer = InfrastructureAnalyzer()

    def convert_program(self, sas_code: str, llm_fallback_fn: Optional[Any] = None, raw_sas_code: Optional[str] = None) -> ProgramConversionResult:
        """
        Converts an entire SAS program into an optimized R script with complete metadata.
        """
        # 1. Parse AST from raw SAS code (extracts macro definitions & infrastructure from raw SAS if provided)
        ast = parse_sas_program(raw_sas_code if raw_sas_code else sas_code)

        # 2. Expand macro calls for step execution
        from macro_processor import SASMacroProcessor
        processor = SASMacroProcessor()
        expanded_code, macro_warns, _ = processor.process(sas_code)
        ast.infrastructure.review_items.extend(macro_warns)

        # Re-parse steps & lineage on expanded code
        expanded_ast = parse_sas_program(expanded_code)
        if expanded_ast.steps:
            ast.steps = expanded_ast.steps

        # 3. Build Dependency Graph
        dep_graph = build_dependency_graph(ast)

        # 3. Analyze Infrastructure
        infra_config = self.infra_analyzer.analyze(ast.infrastructure)

        converted_steps = []
        initial_r_blocks = [infra_config.r_config_code] if infra_config.r_config_code else []
        confidences = []

        # 4. Convert Steps
        for step in ast.steps:
            r_code, conf, method = self.rule_engine.translate_step(step)

            if r_code is None and llm_fallback_fn is not None:
                # LLM Fallback
                try:
                    r_code = llm_fallback_fn(step.source_code, step.input_datasets, self.dialect)
                    conf = 0.75
                    method = "LLMFallback"
                except Exception:
                    r_code = f"# TODO: Manual review required for step: {step.name}"
                    conf = 0.30
                    method = "ManualReviewRequired"

            if r_code is None:
                r_code = f"# TODO: Manual review required for step: {step.name}"
                conf = 0.30
                method = "ManualReviewRequired"

            # Optimize individual step code
            opt_code, opt_metrics = self.optimizer.optimize(r_code)

            confidences.append(conf)
            initial_r_blocks.append(r_code)

            converted_steps.append(ConvertedStepResult(
                step_index=step.step_index,
                step_name=step.name,
                step_type=step.step_type,
                source_sas=step.source_code,
                initial_r_code=r_code,
                optimized_r_code=opt_code,
                confidence_score=conf,
                conversion_method=method,
                optimization_metrics=opt_metrics,
                review_items=infra_config.manual_review_items if step.step_index == 1 else []
            ))

        full_initial = "\n\n".join(initial_r_blocks)

        # 5. Full Program Optimization Pass
        full_optimized, total_metrics = self.optimizer.optimize(full_initial)

        overall_conf = (sum(confidences) / len(confidences)) * 100.0 if confidences else 100.0

        return ProgramConversionResult(
            ast=ast,
            dependency_graph=dep_graph,
            infra_config=infra_config,
            converted_steps=converted_steps,
            full_initial_r=full_initial,
            full_optimized_r=full_optimized,
            overall_confidence=round(overall_conf, 1),
            total_optimization_metrics=total_metrics
        )
