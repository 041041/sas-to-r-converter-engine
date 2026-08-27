"""
dependency_graph.py
───────────────────
Dependency Graph & Data Lineage Analyzer for Enterprise SAS Modernization Engine.
Builds dataset dependencies, macro call hierarchies, and variable scope maps.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from sas_ast import ProgramAST, MacroIR, ProgramStep


@dataclass
class DatasetNode:
    name: str
    produced_by_step: int | None = None
    consumed_by_steps: list[int] = field(default_factory=list)
    is_external: bool = False  # True if dataset comes from LIBNAME or file upload


@dataclass
class MacroCallNode:
    macro_name: str
    called_by: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)


@dataclass
class DependencyGraph:
    """Complete program dependency graph representation."""
    dataset_nodes: dict[str, DatasetNode] = field(default_factory=dict)
    macro_call_graph: dict[str, MacroCallNode] = field(default_factory=dict)
    execution_order: list[int] = field(default_factory=list)
    variable_scope_map: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "datasets": {
                name: {
                    "produced_by": node.produced_by_step,
                    "consumed_by": node.consumed_by_steps,
                    "is_external": node.is_external
                } for name, node in self.dataset_nodes.items()
            },
            "macro_calls": {
                name: {
                    "called_by": node.called_by,
                    "calls": node.calls
                } for name, node in self.macro_call_graph.items()
            },
            "execution_order": self.execution_order
        }


def build_dependency_graph(ast: ProgramAST) -> DependencyGraph:
    """
    Analyzes a ProgramAST and constructs a DependencyGraph mapping dataset lineage
    and macro call structures.
    """
    graph = DependencyGraph()
    
    # 1. Dataset Dependency Graph
    for step in ast.steps:
        graph.execution_order.append(step.step_index)
        
        # Process output datasets (producers)
        for out_ds in step.output_datasets:
            ds_name = out_ds.upper()
            if ds_name not in graph.dataset_nodes:
                graph.dataset_nodes[ds_name] = DatasetNode(name=ds_name)
            graph.dataset_nodes[ds_name].produced_by_step = step.step_index
            
        # Process input datasets (consumers)
        for in_ds in step.input_datasets:
            ds_name = in_ds.upper()
            if ds_name not in graph.dataset_nodes:
                # If not produced by prior step, mark as external
                graph.dataset_nodes[ds_name] = DatasetNode(name=ds_name, is_external=True)
            graph.dataset_nodes[ds_name].consumed_by_steps.append(step.step_index)
            
    # 2. Macro Call Graph
    for macro_name, macro_ir in ast.macros.items():
        if macro_name not in graph.macro_call_graph:
            graph.macro_call_graph[macro_name] = MacroCallNode(macro_name=macro_name)
            
        for sub_macro in macro_ir.nested_macros:
            sub_name = sub_macro.upper()
            graph.macro_call_graph[macro_name].calls.append(sub_name)
            if sub_name not in graph.macro_call_graph:
                graph.macro_call_graph[sub_name] = MacroCallNode(macro_name=sub_name)
            graph.macro_call_graph[sub_name].called_by.append(macro_name)
            
    # 3. Variable Scope Map
    for macro_name, macro_ir in ast.macros.items():
        param_names = [p.name for p in macro_ir.parameters]
        graph.variable_scope_map[macro_name] = param_names + macro_ir.local_vars
        
    return graph


def topological_sort_macros(macro_call_graph: dict[str, MacroCallNode]) -> tuple[list[str], bool, str]:
    """
    Performs topological sort on macro_call_graph.
    Returns (sorted_macro_names, has_cycle, error_message).
    If macro A calls macro B (A depends on B), B must appear BEFORE A in execution/definition order.
    """
    nodes = list(macro_call_graph.keys())
    deps = {node: set(macro_call_graph[node].calls) for node in nodes}
    
    # DFS for cycle detection
    visited = {node: 0 for node in nodes}  # 0: unvisited, 1: visiting, 2: visited
    cycle_found = False
    cycle_node = ""

    def dfs(node):
        nonlocal cycle_found, cycle_node
        visited[node] = 1
        for dep in deps.get(node, []):
            if dep in visited:
                if visited[dep] == 1:
                    cycle_found = True
                    cycle_node = dep
                    return
                elif visited[dep] == 0:
                    dfs(dep)
            if cycle_found:
                return
        visited[node] = 2

    for node in nodes:
        if visited[node] == 0:
            dfs(node)
            if cycle_found:
                return [], True, f"Macro dependency cycle detected involving %{cycle_node}"

    # Topological sort (post-order DFS: dependencies visit first)
    ordered = []
    seen = set()

    def visit(node):
        if node in seen:
            return
        seen.add(node)
        for dep in deps.get(node, []):
            if dep in macro_call_graph:
                visit(dep)
        ordered.append(node)

    for node in nodes:
        visit(node)

    return ordered, False, ""

