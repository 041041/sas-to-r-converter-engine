"""
project_engine/analyzer.py
───────────────────────────
Project Analyzer orchestrator for building ProjectContext from uploaded files.
"""

from __future__ import annotations
from typing import Sequence
from project_engine.models import (
    ProjectContext,
    ResolutionStatus
)
from project_engine.file_registry import ProjectFileRegistry
from project_engine.macro_registry import MacroRegistry
from project_engine.dependency_parser import DependencyParser
from project_engine.dependency_graph import DependencyGraphBuilder
from project_engine.resolver import DependencyResolver


class ProjectAnalyzer:
    """Orchestrates file registration, macro discovery, dependency graphing, and resolution."""

    def __init__(
        self,
        parser: DependencyParser | None = None,
        graph_builder: DependencyGraphBuilder | None = None,
        resolver: DependencyResolver | None = None
    ) -> None:
        self.parser = parser or DependencyParser()
        self.graph_builder = graph_builder or DependencyGraphBuilder(parser=self.parser)
        self.resolver = resolver or DependencyResolver()

    def analyze_project(
        self,
        files: Sequence[tuple[str, str]],
        main_filename: str | None = None
    ) -> ProjectContext:
        """
        Analyzes a set of uploaded files (filename, content) and builds a ProjectContext.

        Args:
            files: List of (filename, content) tuples.
            main_filename: Optional filename designating the main SAS program.
        """
        file_reg = ProjectFileRegistry()
        macro_reg = MacroRegistry()

        # 1. Register Files
        for filename, content in files:
            file_reg.register_file(filename, content)

        if main_filename:
            file_reg.set_main_file(main_filename)

        main_file = file_reg.get_main_file()

        # 2. Scan Macros across files
        for pf in file_reg.all_files():
            macro_reg.scan_file(pf)

        # 3. Build Dependency Graph
        graph = self.graph_builder.build_graph(file_reg.all_files(), macro_reg)

        # 4. Resolve Dependencies
        resolution_result = self.resolver.resolve(graph, macro_reg, file_reg)

        # 5. Build Ordered Supporting Content
        # Group supporting files by topological dependency order of macros contained within them
        ordered_supporting_files = []
        seen_files = set()

        # Add files containing macros in topological order
        for mac_name in resolution_result.resolution_order:
            mdef = macro_reg.get_macro(mac_name)
            if mdef:
                pf = file_reg.get_file(mdef.source_file)
                if pf and not pf.is_main and pf.normalized_path not in seen_files:
                    seen_files.add(pf.normalized_path)
                    ordered_supporting_files.append(pf)

        # Add any remaining non-main files not yet included
        for pf in file_reg.get_supporting_files():
            if pf.normalized_path not in seen_files:
                seen_files.add(pf.normalized_path)
                ordered_supporting_files.append(pf)

        ordered_supporting_content = [pf.source_content for pf in ordered_supporting_files]

        # Assemble ProjectContext
        context = ProjectContext(
            project_files=file_reg.to_dict(),
            macro_registry=macro_reg.all_macros(),
            dependency_graph=graph,
            resolution_result=resolution_result,
            dependency_order=resolution_result.resolution_order,
            ordered_supporting_content=ordered_supporting_content,
            main_program_file=main_file.filename if main_file else None,
            main_program_content=main_file.source_content if main_file else "",
            warnings=resolution_result.warnings.copy(),
            errors=resolution_result.errors.copy(),
            metadata={
                "total_files": len(file_reg),
                "total_macros": len(macro_reg),
                "total_dependencies": len(graph.edges),
                "status": resolution_result.status.value if isinstance(resolution_result.status, ResolutionStatus) else str(resolution_result.status)
            }
        )

        return context
