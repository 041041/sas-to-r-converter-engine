"""
project_engine/models.py
─────────────────────────
Typed domain models for Enterprise SAS Project Dependency Architecture.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
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


class DependencyType(str, Enum):
    MACRO_CALL = "MACRO_CALL"
    INCLUDE = "INCLUDE"
    FILE_DEPENDENCY = "FILE_DEPENDENCY"


@dataclass
class IncludeReference:
    caller_file: str
    referenced_path: str
    normalized_filename: str
    line_number: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "caller_file": self.caller_file,
            "referenced_path": self.referenced_path,
            "normalized_filename": self.normalized_filename,
            "line_number": self.line_number
        }


@dataclass
class DependencyEdge:
    caller: str
    dependency: str
    dependency_type: DependencyType = DependencyType.MACRO_CALL
    source_file: str | None = None
    line_number: int = 0
    status: str = "RESOLVED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "caller": self.caller,
            "dependency": self.dependency,
            "dependency_type": self.dependency_type.value if isinstance(self.dependency_type, DependencyType) else str(self.dependency_type),
            "source_file": self.source_file,
            "line_number": self.line_number,
            "status": self.status
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

    def add_edge(
        self,
        caller: str,
        dependency: str,
        dependency_type: DependencyType = DependencyType.MACRO_CALL,
        source_file: str | None = None,
        line_number: int = 0,
        status: str = "RESOLVED"
    ) -> None:
        self.add_node(caller)
        self.add_node(dependency)
        if dependency not in self.adjacency[caller]:
            self.adjacency[caller].append(dependency)
        if caller not in self.reverse_adjacency[dependency]:
            self.reverse_adjacency[dependency].append(caller)

        # Ensure no duplicate edge with same caller, dependency, and dependency_type
        for existing in self.edges:
            if existing.caller == caller and existing.dependency == dependency and existing.dependency_type == dependency_type:
                return

        self.edges.append(DependencyEdge(
            caller=caller,
            dependency=dependency,
            dependency_type=dependency_type,
            source_file=source_file,
            line_number=line_number,
            status=status
        ))

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
    missing_includes: list[IncludeReference] = field(default_factory=list)
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
            "missing_includes": [inc.to_dict() for inc in self.missing_includes],
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


@dataclass
class RProject:
    """Explicit domain model representing a structured, modular R project."""
    project_name: str = "converted_project"
    main_file: str = "main.R"
    source_files: dict[str, str] = field(default_factory=dict)
    entry_function: str | None = None
    dependency_order: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def write_to_directory(self, target_dir: str | Path) -> dict[str, str]:
        """
        Writes all source files in this RProject into target_dir directory structure.
        Returns a dict mapping relative file paths to absolute file path strings.
        """
        target_path = Path(target_dir)
        written_files = {}
        for rel_path, content in self.source_files.items():
            full_path = target_path / rel_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding="utf-8")
            written_files[rel_path] = str(full_path.resolve())
        return written_files

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_name": self.project_name,
            "main_file": self.main_file,
            "source_files": list(self.source_files.keys()),
            "entry_function": self.entry_function,
            "dependency_order": self.dependency_order,
            "metadata": self.metadata,
        }
