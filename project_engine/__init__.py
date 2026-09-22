"""
project_engine package
──────────────────────
Enterprise SAS Project Dependency Architecture package.
"""

from .models import (
    ProjectContext,
    ProjectFile,
    MacroDefinition,
    MacroReference,
    IncludeReference,
    DependencyEdge,
    DependencyType,
    DependencyGraph,
    ResolutionResult,
    ResolutionStatus,
    RProject
)
from .r_project_assembler import RProjectAssembler
from .r_project_zip import RProjectZipExporter
from .output_handler import prepare_conversion_output, ConversionOutput
from .file_registry import ProjectFileRegistry
from .macro_registry import MacroRegistry
from .dependency_parser import DependencyParser
from .include_parser import IncludeParser
from .dependency_graph import DependencyGraphBuilder
from .resolver import DependencyResolver
from .analyzer import ProjectAnalyzer
from .validation import ProjectValidator
from .classifier import ProgramClassifier, ProgramType
from .schema_registry import DatasetSchemaRegistry
from .quality import (
    QualityStatus,
    ConfidenceBand,
    QualitySummary,
    evaluate_quality_summary
)

__all__ = [
    "ProjectContext",
    "ProjectFile",
    "MacroDefinition",
    "MacroReference",
    "IncludeReference",
    "DependencyEdge",
    "DependencyType",
    "DependencyGraph",
    "ResolutionResult",
    "ResolutionStatus",
    "ProjectFileRegistry",
    "MacroRegistry",
    "DependencyParser",
    "IncludeParser",
    "DependencyGraphBuilder",
    "DependencyResolver",
    "ProjectAnalyzer",
    "ProjectValidator",
    "ProgramType",
    "ProgramClassifier",
    "QualityStatus",
    "ConfidenceBand",
    "QualitySummary",
    "evaluate_quality_summary",
    "DatasetSchemaRegistry",
    "RProject",
    "RProjectAssembler",
    "RProjectZipExporter",
    "prepare_conversion_output",
    "ConversionOutput",
]
