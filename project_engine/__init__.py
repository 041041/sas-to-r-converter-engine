"""
project_engine package
──────────────────────
Enterprise SAS Project Dependency Architecture package.
"""

from project_engine.models import (
    ProjectContext,
    ProjectFile,
    MacroDefinition,
    MacroReference,
    IncludeReference,
    DependencyEdge,
    DependencyType,
    DependencyGraph,
    ResolutionResult,
    ResolutionStatus
)
from project_engine.file_registry import ProjectFileRegistry
from project_engine.macro_registry import MacroRegistry
from project_engine.dependency_parser import DependencyParser
from project_engine.include_parser import IncludeParser
from project_engine.dependency_graph import DependencyGraphBuilder
from project_engine.resolver import DependencyResolver
from project_engine.analyzer import ProjectAnalyzer
from project_engine.validation import ProjectValidator
from project_engine.classifier import ProgramClassifier, ProgramType
from project_engine.quality import (
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
]
