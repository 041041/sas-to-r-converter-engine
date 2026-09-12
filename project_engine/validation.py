"""
project_engine/validation.py
─────────────────────────────
Project Validator for formatting project analysis summaries and error/warning messaging.
"""

from __future__ import annotations
from project_engine.models import ProjectContext, ResolutionStatus
from project_engine.classifier import ProgramClassifier


class ProjectValidator:
    """Validates ProjectContext and formats readable reports for UI display."""

    def validate(self, context: ProjectContext) -> dict[str, any]:
        """Returns structured validation status and summary."""
        res = context.resolution_result
        status = res.status

        classifier = ProgramClassifier()
        prog_type = classifier.classify_source(context.main_program_content or "")

        summary = {
            "is_valid": status == ResolutionStatus.RESOLVED,
            "status": status.value if isinstance(status, ResolutionStatus) else str(status),
            "program_type": prog_type.value if hasattr(prog_type, "value") else str(prog_type),
            "files_count": len(context.project_files),
            "macros_count": len(context.macro_registry),
            "dependencies_count": len(context.dependency_graph.edges),
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
        main_node = f"MAIN ({main_name})" if main_name else None

        top_calls = graph.adjacency.get(main_node, []) if main_node in graph.adjacency else []
        if not top_calls:
            # If main node not explicitly linked, root all top-level macros
            called_by_others = {edge.dependency for edge in graph.edges}
            top_calls = [m for m in context.dependency_order if m not in called_by_others]

        for i, mac in enumerate(top_calls):
            is_last = (i == len(top_calls) - 1)
            lines.extend(self._format_sub_tree(context, mac, prefix="", is_last=is_last, visited=set()))

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

        mdef = context.macro_registry.get(node)
        status_icon = "✅" if mdef else "❌ (missing)"
        source_info = f" ({mdef.source_file})" if mdef else ""

        lines.append(f"{prefix}{connector}{node}{source_info} {status_icon}")

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
