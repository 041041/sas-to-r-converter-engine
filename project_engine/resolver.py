"""
project_engine/resolver.py
───────────────────────────
Dependency Resolver for topological sorting, cycle detection, missing dependency detection,
and auditability logging across unified macro and %include dependency graphs.
"""

from __future__ import annotations
from typing import Any
from project_engine.models import (
    DependencyGraph,
    DependencyType,
    IncludeReference,
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

        # 2. Check for Missing Dependencies (%include and macro calls)
        all_macros = set(macro_registry.all_macros().keys())
        registered_file_names = {pf.filename for pf in file_registry.all_files()}
        missing_macro_refs: list[MacroReference] = []
        missing_include_refs: list[IncludeReference] = []

        for edge in graph.edges:
            caller = edge.caller
            dep = edge.dependency

            if edge.dependency_type == DependencyType.INCLUDE:
                if file_registry.get_file(dep) is None:
                    inc_ref = IncludeReference(
                        caller_file=caller,
                        referenced_path=dep,
                        normalized_filename=dep,
                        line_number=edge.line_number
                    )
                    missing_include_refs.append(inc_ref)
            elif edge.dependency_type == DependencyType.MACRO_CALL:
                if dep not in all_macros and file_registry.get_file(dep) is None:
                    source_file = edge.source_file or self._find_caller_source(caller, macro_registry, file_registry)
                    ref = MacroReference(
                        caller=caller,
                        referenced_macro=dep,
                        source_file=source_file,
                        line=edge.line_number,
                        reason="macro definition not found"
                    )
                    missing_macro_refs.append(ref)

        if missing_include_refs or missing_macro_refs:
            result.status = ResolutionStatus.UNRESOLVED
            result.missing_dependencies = missing_macro_refs
            result.missing_includes = missing_include_refs

            for inc in missing_include_refs:
                result.errors.append(
                    f"Unresolved project dependency: caller '{inc.caller_file}' -> '{inc.normalized_filename}' (file not found in uploaded project)"
                )
            for ref in missing_macro_refs:
                result.errors.append(
                    f"Unresolved macro dependency: %{ref.referenced_macro} called by '{ref.caller}' (definition not found)"
                )
            return result

        # 3. Cycle Detection via DFS
        cycle_found, circular_paths = self._detect_cycles(graph)
        if cycle_found:
            result.status = ResolutionStatus.CIRCULAR_DEPENDENCY
            result.circular_paths = circular_paths
            for path in circular_paths:
                result.errors.append(f"Circular project dependency detected: {' -> '.join(path)}")
            return result

        # 4. Topological Sort (Post-order DFS: dependencies visit FIRST)
        order = self._topological_sort(graph, file_registry, macro_registry)
        result.resolution_order = order
        result.status = ResolutionStatus.RESOLVED

        # 5. Build Audit Trail
        for node in order:
            mdef = macro_registry.get_macro(node)
            pf = file_registry.get_file(node)
            deps = graph.adjacency.get(node, [])
            resolved_from = {}
            for d in deps:
                ddef = macro_registry.get_macro(d)
                dpf = file_registry.get_file(d)
                if ddef:
                    resolved_from[d] = ddef.source_file
                elif dpf:
                    resolved_from[d] = dpf.filename

            node_type = "macro" if mdef else ("file" if pf else "unknown")
            source = mdef.source_file if mdef else (pf.filename if pf else None)

            audit_entry: dict[str, Any] = {
                "node": node,
                "node_type": node_type,
                "source_file": source,
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
        pf = file_registry.get_file(caller)
        if pf:
            return pf.filename
        mdef = macro_registry.get_macro(caller)
        return mdef.source_file if mdef else "Unknown"

    def _detect_cycles(
        self,
        graph: DependencyGraph
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

        for node in sorted(list(graph.nodes)):
            if visited.get(node, 0) == 0:
                dfs(node)

        return (len(circular_paths) > 0, circular_paths)

    def _topological_sort(
        self,
        graph: DependencyGraph,
        file_registry: ProjectFileRegistry,
        macro_registry: MacroRegistry
    ) -> list[str]:
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
            order.append(node)

        main_file = file_registry.get_main_file()
        main_filename = main_file.filename if main_file else None

        roots = []
        if main_filename and main_filename in graph.nodes:
            roots.append(main_filename)

        for node in sorted(list(graph.nodes)):
            if node not in roots:
                roots.append(node)

        for node in roots:
            visit(node)

        macros = set(macro_registry.all_macros().keys())
        has_file_includes = any(e.dependency_type == DependencyType.INCLUDE for e in graph.edges)

        if not has_file_includes and len(macros) > 0:
            # Macro-only project: return only macro names in topological order for backward compatibility
            return [n for n in order if n in macros]

        # Mixed or Include project: return all active nodes in topological order
        active_nodes = set()
        for e in graph.edges:
            active_nodes.add(e.caller)
            active_nodes.add(e.dependency)
        if main_filename:
            active_nodes.add(main_filename)

        filtered_order = [n for n in order if n in active_nodes or n in macros]
        return filtered_order
