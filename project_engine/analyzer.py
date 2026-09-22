"""
project_engine/analyzer.py
───────────────────────────
Project Analyzer orchestrator for building ProjectContext from uploaded files.
"""

from __future__ import annotations
from typing import Sequence
from .models import (
    DependencyType,
    ProjectContext,
    ResolutionStatus
)
from .file_registry import ProjectFileRegistry
from .macro_registry import MacroRegistry
from .dependency_parser import DependencyParser
from .include_parser import IncludeParser
from .dependency_graph import DependencyGraphBuilder
from .resolver import DependencyResolver


class ProjectAnalyzer:
    """Orchestrates file registration, macro discovery, dependency graphing, and resolution."""

    def __init__(
        self,
        parser: DependencyParser | None = None,
        include_parser: IncludeParser | None = None,
        graph_builder: DependencyGraphBuilder | None = None,
        resolver: DependencyResolver | None = None
    ) -> None:
        self.parser = parser or DependencyParser()
        self.include_parser = include_parser or IncludeParser()
        self.graph_builder = graph_builder or DependencyGraphBuilder(
            parser=self.parser,
            include_parser=self.include_parser
        )
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
        # Group supporting files by topological dependency order (both included files and files containing macros)
        ordered_supporting_files = []
        seen_files = set()

        for item in resolution_result.resolution_order:
            pf = file_reg.get_file(item)
            if pf:
                if not pf.is_main and pf.normalized_path not in seen_files:
                    seen_files.add(pf.normalized_path)
                    ordered_supporting_files.append(pf)
            else:
                mdef = macro_reg.get_macro(item)
                if mdef:
                    mpf = file_reg.get_file(mdef.source_file)
                    if mpf and not mpf.is_main and mpf.normalized_path not in seen_files:
                        seen_files.add(mpf.normalized_path)
                        ordered_supporting_files.append(mpf)

        # Add any remaining non-main files not yet included
        for pf in file_reg.get_supporting_files():
            if pf.normalized_path not in seen_files:
                seen_files.add(pf.normalized_path)
                ordered_supporting_files.append(pf)

        ordered_supporting_content = [pf.source_content for pf in ordered_supporting_files]

        macro_deps_count = len([e for e in graph.edges if e.dependency_type == DependencyType.MACRO_CALL])
        include_deps_count = len([e for e in graph.edges if e.dependency_type == DependencyType.INCLUDE])

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
                "macro_dependencies_count": macro_deps_count,
                "include_dependencies_count": include_deps_count,
                "status": resolution_result.status.value if isinstance(resolution_result.status, ResolutionStatus) else str(resolution_result.status)
            }
        )

        return context
