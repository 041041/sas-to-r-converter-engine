"""
macro_functions.py
──────────────────
Controlled Macro Function Evaluator & Function Registry for SAS Modernization Engine.
Evaluates %EVAL, %SYSEVALF, %UPCASE, %LOWCASE, %SUBSTR, %SCAN, %LENGTH, %INDEX, %TRIM, %LEFT,
and controlled %SYSFUNC() calls deterministically.
"""

from __future__ import annotations
import re
import datetime
from typing import Optional, Callable, Tuple


class MacroFunctionRegistry:
    """
    Registry for SAS macro functions (%EVAL, %SUBSTR, %SYSFUNC, etc.).
    """

    def __init__(self):
        self._registry: dict[str, Callable[..., str]] = {}
        self._register_default_functions()

    def register(self, name: str, fn: Callable[..., str]):
        self._registry[name.upper()] = fn

    def evaluate(self, func_name: str, args_str: str) -> Tuple[Optional[str], bool]:
        """
        Evaluates a macro function call if registered.
        Returns: (evaluated_result, is_supported)
        """
        name = func_name.upper()
        if name in self._registry:
            try:
                res = self._registry[name](args_str)
                return str(res), True
            except Exception:
                return None, False
        return None, False

    def _register_default_functions(self):
        # 1. Numeric functions
        self.register("EVAL", self._eval_expr)
        self.register("SYSEVALF", self._eval_expr)

        # 2. String functions
        self.register("UPCASE", lambda s: s.upper())
        self.register("LOWCASE", lambda s: s.lower())
        self.register("SUBSTR", self._substr)
        self.register("SCAN", self._scan)
        self.register("LENGTH", lambda s: str(len(s)))
        self.register("INDEX", self._index)
        self.register("TRIM", lambda s: s.rstrip())
        self.register("LEFT", lambda s: s.lstrip())

        # 3. System functions
        self.register("SYSFUNC", self._sysfunc)

    def _eval_expr(self, expr: str) -> str:
        """Evaluates arithmetic expressions like %EVAL(100 + 5)."""
        clean_expr = expr.strip()
        # Basic safe math evaluation
        if re.match(r'^[0-9\.\+\-\*/\(\)\s]+$', clean_expr):
            return str(eval(clean_expr))
        return clean_expr

    def _substr(self, args_str: str) -> str:
        """%SUBSTR(string, position, length) - 1-indexed SAS substr."""
        parts = [p.strip() for p in args_str.split(',')]
        string = parts[0]
        pos = int(parts[1]) - 1 if len(parts) > 1 and parts[1].isdigit() else 0
        length = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
        
        pos = max(0, pos)
        if length is not None:
            return string[pos:pos+length]
        return string[pos:]

    def _scan(self, args_str: str) -> str:
        """%SCAN(string, n, delimiter) - 1-indexed SAS word extraction."""
        parts = [p.strip() for p in args_str.split(',')]
        string = parts[0]
        n = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
        delim = parts[2].strip('"\'') if len(parts) > 2 else ' '
        
        tokens = [t for t in string.split(delim) if t]
        idx = n - 1
        if 0 <= idx < len(tokens):
            return tokens[idx]
        return ""

    def _index(self, args_str: str) -> str:
        """%INDEX(string, substring) - 1-indexed position of substring."""
        parts = [p.strip() for p in args_str.split(',')]
        string = parts[0]
        substr = parts[1].strip('"\'') if len(parts) > 1 else ""
        pos = string.find(substr)
        return str(pos + 1) if pos >= 0 else "0"

    def _sysfunc(self, args_str: str) -> str:
        """Controlled %SYSFUNC() handler."""
        sub = args_str.strip().lower()
        if "today()" in sub or "date()" in sub:
            return datetime.date.today().strftime("%d%b%Y").upper()
        if "time()" in sub:
            return datetime.datetime.now().strftime("%H:%M:%S")
        return f"/* %SYSFUNC({args_str}) */"


def evaluate_macro_functions_in_text(text: str, registry: Optional[MacroFunctionRegistry] = None) -> Tuple[str, list[str]]:
    """
    Scans text for %FUNC(...) calls and evaluates registered macro functions.
    Returns: (processed_text, unresolved_warnings)
    """
    if not registry:
        registry = MacroFunctionRegistry()

    unresolved = []
    processed = text

    # Pattern for macro function calls: %FUNC_NAME(args)
    pattern = r'%(\w+)\s*\(([^()]*)\)'
    
    for _ in range(3):  # up to 3 passes for nested function calls
        if '%' not in processed:
            break

        def _replace_fn_call(m):
            fn_name = m.group(1).upper()
            args = m.group(2)
            
            # Skip macro control flow keywords
            if fn_name in ("MACRO", "MEND", "LET", "IF", "THEN", "ELSE", "DO", "END"):
                return m.group(0)
                
            res, is_ok = registry.evaluate(fn_name, args)
            if is_ok and res is not None:
                return res
            else:
                unresolved.append(f"Unresolved macro function: %{fn_name}({args})")
                return m.group(0)

        prev_processed = processed
        processed = re.sub(pattern, _replace_fn_call, processed)
        if processed == prev_processed:
            break

    return processed, unresolved
