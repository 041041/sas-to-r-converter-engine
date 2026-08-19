"""
macro_execution_context.py
───────────────────────────
SAS Macro Execution Context & Symbol Resolution Engine.
Handles Global & Local Scopes, Symbol Tables, Dynamic Indirect References (&&var&i),
Variable Lookup Precedence, and Multi-Pass String Resolution.
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Optional, Any


@dataclass
class MacroSymbol:
    name: str
    value: str
    is_global: bool = False
    is_parameter: bool = False
    scope_name: str = "GLOBAL"


class MacroScope:
    """Represents a single scope (Global or Local to a macro invocation)."""

    def __init__(self, name: str, parent_scope: Optional[MacroScope] = None):
        self.name = name
        self.parent_scope = parent_scope
        self.symbols: dict[str, MacroSymbol] = {}

    def set_symbol(self, name: str, value: str, is_global: bool = False, is_parameter: bool = False):
        clean_name = name.lstrip('&%').upper()
        self.symbols[clean_name] = MacroSymbol(
            name=clean_name,
            value=str(value),
            is_global=is_global,
            is_parameter=is_parameter,
            scope_name=self.name
        )

    def get_symbol(self, name: str) -> Optional[MacroSymbol]:
        clean_name = name.lstrip('&%').upper()
        if clean_name in self.symbols:
            return self.symbols[clean_name]
        if self.parent_scope:
            return self.parent_scope.get_symbol(clean_name)
        return None


class MacroExecutionContext:
    """
    Manages the call stack of MacroScopes and resolves macro variable references.
    """

    def __init__(self):
        self.global_scope = MacroScope("GLOBAL")
        self.scope_stack: list[MacroScope] = [self.global_scope]

    @property
    def current_scope(self) -> MacroScope:
        return self.scope_stack[-1]

    def push_scope(self, name: str, params: Optional[dict[str, Any]] = None):
        """Pushes a new local scope for a macro invocation."""
        new_scope = MacroScope(name=name, parent_scope=self.current_scope)
        if params:
            for k, v in params.items():
                new_scope.set_symbol(k, str(v) if v is not None else "", is_parameter=True)
        self.scope_stack.append(new_scope)

    def pop_scope(self):
        """Pops the top local scope after a macro completes execution."""
        if len(self.scope_stack) > 1:
            self.scope_stack.pop()

    def set_variable(self, name: str, value: str, is_global: bool = False):
        """
        Sets a macro variable. If is_global is True or variable exists in Global scope,
        sets in Global scope. Otherwise sets in current local scope.
        """
        clean_name = name.lstrip('&%').upper()
        if is_global or len(self.scope_stack) == 1:
            self.global_scope.set_symbol(clean_name, value, is_global=True)
        else:
            # If variable already exists in an upper scope, update it there
            sym = self.current_scope.get_symbol(clean_name)
            if sym and sym.is_global:
                self.global_scope.set_symbol(clean_name, value, is_global=True)
            else:
                self.current_scope.set_symbol(clean_name, value, is_global=False)

    def get_variable(self, name: str) -> Optional[str]:
        """Looks up variable in current local scope, parent scopes, and global scope."""
        sym = self.current_scope.get_symbol(name)
        return sym.value if sym else None

    def resolve_expression(self, expr: str) -> str:
        """
        Multi-pass dynamic symbol resolution engine.
        Handles indirect references like &&var&i, &&ds&i, &prefix._&i, &lib..table.
        """
        if not expr or '&' not in expr:
            return expr

        resolved = expr

        # Run up to 5 passes for nested/indirect resolution (e.g. &&ds&i -> &ds1 -> DM)
        for _ in range(5):
            if '&' not in resolved:
                break

            prev_resolved = resolved

            # Step 1: Replace `&&` with literal `&`
            resolved = re.sub(r'&&', '&', resolved)

            # Step 2: Handle standard single macro variables `&var.` or `&var`
            def _replace_single_amp(m):
                var_name = m.group(1).upper()
                sym_val = self.get_variable(var_name)
                if sym_val is not None:
                    return sym_val
                return m.group(0)  # leave un-substituted if missing

            resolved = re.sub(r'&([a-zA-Z0-9_]+)\.?', _replace_single_amp, resolved)

            if resolved == prev_resolved:
                break

        return resolved
