"""
project_engine/models.py
─────────────────────────
Typed domain models for Enterprise SAS Project Dependency Architecture.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ResolutionStatus(str, Enum):
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED_DEPENDENCY"
    DUPLICATE_DEFINITION = "DUPLICATE_DEFINITION"
    CIRCULAR_DEPENDENCY = "CIRCULAR_DEPENDENCY"
    INVALID_DEFINITION = "INVALID_DEFINITION"


@dataclass
class ProjectFile:
    filename: str
    normalized_path: str
    file_type: str
    source_content: str
    is_main: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "normalized_path": self.normalized_path,
            "file_type": self.file_type,
            "is_main": self.is_main,
            "content_length": len(self.source_content)
        }


@dataclass
class MacroParameter:
    name: str
    default_value: str | None = None
    is_keyword: bool = False


@dataclass
class MacroDefinition:
    name: str  # Normalized uppercase
    original_name: str
    source_file: str
    start_line: int = 1
    end_line: int = 1
    source_content: str = ""
    parameters: list[MacroParameter] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "original_name": self.original_name,
            "source_file": self.source_file,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "parameters": [p.name for p in self.parameters]
        }


@dataclass
class MacroReference:
    caller: str
    referenced_macro: str  # Normalized uppercase
    source_file: str
    line: int = 0
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "caller": self.caller,
            "referenced_macro": self.referenced_macro,
            "source_file": self.source_file,
            "line": self.line,
            "reason": self.reason
        }


@dataclass
class DependencyEdge:
    caller: str
    dependency: str

    def to_dict(self) -> dict[str, str]:
        return {
            "caller": self.caller,
            "dependency": self.dependency
        }


@dataclass
class DependencyGraph:
    nodes: set[str] = field(default_factory=set)
    edges: list[DependencyEdge] = field(default_factory=list)
    adjacency: dict[str, list[str]] = field(default_factory=dict)
    reverse_adjacency: dict[str, list[str]] = field(default_factory=dict)

    def add_node(self, node: str) -> None:
        self.nodes.add(node)
        if node not in self.adjacency:
            self.adjacency[node] = []
        if node not in self.reverse_adjacency:
            self.reverse_adjacency[node] = []

    def add_edge(self, caller: str, dependency: str) -> None:
        self.add_node(caller)
        self.add_node(dependency)
        if dependency not in self.adjacency[caller]:
            self.adjacency[caller].append(dependency)
            self.edges.append(DependencyEdge(caller=caller, dependency=dependency))
        if caller not in self.reverse_adjacency[dependency]:
            self.reverse_adjacency[dependency].append(caller)

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": sorted(list(self.nodes)),
            "edges": [e.to_dict() for e in self.edges],
            "adjacency": {k: sorted(v) for k, v in self.adjacency.items()}
        }


@dataclass
class ResolutionResult:
    status: ResolutionStatus = ResolutionStatus.RESOLVED
    resolution_order: list[str] = field(default_factory=list)
    missing_dependencies: list[MacroReference] = field(default_factory=list)
    duplicate_definitions: dict[str, list[str]] = field(default_factory=dict)
    circular_paths: list[list[str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    audit_trail: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value if isinstance(self.status, ResolutionStatus) else str(self.status),
            "resolution_order": self.resolution_order,
            "missing_dependencies": [m.to_dict() for m in self.missing_dependencies],
            "duplicate_definitions": self.duplicate_definitions,
            "circular_paths": self.circular_paths,
            "warnings": self.warnings,
            "errors": self.errors,
            "audit_trail": self.audit_trail
        }


@dataclass
class ProjectContext:
    project_files: dict[str, ProjectFile] = field(default_factory=dict)
    macro_registry: dict[str, MacroDefinition] = field(default_factory=dict)
    dependency_graph: DependencyGraph = field(default_factory=DependencyGraph)
    resolution_result: ResolutionResult = field(default_factory=ResolutionResult)
    dependency_order: list[str] = field(default_factory=list)
    ordered_supporting_content: list[str] = field(default_factory=list)
    main_program_file: str | None = None
    main_program_content: str = ""
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def export_manifest(self) -> dict[str, Any]:
        """Generates internal manifest suitable for future R project packaging."""
        return {
            "main_program": self.main_program_file,
            "status": self.resolution_result.status.value if isinstance(self.resolution_result.status, ResolutionStatus) else str(self.resolution_result.status),
            "dependency_order": self.dependency_order,
            "files": {
                norm: pf.to_dict() for norm, pf in self.project_files.items()
            },
            "macros": {
                name: m.to_dict() for name, m in self.macro_registry.items()
            },
            "audit_trail": self.resolution_result.audit_trail
        }
