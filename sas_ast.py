"""
sas_ast.py
──────────
Core AST & Intermediate Representation (IR) data models for the Enterprise
SAS Modernization Engine.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Any


@dataclass
class MacroParameter:
    """Represents a SAS macro parameter (positional or keyword)."""
    name: str
    default_value: Optional[str] = None
    is_keyword: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "default_value": self.default_value,
            "is_keyword": self.is_keyword
        }


@dataclass
class MacroIR:
    """Intermediate Representation of a SAS Macro definition."""
    name: str
    parameters: list[MacroParameter] = field(default_factory=list)
    local_vars: list[str] = field(default_factory=list)
    global_vars: list[str] = field(default_factory=list)
    nested_macros: list[str] = field(default_factory=list)
    conditions: list[dict[str, Any]] = field(default_factory=list)  # %IF/%THEN/%ELSE
    loops: list[dict[str, Any]] = field(default_factory=list)       # %DO %TO, %DO %WHILE, %DO %UNTIL
    generated_code_template: str = ""
    input_datasets: list[str] = field(default_factory=list)
    output_datasets: list[str] = field(default_factory=list)
    procs_used: list[str] = field(default_factory=list)
    complexity_score: float = 0.0
    has_dynamic_naming: bool = False
    has_indirect_refs: bool = False
    raw_body: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "parameters": [p.to_dict() for p in self.parameters],
            "local_vars": self.local_vars,
            "global_vars": self.global_vars,
            "nested_macros": self.nested_macros,
            "conditions": self.conditions,
            "loops": self.loops,
            "input_datasets": self.input_datasets,
            "output_datasets": self.output_datasets,
            "procs_used": self.procs_used,
            "complexity_score": self.complexity_score,
            "has_dynamic_naming": self.has_dynamic_naming,
            "has_indirect_refs": self.has_indirect_refs,
        }


@dataclass
class InfraIR:
    """Intermediate Representation of SAS Environment & Infrastructure constructs."""
    libnames: dict[str, str] = field(default_factory=dict)       # e.g. {"SOURCE": "/clinical/data"}
    filenames: dict[str, str] = field(default_factory=dict)      # e.g. {"RAWDATA": "/path/to/raw.csv"}
    includes: list[str] = field(default_factory=list)            # %INCLUDE file paths/refs
    options: dict[str, str] = field(default_factory=dict)        # OPTIONS settings
    titles_footnotes: list[str] = field(default_factory=list)    # TITLE & FOOTNOTE statements
    user_formats: dict[str, dict[str, Any]] = field(default_factory=dict) # Format definitions
    review_items: list[str] = field(default_factory=list)        # Items needing manual review

    def to_dict(self) -> dict[str, Any]:
        return {
            "libnames": self.libnames,
            "filenames": self.filenames,
            "includes": self.includes,
            "options": self.options,
            "titles_footnotes": self.titles_footnotes,
            "user_formats": self.user_formats,
            "review_items": self.review_items,
        }


@dataclass
class DatasetLineage:
    """Tracks dataset transformations and lineage across program execution."""
    dataset_name: str
    source_datasets: list[str] = field(default_factory=list)
    operation_type: str = "DATA_STEP"  # DATA_STEP, PROC_SORT, PROC_SQL, PROC_TRANSPOSE, etc.
    created_by_step: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_name": self.dataset_name,
            "source_datasets": self.source_datasets,
            "operation_type": self.operation_type,
            "created_by_step": self.created_by_step,
        }


@dataclass
class ComplexityMetrics:
    """Calculated program complexity metrics and risk classification."""
    score: float = 0.0
    macro_count: int = 0
    proc_count: int = 0
    data_step_count: int = 0
    dynamic_name_count: int = 0
    indirect_ref_count: int = 0
    infra_count: int = 0
    risk_level: str = "Low"  # Low, Medium, High

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 1),
            "macro_count": self.macro_count,
            "proc_count": self.proc_count,
            "data_step_count": self.data_step_count,
            "dynamic_name_count": self.dynamic_name_count,
            "indirect_ref_count": self.indirect_ref_count,
            "infra_count": self.infra_count,
            "risk_level": self.risk_level,
        }


@dataclass
class ProgramStep:
    """Represents a discrete executable step (DATA step, PROC step, or Infra command)."""
    step_index: int
    step_type: str  # DATA_STEP, PROC_STEP, INFRASTRUCTURE, MACRO_DEF, MACRO_CALL
    name: str       # e.g., "ADSL", "PROC SORT", "LIBNAME SOURCE"
    source_code: str
    input_datasets: list[str] = field(default_factory=list)
    output_datasets: list[str] = field(default_factory=list)
    ast_node: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "step_type": self.step_type,
            "name": self.name,
            "source_code": self.source_code,
            "input_datasets": self.input_datasets,
            "output_datasets": self.output_datasets,
        }


@dataclass
class ProgramAST:
    """Top-level AST and IR model representing an entire SAS program or macro library."""
    raw_sas_code: str
    infrastructure: InfraIR = field(default_factory=InfraIR)
    macros: dict[str, MacroIR] = field(default_factory=dict)
    steps: list[ProgramStep] = field(default_factory=list)
    lineage: list[DatasetLineage] = field(default_factory=list)
    complexity: ComplexityMetrics = field(default_factory=ComplexityMetrics)

    def to_dict(self) -> dict[str, Any]:
        return {
            "infrastructure": self.infrastructure.to_dict(),
            "macros": {k: v.to_dict() for k, v in self.macros.items()},
            "steps": [s.to_dict() for s in self.steps],
            "lineage": [l.to_dict() for l in self.lineage],
            "complexity": self.complexity.to_dict(),
        }
