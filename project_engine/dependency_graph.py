"""
project_engine/dependency_graph.py
───────────────────────────────────
Dependency Graph Builder for constructing unified macro call and %include dependency graphs.
"""

from __future__ import annotations
from project_engine.models import DependencyGraph, DependencyType, ProjectFile
from project_engine.macro_registry import MacroRegistry
from project_engine.dependency_parser import DependencyParser
from project_engine.include_parser import IncludeParser


class DependencyGraphBuilder:
    """Builds a directed dependency graph mapping callers to called macros and included files."""

    def __init__(
        self,
        parser: DependencyParser | None = None,
        include_parser: IncludeParser | None = None
    ) -> None:
        self.parser = parser or DependencyParser()
        self.include_parser = include_parser or IncludeParser()

    def build_graph(self, files: list[ProjectFile], macro_registry: MacroRegistry) -> DependencyGraph:
        """Constructs a complete unified DependencyGraph for the project."""
        graph = DependencyGraph()

        # 1. Register file nodes
        for pf in files:
            graph.add_node(pf.filename)

        # 2. Register macro nodes
        for norm_name in macro_registry.all_macros().keys():
            graph.add_node(norm_name)

        # 3. Discover %INCLUDE directives in all files
        for pf in files:
            inc_refs = self.include_parser.parse_includes(pf.source_content, pf.filename)
            for inc in inc_refs:
                graph.add_edge(
                    caller=pf.filename,
                    dependency=inc.normalized_filename,
                    dependency_type=DependencyType.INCLUDE,
                    source_file=pf.filename,
                    line_number=inc.line_number
                )

        # 4. Discover Macro calls in top-level code of all files
        for pf in files:
            refs = self.parser.parse_main_references(pf.filename, pf.source_content, pf.filename)
            for ref in refs:
                graph.add_edge(
                    caller=pf.filename,
                    dependency=ref.referenced_macro,
                    dependency_type=DependencyType.MACRO_CALL,
                    source_file=pf.filename,
                    line_number=ref.line
                )

        # 5. Discover Macro calls and %includes inside macro definitions
        for mdef in macro_registry.all_macros().values():
            graph.add_node(mdef.name)
            refs = self.parser.parse_references(mdef.name, mdef.source_content, mdef.source_file)
            for ref in refs:
                if ref.referenced_macro != mdef.name:  # Avoid self-loops
                    graph.add_edge(
                        caller=mdef.name,
                        dependency=ref.referenced_macro,
                        dependency_type=DependencyType.MACRO_CALL,
                        source_file=mdef.source_file,
                        line_number=ref.line
                    )

            inc_refs = self.include_parser.parse_includes(mdef.source_content, mdef.source_file)
            for inc in inc_refs:
                graph.add_edge(
                    caller=mdef.name,
                    dependency=inc.normalized_filename,
                    dependency_type=DependencyType.INCLUDE,
                    source_file=mdef.source_file,
                    line_number=inc.line_number
                )

        return graph
