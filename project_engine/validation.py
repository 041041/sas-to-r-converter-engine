"""
project_engine/validation.py
─────────────────────────────
Project Validator for formatting project analysis summaries and error/warning messaging.
"""

from __future__ import annotations
from typing import Any
from project_engine.models import DependencyType, ProjectContext, ResolutionStatus
from project_engine.classifier import ProgramClassifier


class ProjectValidator:
    """Validates ProjectContext and formats readable reports for UI display."""

    def validate(self, context: ProjectContext) -> dict[str, Any]:
        """Returns structured validation status and summary."""
        res = context.resolution_result
        status = res.status

        classifier = ProgramClassifier()
        prog_type = classifier.classify_context(context)

        edges = context.dependency_graph.edges
        macro_deps_count = len([e for e in edges if getattr(e, "dependency_type", None) == DependencyType.MACRO_CALL or str(getattr(e, "dependency_type", "")) == "MACRO_CALL"])
        include_deps_count = len([e for e in edges if getattr(e, "dependency_type", None) == DependencyType.INCLUDE or str(getattr(e, "dependency_type", "")) == "INCLUDE"])

        summary = {
            "is_valid": status == ResolutionStatus.RESOLVED,
            "status": status.value if isinstance(status, ResolutionStatus) else str(status),
            "program_type": prog_type.value if hasattr(prog_type, "value") else str(prog_type),
            "files_count": len(context.project_files),
            "macros_count": len(context.macro_registry),
            "dependencies_count": len(edges),
            "macro_dependencies_count": macro_deps_count,
            "include_dependencies_count": include_deps_count,
            "resolved_count": len(res.resolution_order),
            "warnings": context.warnings + res.warnings,
            "errors": context.errors + res.errors
        }
        return summary

    def format_tree_view(self, context: ProjectContext) -> str:
        """Formats a human-readable ASCII dependency tree for UI display."""
        lines = []
        main_name = context.main_program_file or "Main Program"
        lines.append(f"📦 {main_name}")

        graph = context.dependency_graph
        main_node = main_name if main_name in graph.nodes else f"MAIN ({main_name})"

        top_calls = graph.adjacency.get(main_node, []) if main_node in graph.adjacency else []
        if not top_calls and f"MAIN ({main_name})" in graph.adjacency:
            top_calls = graph.adjacency.get(f"MAIN ({main_name})", [])

        if not top_calls:
            # If main node not explicitly linked, root all top-level nodes not called by others
            called_by_others = {edge.dependency for edge in graph.edges}
            top_calls = [m for m in context.dependency_order if m != main_name and m not in called_by_others]

        for i, node in enumerate(top_calls):
            is_last = (i == len(top_calls) - 1)
            lines.extend(self._format_sub_tree(context, node, prefix="", is_last=is_last, visited=set()))

        return "\n".join(lines)

    def _format_sub_tree(
        self,
        context: ProjectContext,
        node: str,
        prefix: str,
        is_last: bool,
        visited: set[str]
    ) -> list[str]:
        lines = []
        connector = "└── " if is_last else "├── "

        is_file = node in context.project_files
        is_macro = node in context.macro_registry
        mdef = context.macro_registry.get(node)
        pf = context.project_files.get(node)

        if is_file:
            icon = "📄 "
            source_info = ""
            status_icon = "✅"
        elif is_macro:
            icon = "🧩 "
            source_info = f" ({mdef.source_file})" if mdef else ""
            status_icon = "✅"
        else:
            icon = "📄 " if node.endswith(".sas") else "🧩 "
            source_info = ""
            status_icon = "❌"

        lines.append(f"{prefix}{connector}{icon}{node}{source_info} {status_icon}")

        if node in visited:
            child_prefix = prefix + ("    " if is_last else "│   ")
            lines.append(f"{child_prefix}└── 🔄 (recursive/cycle)")
            return lines

        visited.add(node)
        children = context.dependency_graph.adjacency.get(node, [])
        child_prefix = prefix + ("    " if is_last else "│   ")

        for idx, child in enumerate(children):
            c_last = (idx == len(children) - 1)
            lines.extend(self._format_sub_tree(context, child, child_prefix, c_last, visited.copy()))

        return lines
