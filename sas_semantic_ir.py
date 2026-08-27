"""
sas_semantic_ir.py
──────────────────
SAS Semantic Intermediate Representation (Semantic IR) for Enterprise SAS Modernization Engine.
Captures high-level programmatic intent (DatasetRead, DatasetWrite, DatasetFilter, DatasetJoin,
DatasetSort, DatasetAggregate, VariableDerivation, RFunctionSignature) rather than raw SAS syntax.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Any
from sas_ast import ProgramAST, ProgramStep


@dataclass
class SemanticOperation:
    """Represents a single high-level semantic operation in SAS logic."""
    op_type: str  # DATASET_READ, DATASET_WRITE, DATASET_FILTER, DATASET_JOIN, DATASET_SORT, DATASET_AGGREGATE, VARIABLE_DERIVATION, INFRA_CONFIG, MACRO_FUNC_DEF
    target_dataset: Optional[str] = None
    source_datasets: list[str] = field(default_factory=list)
    expressions: list[str] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    sas_source_snippet: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "op_type": self.op_type,
            "target_dataset": self.target_dataset,
            "source_datasets": self.source_datasets,
            "expressions": self.expressions,
            "parameters": self.parameters,
            "sas_source_snippet": self.sas_source_snippet,
        }


@dataclass
class RFunctionSignature:
    """Represents a reusable R function derived from a SAS Macro."""
    function_name: str
    arguments: list[dict[str, Any]] = field(default_factory=list)  # [{"name": "input", "default": None}]
    body_operations: list[SemanticOperation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "function_name": self.function_name,
            "arguments": self.arguments,
            "body_operations": [op.to_dict() for op in self.body_operations],
        }


@dataclass
class SemanticProgram:
    """Top-level Semantic IR for an entire SAS program."""
    program_name: str
    infrastructure_ops: list[SemanticOperation] = field(default_factory=list)
    r_functions: list[RFunctionSignature] = field(default_factory=list)
    pipeline_operations: list[SemanticOperation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "program_name": self.program_name,
            "infrastructure_ops": [op.to_dict() for op in self.infrastructure_ops],
            "r_functions": [fn.to_dict() for fn in self.r_functions],
            "pipeline_operations": [op.to_dict() for op in self.pipeline_operations],
        }


from macro_converter import classify_macro

def build_semantic_ir(ast: ProgramAST, expanded_sas_code: str) -> SemanticProgram:
    """
    Constructs a SemanticProgram IR from the ProgramAST and resolved SAS code.
    """
    sem_program = SemanticProgram(program_name="SAS_Modernized_Program")

    # 1. Map Infrastructure
    for lib, val in ast.infrastructure.libnames.items():
        sem_program.infrastructure_ops.append(SemanticOperation(
            op_type="INFRA_CONFIG",
            parameters={"type": "LIBNAME", "name": lib, "val": val},
            sas_source_snippet=f"libname {lib} '{val}';"
        ))
    for fil, val in ast.infrastructure.filenames.items():
        sem_program.infrastructure_ops.append(SemanticOperation(
            op_type="INFRA_CONFIG",
            parameters={"type": "FILENAME", "name": fil, "val": val},
            sas_source_snippet=f"filename {fil} '{val}';"
        ))

    # 2. Map SAS Macros to RFunctionSignatures (Path B reusable macros only)
    all_macro_defs = {
        m_name: {'body': m_ir.raw_body, 'params': [p.name for p in m_ir.parameters]}
        for m_name, m_ir in ast.macros.items()
    }
    for m_name, m_ir in ast.macros.items():
        macro_def = {'body': m_ir.raw_body, 'params': [p.name for p in m_ir.parameters]}
        if classify_macro(m_name, macro_def, all_macro_defs=all_macro_defs) != 'PATH_B':
            continue

        fn_args = []
        for p in m_ir.parameters:
            fn_args.append({
                "name": p.name.lower(),
                "default": p.default_value
            })
        sem_program.r_functions.append(RFunctionSignature(
            function_name=m_name.lower(),
            arguments=fn_args,
            body_operations=[]
        ))

    # 3. Map Execution Steps to High-Level Semantic Operations
    for step in ast.steps:
        code = step.source_code
        in_ds = step.input_datasets
        out_ds = step.output_datasets[0] if step.output_datasets else None

        if "proc sort" in code.lower():
            # Extract BY vars
            import re
            by_m = re.search(r"by\s+([^;]+);", code, re.I)
            by_vars = by_m.group(1).strip().split() if by_m else []
            sem_program.pipeline_operations.append(SemanticOperation(
                op_type="DATASET_SORT",
                target_dataset=out_ds,
                source_datasets=in_ds,
                parameters={"by_vars": by_vars},
                sas_source_snippet=code[:100]
            ))
        elif "proc sql" in code.lower():
            if "join" in code.lower():
                op_type = "DATASET_JOIN"
            else:
                op_type = "SQL_QUERY"
            sem_program.pipeline_operations.append(SemanticOperation(
                op_type=op_type,
                target_dataset=out_ds,
                source_datasets=in_ds,
                sas_source_snippet=code[:100]
            ))
        elif "proc freq" in code.lower():
            sem_program.pipeline_operations.append(SemanticOperation(
                op_type="DATASET_AGGREGATE",
                target_dataset=out_ds or "freq_summary",
                source_datasets=in_ds,
                parameters={"method": "FREQ"},
                sas_source_snippet=code[:100]
            ))
        elif "proc means" in code.lower() or "proc summary" in code.lower():
            sem_program.pipeline_operations.append(SemanticOperation(
                op_type="DATASET_AGGREGATE",
                target_dataset=out_ds or "means_summary",
                source_datasets=in_ds,
                parameters={"method": "MEANS"},
                sas_source_snippet=code[:100]
            ))
        elif step.step_type == "DATA_STEP":
            # DATA step filtering/derivation
            sem_program.pipeline_operations.append(SemanticOperation(
                op_type="DATASET_FILTER",
                target_dataset=out_ds,
                source_datasets=in_ds,
                sas_source_snippet=code[:100]
            ))

    return sem_program
