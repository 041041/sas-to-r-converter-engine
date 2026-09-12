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
    DependencyEdge,
    DependencyGraph,
    ResolutionResult,
    ResolutionStatus
)
from project_engine.file_registry import ProjectFileRegistry
from project_engine.macro_registry import MacroRegistry
from project_engine.dependency_parser import DependencyParser
from project_engine.dependency_graph import DependencyGraphBuilder
from project_engine.resolver import DependencyResolver
from project_engine.analyzer import ProjectAnalyzer
from project_engine.validation import ProjectValidator

__all__ = [
    "ProjectContext",
    "ProjectFile",
    "MacroDefinition",
    "MacroReference",
    "DependencyEdge",
    "DependencyGraph",
    "ResolutionResult",
    "ResolutionStatus",
    "ProjectFileRegistry",
    "MacroRegistry",
    "DependencyParser",
    "DependencyGraphBuilder",
    "DependencyResolver",
    "ProjectAnalyzer",
    "ProjectValidator",
]
