"""
project_engine/dependency_graph.py
───────────────────────────────────
Dependency Graph Builder for constructing directed macro call dependency graphs.
"""

from __future__ import annotations
from project_engine.models import DependencyGraph, ProjectFile
from project_engine.macro_registry import MacroRegistry
from project_engine.dependency_parser import DependencyParser


class DependencyGraphBuilder:
    """Builds a directed dependency graph mapping callers to called macros."""

    def __init__(self, parser: DependencyParser | None = None) -> None:
        self.parser = parser or DependencyParser()

    def build_graph(self, files: list[ProjectFile], macro_registry: MacroRegistry) -> DependencyGraph:
        """Constructs a complete DependencyGraph for the project."""
        graph = DependencyGraph()

        # 1. Register all macro nodes
        for norm_name in macro_registry.all_macros().keys():
            graph.add_node(norm_name)

        # 2. Process main program outer code if present
        for pf in files:
            if pf.is_main:
                main_node = f"MAIN ({pf.filename})"
                graph.add_node(main_node)
                refs = self.parser.parse_main_references(main_node, pf.source_content, pf.filename)
                for ref in refs:
                    graph.add_edge(main_node, ref.referenced_macro)

        # 3. Process all macro definitions
        for mdef in macro_registry.all_macros().values():
            graph.add_node(mdef.name)
            refs = self.parser.parse_references(mdef.name, mdef.source_content, mdef.source_file)
            for ref in refs:
                if ref.referenced_macro != mdef.name:  # Avoid self-loops
                    graph.add_edge(mdef.name, ref.referenced_macro)

        return graph
