"""
project_engine/resolver.py
───────────────────────────
Dependency Resolver for topological sorting, cycle detection, missing dependency detection,
and auditability logging.
"""

from __future__ import annotations
from typing import Any
from project_engine.models import (
    DependencyGraph,
    MacroReference,
    ResolutionResult,
    ResolutionStatus
)
from project_engine.macro_registry import MacroRegistry
from project_engine.file_registry import ProjectFileRegistry


class DependencyResolver:
    """Resolves project dependencies, detects cycles/missing/duplicates, and produces topological execution order."""

    def resolve(
        self,
        graph: DependencyGraph,
        macro_registry: MacroRegistry,
        file_registry: ProjectFileRegistry
    ) -> ResolutionResult:
        """Resolves dependencies across the project graph."""
        result = ResolutionResult()

        # 1. Check for Duplicate Macro Definitions
        duplicates = macro_registry.get_duplicates()
        if duplicates:
            result.status = ResolutionStatus.DUPLICATE_DEFINITION
            result.duplicate_definitions = duplicates
            for mac, files in duplicates.items():
                err_msg = f"Duplicate definition found for macro %{mac} in files: {', '.join(files)}"
                result.errors.append(err_msg)
            return result

        # 2. Check for Missing Dependencies
        all_macros = set(macro_registry.all_macros().keys())
        missing_refs: list[MacroReference] = []

        for edge in graph.edges:
            dep = edge.dependency
            if dep.startswith("MAIN ("):
                continue
            if dep not in all_macros:
                ref = MacroReference(
                    caller=edge.caller,
                    referenced_macro=dep,
                    source_file=self._find_caller_source(edge.caller, macro_registry, file_registry),
                    reason="source definition not found"
                )
                missing_refs.append(ref)

        if missing_refs:
            result.status = ResolutionStatus.UNRESOLVED
            result.missing_dependencies = missing_refs
            for ref in missing_refs:
                result.errors.append(
                    f"Unresolved macro dependency: %{ref.referenced_macro} called by '{ref.caller}' (definition not found)"
                )
            return result

        # 3. Cycle Detection via DFS
        cycle_found, circular_paths = self._detect_cycles(graph, all_macros)
        if cycle_found:
            result.status = ResolutionStatus.CIRCULAR_DEPENDENCY
            result.circular_paths = circular_paths
            for path in circular_paths:
                result.errors.append(f"Circular macro dependency detected: {' -> '.join(path)}")
            return result

        # 4. Topological Sort (Post-order DFS: dependencies visit FIRST)
        order = self._topological_sort(graph, all_macros)
        result.resolution_order = order
        result.status = ResolutionStatus.RESOLVED

        # 5. Build Audit Trail
        for mac in order:
            mdef = macro_registry.get_macro(mac)
            deps = graph.adjacency.get(mac, [])
            resolved_from = {}
            for d in deps:
                ddef = macro_registry.get_macro(d)
                if ddef:
                    resolved_from[d] = ddef.source_file

            audit_entry: dict[str, Any] = {
                "macro": mac,
                "source_file": mdef.source_file if mdef else None,
                "dependencies": deps,
                "resolved_from": resolved_from
            }
            result.audit_trail.append(audit_entry)

        return result

    def _find_caller_source(
        self,
        caller: str,
        macro_registry: MacroRegistry,
        file_registry: ProjectFileRegistry
    ) -> str:
        """Helper to identify the source file of a caller."""
        if caller.startswith("MAIN ("):
            main_file = file_registry.get_main_file()
            return main_file.filename if main_file else "Main Program"
        mdef = macro_registry.get_macro(caller)
        return mdef.source_file if mdef else "Unknown"

    def _detect_cycles(
        self,
        graph: DependencyGraph,
        valid_nodes: set[str]
    ) -> tuple[bool, list[list[str]]]:
        """Detects circular dependency paths in graph using 3-color DFS."""
        visited: dict[str, int] = {node: 0 for node in graph.nodes}  # 0: unvisited, 1: visiting, 2: visited
        circular_paths: list[list[str]] = []
        path_stack: list[str] = []

        def dfs(node: str):
            visited[node] = 1
            path_stack.append(node)

            for neighbor in graph.adjacency.get(node, []):
                if neighbor not in visited:
                    continue
                if visited[neighbor] == 1:
                    # Cycle detected
                    idx = path_stack.index(neighbor)
                    cycle_path = path_stack[idx:] + [neighbor]
                    circular_paths.append(cycle_path)
                elif visited[neighbor] == 0:
                    dfs(neighbor)

            path_stack.pop()
            visited[node] = 2

        for node in graph.nodes:
            if visited.get(node, 0) == 0:
                dfs(node)

        return (len(circular_paths) > 0, circular_paths)

    def _topological_sort(self, graph: DependencyGraph, macro_nodes: set[str]) -> list[str]:
        """Produces topological ordering where dependencies come BEFORE callers."""
        visited = set()
        order = []

        def visit(node: str):
            if node in visited:
                return
            visited.add(node)
            for dep in graph.adjacency.get(node, []):
                if dep in graph.nodes:
                    visit(dep)
            if node in macro_nodes:
                order.append(node)

        # Visit starting from non-macro nodes (e.g. MAIN) first if present
        for node in sorted(list(graph.nodes)):
            visit(node)

        return order
