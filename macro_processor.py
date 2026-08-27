"""
macro_processor.py
──────────────────
SAS Macro Pre-processor for Smart SAS to R Converter.

Handles:
  - %let variable substitution
  - Simple and nested macro definitions/calls
  - %if/%then/%else logic
  - %do/%to/%end numeric loops
  - Dynamic macro name resolution
  - SQL-generated macro variable hints
  - Multi-file macro library merging
"""

from __future__ import annotations
import re


# ─────────────────────────────────────────────────────────────────
# HELPER UTILITIES
# ─────────────────────────────────────────────────────────────────

def _strip_comments(code: str) -> str:
    """Remove SAS block comments /* ... */ and * ... ; line comments."""
    # Block comments
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
    # Line comments starting with * (only at statement start)
    code = re.sub(r'^\s*\*[^;]*;', '', code, flags=re.MULTILINE)
    return code


def _normalize_whitespace(code: str) -> str:
    """Collapse multiple blank lines to one."""
    return re.sub(r'\n{3,}', '\n\n', code).strip()


# ─────────────────────────────────────────────────────────────────
# MACRO SCOPE FRAME
# ─────────────────────────────────────────────────────────────────

class MacroFrame:
    """Represents a single macro invocation scope frame."""
    def __init__(self, name: str, is_global: bool = False):
        self.name = name.upper()
        self.is_global = is_global
        self.vars: dict[str, str] = {}
        self.local_declared: set[str] = set()

    def get_var(self, name: str) -> str | None:
        return self.vars.get(name.upper())

    def set_var(self, name: str, val: str):
        self.vars[name.upper()] = val


# ─────────────────────────────────────────────────────────────────
# MAIN PROCESSOR CLASS
# ─────────────────────────────────────────────────────────────────

class SASMacroProcessor:
    """
    Pre-processes SAS code by expanding macros before LLM conversion.
    """

    MAX_DEPTH = 10  # max recursion depth for nested macro calls

    def __init__(self):
        self.macro_library: dict = {}   # {NAME: {params, body}}
        self.let_vars: dict = {}        # {NAME: value}
        self.sql_var_hints: list = []   # hints for LLM
        self.warnings: list = []        # non-fatal issues
        self.global_frame = MacroFrame("GLOBAL", is_global=True)
        self.frame_stack: list[MacroFrame] = [self.global_frame]

    def _get_active_vars(self, extra_vars: dict = None) -> dict[str, str]:
        active = {}
        for frame in self.frame_stack:
            active.update(frame.vars)
        if extra_vars:
            active.update(extra_vars)
        return active

    def _set_var_in_scope(self, name: str, val: str):
        name = name.upper()
        curr = self.frame_stack[-1]
        if name in curr.local_declared or name in curr.vars:
            curr.vars[name] = val
            return

        for frame in reversed(self.frame_stack):
            if name in frame.vars:
                frame.vars[name] = val
                return

        curr.vars[name] = val
        if curr.is_global:
            self.let_vars[name] = val

    # ── PUBLIC ENTRY POINT ────────────────────────────────────────

    def process(self, sas_code: str, extra_files: list[str] = None, expand_path_b: bool = True) -> tuple[str, list, list]:
        """
        Main entry point.

        Args:
            sas_code:        Main SAS program text
            extra_files:     List of additional .sas macro library strings
            expand_path_b:   If False, leaves PATH_B reusable utility macro calls unexpanded

        Returns:
            (expanded_code, warnings, sql_hints)
        """
        self.macro_library = {}
        self.global_frame = MacroFrame("GLOBAL", is_global=True)
        self.frame_stack = [self.global_frame]
        self.let_vars = self.global_frame.vars
        self.sql_var_hints = []
        self.warnings = []

        # 1. Merge extra macro library files first
        combined = ""
        if extra_files:
            for f in extra_files:
                combined += _strip_comments(f) + "\n"
        combined += _strip_comments(sas_code)

        # 2. Extract all macro definitions first
        self._parse_macro_definitions(combined)

        # 3. Strip top-level macro definition blocks from code
        code_without_defs = self._remove_macro_definitions(combined)
        code_without_defs = self._parse_scope_statements(code_without_defs)

        # 4. Extract top-level %let variables (outside macro definitions)
        self._parse_let_variables(code_without_defs)

        # 5. Expand %do loops
        code_do = self._expand_do_loops(code_without_defs)

        # 7. Detect PROC SQL INTO: macro vars
        self._detect_sql_macro_vars(code_do)

        # 8. Recursively expand macro calls
        expanded = self._expand_macro_calls(code_do, expand_path_b=expand_path_b)

        # 8.5 Substitute global macro variables updated during macro execution
        expanded = self._substitute_let_vars(expanded, self._get_active_vars())
        expanded = self._evaluate_if_else(expanded, self._get_active_vars())

        # 9. Final cleanup
        final_code = self._cleanup(expanded)

        return (final_code, self.warnings, self.sql_var_hints)

    def _parse_scope_statements(self, code: str) -> str:
        """Parse %LOCAL and %GLOBAL variable declarations."""
        curr = self.frame_stack[-1]
        for lm in re.finditer(r'%local\s+([^;]+);', code, re.IGNORECASE):
            raw_vars = lm.group(1).strip()
            for v in raw_vars.split():
                v_name = v.strip().lstrip('&').upper()
                if v_name:
                    curr.local_declared.add(v_name)
                    curr.vars[v_name] = curr.vars.get(v_name, "")

        for gm in re.finditer(r'%global\s+([^;]+);', code, re.IGNORECASE):
            raw_vars = gm.group(1).strip()
            for v in raw_vars.split():
                v_name = v.strip().lstrip('&').upper()
                if v_name:
                    self.global_frame.vars[v_name] = self.global_frame.vars.get(v_name, "")

        return re.sub(r'%(?:local|global)\s+[^;]+;', '', code, flags=re.IGNORECASE)

    # ── STEP 2: PARSE %LET ───────────────────────────────────────

    def _evaluate_bounded_macro_functions(self, expr: str, let_dict: dict = None) -> str | None:
        """
        Evaluates bounded static SAS macro string & date functions:
          - %sysfunc(today()) / %sysfunc(date()) -> "Sys.Date()"
          - %substr(str, start, [len])
          - %scan(str, n, [delimiter])
          - %index(str, substr)
          - %length(str)
        Returns evaluated string or None if un-evaluable / unsupported.
        """
        if let_dict is None:
            let_dict = self._get_active_vars()

        # Reject unsupported macro functions or indirect references
        if '&&' in expr:
            return None

        # Reject unsupported macro quoting / eval functions
        unsupported = [
            r'%eval\b', r'%sysevalf\b', r'%esevalf\b',
            r'%nrstr\b', r'%bquote\b', r'%nrbquote\b', r'%superq\b'
        ]
        for pat in unsupported:
            if re.search(pat, expr, re.I):
                return None

        # Substitute known macro variables first
        for _ in range(5):
            orig = expr
            for k, v in let_dict.items():
                if k:
                    expr = re.sub(rf'&{k}\.', str(v), expr, flags=re.I)
                    expr = re.sub(rf'&{k}\b', str(v), expr, flags=re.I)
            if expr == orig:
                break

        # If unresolved macro variable remains, return None
        if re.search(r'&\w+', expr):
            return None

        # Evaluate nested macro calls from innermost to outermost (max 10 passes)
        for _ in range(10):
            # 1. %SYSFUNC(today() [, format]) or %SYSFUNC(date() [, format])
            m_sys = re.search(r'%sysfunc\s*\(\s*(today|date)\s*\(\s*\)\s*(?:,\s*[^)]+)?\s*\)', expr, re.I)
            if m_sys:
                expr = expr[:m_sys.start()] + "Sys.Date()" + expr[m_sys.end():]
                continue

            # Guard: any other %sysfunc call -> SAFE REJECT
            if re.search(r'%sysfunc\b', expr, re.I):
                return None

            # 2. %LENGTH(text)
            m_len = re.search(r'%length\s*\(\s*([^()]*)\s*\)', expr, re.I)
            if m_len:
                raw_text = m_len.group(1).strip("'\"")
                expr = expr[:m_len.start()] + str(len(raw_text)) + expr[m_len.end():]
                continue

            # 3. %INDEX(text, substr)
            m_idx = re.search(r'%index\s*\(\s*([^(),]+)\s*,\s*([^()]+)\s*\)', expr, re.I)
            if m_idx:
                src = m_idx.group(1).strip().strip("'\"")
                sub = m_idx.group(2).strip().strip("'\"")
                found_pos = src.find(sub)
                res_idx = (found_pos + 1) if found_pos != -1 else 0
                expr = expr[:m_idx.start()] + str(res_idx) + expr[m_idx.end():]
                continue

            # 4. %SUBSTR(text, start [, len])
            m_sub = re.search(r'%substr\s*\(\s*([^(),]+)\s*,\s*(\d+)\s*(?:,\s*(\d+))?\s*\)', expr, re.I)
            if m_sub:
                src = m_sub.group(1).strip().strip("'\"")
                start = int(m_sub.group(2))
                length = int(m_sub.group(3)) if m_sub.group(3) else None
                if start < 1 or start > len(src) + 1:
                    return None
                if length is not None:
                    if length < 0:
                        return None
                    res_str = src[start - 1 : start - 1 + length]
                else:
                    res_str = src[start - 1 :]
                expr = expr[:m_sub.start()] + res_str + expr[m_sub.end():]
                continue

            # 5. %SCAN(text, n [, delim])
            m_scan = re.search(r'%scan\s*\(\s*([^(),]+)\s*,\s*(\d+)\s*(?:,\s*(%str\([^)]*\)|[^(),]+))?\s*\)', expr, re.I)
            if m_scan:
                src = m_scan.group(1).strip().strip("'\"")
                n_idx = int(m_scan.group(2))
                raw_delim = m_scan.group(3) if m_scan.group(3) else ""
                if raw_delim:
                    raw_delim = raw_delim.strip()
                    m_str_delim = re.match(r'^%str\s*\(\s*(.*?)\s*\)$', raw_delim, re.I)
                    if m_str_delim:
                        delim_char = m_str_delim.group(1).strip("'\"")
                    else:
                        delim_char = raw_delim.strip("'\"")
                else:
                    delim_char = None

                if delim_char:
                    tokens = [t for t in src.split(delim_char) if t]
                else:
                    tokens = src.split()

                if 1 <= n_idx <= len(tokens):
                    res_scan = tokens[n_idx - 1]
                else:
                    res_scan = ""

                expr = expr[:m_scan.start()] + res_scan + expr[m_scan.end():]
                continue

            # No more macro functions found
            break

        # If any un-expanded macro function call remains (%something), return None
        if re.search(r'%\w+', expr):
            return None

        return expr

    def _parse_let_variables(self, code: str):
        """Extract all %let name = value; statements."""
        pattern = re.compile(
            r'%let\s+(\w+)\s*=\s*(.*?)\s*;',
            re.IGNORECASE | re.DOTALL
        )
        for m in pattern.finditer(code):
            name  = m.group(1).strip().upper()
            value = m.group(2).strip()
            if '&&' in value:
                val_res, ok = self._resolve_bounded_indirect_reference(value, self._get_active_vars())
                if ok:
                    value = val_res
                else:
                    self.warnings.append("⚠️ Indirect macro variable reference (&&) is unsupported — left unexpanded.")
            if re.search(r'%\w+', value):
                eval_val = self._evaluate_bounded_macro_functions(value, self._get_active_vars())
                if eval_val is not None:
                    value = eval_val
                elif '&&' not in value:
                    self.warnings.append(
                        f"⚠️ Un-evaluable or unsupported macro function in %LET {name} = {value} — left unexpanded."
                    )
            self._set_var_in_scope(name, value)

    # ── STEP 3: PARSE MACRO DEFINITIONS ─────────────────────────

    def _parse_macro_definitions(self, code: str):
        """Extract %macro name(params); body %mend; blocks using balanced nesting detection."""
        pos = 0
        n = len(code)
        while pos < n:
            m = re.search(r'%macro\s+(\w+)\s*(?:\((.*?)\))?\s*;', code[pos:], re.IGNORECASE | re.DOTALL)
            if not m:
                break

            header_start = pos + m.start()
            header_end = pos + m.end()
            macro_name = m.group(1).strip().upper()
            params_raw = m.group(2) or ""

            depth = 1
            cur = header_end
            body_start = header_end
            body_end = None
            block_end = None

            token_pat = re.compile(r'(%macro\b|%mend(?:\s+\w+)?\s*;)', re.IGNORECASE)

            while cur < n:
                tm = token_pat.search(code, cur)
                if not tm:
                    break
                tok = tm.group(1).upper()
                if tok.startswith('%MACRO'):
                    depth += 1
                elif tok.startswith('%MEND'):
                    depth -= 1
                    if depth == 0:
                        body_end = tm.start()
                        block_end = tm.end()
                        break
                cur = tm.end()

            if depth != 0 or block_end is None:
                self.warnings.append(f"⚠️ Malformed or unclosed %MACRO definition for %{macro_name} — safe reject.")
                pos = header_end
                continue

            body = code[body_start:body_end].strip()

            params: list[str] = []
            defaults: dict[str, str] = {}
            if params_raw.strip():
                for p in params_raw.split(','):
                    p = p.strip()
                    if not p:
                        continue
                    if '=' in p:
                        param_name, default_val = p.split('=', 1)
                        param_name = param_name.strip().lstrip('&').upper()
                        defaults[param_name] = default_val.strip()
                    else:
                        param_name = p.lstrip('&').upper()
                    params.append(param_name)

            self.macro_library[macro_name] = {
                "params": params,
                "defaults": defaults,
                "body": body,
            }

            # Recursively extract nested macro definitions inside body
            if re.search(r'%macro\b', body, re.IGNORECASE):
                self._parse_macro_definitions(body)

            pos = block_end

    # ── STEP 4: REMOVE MACRO DEFINITIONS ────────────────────────

    def _remove_macro_definitions(self, code: str) -> str:
        """Strip top-level %macro...%mend blocks from code using balanced block scanning."""
        pos = 0
        result = []
        n = len(code)
        last_idx = 0

        while pos < n:
            m = re.search(r'%macro\s+(\w+)\s*(?:\((.*?)\))?\s*;', code[pos:], re.IGNORECASE | re.DOTALL)
            if not m:
                result.append(code[last_idx:])
                break

            header_start = pos + m.start()
            header_end = pos + m.end()

            depth = 1
            cur = header_end
            block_end = None

            token_pat = re.compile(r'(%macro\b|%mend(?:\s+\w+)?\s*;)', re.IGNORECASE)

            while cur < n:
                tm = token_pat.search(code, cur)
                if not tm:
                    break
                tok = tm.group(1).upper()
                if tok.startswith('%MACRO'):
                    depth += 1
                elif tok.startswith('%MEND'):
                    depth -= 1
                    if depth == 0:
                        block_end = tm.end()
                        break
                cur = tm.end()

            if block_end is None:
                result.append(code[last_idx:])
                break

            result.append(code[last_idx:header_start])
            last_idx = block_end
            pos = block_end

        return "".join(result)

    # ── STEP 5: SUBSTITUTE %LET VARS ────────────────────────────

    def _substitute_let_vars(self, code: str, let_dict: dict) -> str:
        """Replace &var and &var. references with their values, handling indirect && references."""
        has_indirect = '&&' in code
        for _ in range(5):
            orig_code = code
            for name, value in let_dict.items():
                if not name:
                    continue
                # &NAME. (with dot separator)
                code = re.sub(rf'(?<!&)&{name}\.', str(value), code, flags=re.IGNORECASE)
                # &NAME (without dot)
                code = re.sub(rf'(?<!&)&{name}\b', str(value), code, flags=re.IGNORECASE)
            if code == orig_code:
                break
        return code

    # ── HELPER: RESOLVE BOUNDED INDIRECT REFERENCES ─────────────

    def _resolve_bounded_indirect_reference(self, code_str: str, iter_vars: dict, active_iter: str = None) -> tuple[str, bool]:
        """
        Resolves bounded SAS indirect macro variable references of the form:
           &&<base>&<iter>
        when <iter> matches the active %DO loop iterator and target variable <base><iter_val>
        exists in the symbol table.

        Returns (resolved_code, success_flag). If failed / invalid, returns (code_str, False).
        """
        # 1. Reject multi-level indirection (&&&&) or 3+ consecutive ampersands
        if re.search(r'(?:&&){2,}', code_str) or re.search(r'&{3,}', code_str):
            self.warnings.append("⚠️ Multi-level indirect macro reference (&&&&) is unsupported — safe reject.")
            return code_str, False

        # 2. Reject unsupported sysfunc or dynamic calls with &&
        if re.search(r'%sysfunc\s*\(\s*\w+\s*\([^)]*&&', code_str, re.I):
            self.warnings.append("⚠️ Unsupported %SYSFUNC with indirect reference — safe reject.")
            return code_str, False

        # Find all &&<base>&<iter> or &&<base><digit> patterns
        pattern = re.compile(r'&&\s*([A-Za-z_]\w*)\s*&([A-Za-z_]\w*)\.?', re.IGNORECASE)
        pattern_digit = re.compile(r'&&\s*([A-Za-z_]\w*?)(\d+)\b', re.IGNORECASE)

        failed = False
        def replace_indirect(m):
            nonlocal failed
            base_name = m.group(1).upper()
            iter_name = m.group(2).upper()

            # Check if iter_name matches active_iter and is in iter_vars
            if not active_iter or iter_name not in iter_vars or iter_name != active_iter.upper():
                self.warnings.append(f"⚠️ Unknown or inactive loop iterator &{iter_name} in indirect reference — safe reject.")
                failed = True
                return m.group(0)

            iter_val = iter_vars[iter_name]
            target_var_name = f"{base_name}{iter_val}".upper()

            if target_var_name not in iter_vars:
                self.warnings.append(f"⚠️ Missing target macro variable &{target_var_name} for indirect reference — safe reject.")
                failed = True
                return m.group(0)

            resolved_val = iter_vars[target_var_name]
            return str(resolved_val)

        def replace_indirect_digit(m):
            base_name = m.group(1).upper()
            digit_val = m.group(2)
            target_var_name = f"{base_name}{digit_val}".upper()
            if target_var_name in iter_vars:
                return str(iter_vars[target_var_name])
            return m.group(0)

        res_code = pattern.sub(replace_indirect, code_str)
        res_code = pattern_digit.sub(replace_indirect_digit, res_code)
        if failed:
            return code_str, False
        return res_code, True

    # ── STEP 6: EXPAND %DO LOOPS ────────────────────────────────

    def _expand_do_loops(self, code_str: str, local_vars: dict = None) -> str:
        """
        Expand %do i = start %to end; body %end; loops.
        Handles nested loops recursively using balanced block extraction and substitutes loop-local %let statements.
        """
        vars_to_sub = {**self.let_vars, **(local_vars or {})}

        pos = 0
        while pos < len(code_str):
            m = re.search(r'%do\s+(\w+)\s*=\s*(.*?)\s*%to\s*(.*?)(?:\s*%by\s*(.*?))?\s*;', code_str[pos:], re.IGNORECASE)
            if not m:
                break
            start_idx = pos + m.start()
            var = m.group(1).upper()
            start_str = self._substitute_let_vars(m.group(2).strip(), vars_to_sub)
            end_str = self._substitute_let_vars(m.group(3).strip(), vars_to_sub)
            step_str = self._substitute_let_vars(m.group(4).strip(), vars_to_sub) if m.group(4) else "1"
            try:
                start = int(start_str)
                end   = int(end_str)
                step  = int(step_str)
            except ValueError:
                start, end, step = 1, 1, 1

            body_offset = pos + m.end()
            body, end_pos = self._extract_do_end_block(code_str, body_offset)
            if body is None:
                pos = body_offset
                continue

            expanded = ""
            for i in range(start, end + 1, step):
                iter_vars = {**vars_to_sub, var: str(i)}
                iteration = body
                for lm in re.finditer(r'%let\s+(\w+)\s*=\s*(.*?)\s*;', iteration, re.IGNORECASE):
                    let_name = lm.group(1).upper()
                    let_val_raw = lm.group(2).strip()
                    let_val_sub = self._substitute_let_vars(let_val_raw, iter_vars)
                    if '&&' in let_val_sub:
                        let_val_sub, _ = self._resolve_bounded_indirect_reference(let_val_sub, iter_vars, var)
                    iter_vars[let_name] = let_val_sub

                iteration = re.sub(r'%let\s+\w+\s*=\s*.*?;', '', iteration, flags=re.IGNORECASE)
                if '&&' in iteration:
                    iteration, _ = self._resolve_bounded_indirect_reference(iteration, iter_vars, var)

                iteration = self._substitute_let_vars(iteration, iter_vars)
                iteration = self._evaluate_if_else(iteration, iter_vars)
                expanded += iteration + "\n"
            code_str = code_str[:start_idx] + expanded + code_str[end_pos:]
            pos = start_idx + len(expanded)

        return code_str

    # ── STEP 7: DETECT SQL MACRO VARS ───────────────────────────

    def _detect_sql_macro_vars(self, code: str):
        """
        Find PROC SQL INTO: patterns — these create macro vars from data.
        We can't resolve them statically, but we generate LLM hints.
        """
        pattern = re.compile(
            r'select\s+(.+?)\s+into\s+:(\w+)\s+from\s+([\w.]+)',
            re.IGNORECASE | re.DOTALL
        )
        for m in pattern.finditer(code):
            expr  = m.group(1).strip()
            var   = m.group(2).strip()
            table = m.group(3).strip()
            hint  = (f"Macro variable &{var} was generated by SQL: "
                     f"SELECT {expr} INTO :{var} FROM {table}. "
                     f"In R, compute this with dplyr before using the value.")
            self.sql_var_hints.append(hint)
            self.warnings.append(
                f"⚠️ SQL-generated macro variable &{var} detected — "
                f"auto-resolved to R comment. Review generated code."
            )

    # ── STEP 8: EXPAND MACRO CALLS ──────────────────────────────

    def _expand_macro_calls(self, code: str, depth: int = 0, local_vars: dict = None, active_macros: set = None, expand_path_b: bool = True) -> str:
        """
        Recursively expand macro calls in code.
        Handles: %macro_name; and %macro_name(args);
        """
        if active_macros is None:
            active_macros = set()

        if depth > self.MAX_DEPTH:
            self.warnings.append(
                "⚠️ Maximum macro recursion depth reached. "
                "Some nested macros may not be fully expanded."
            )
            return code

        # Pattern: %NAME; or %NAME(args);
        call_pattern = re.compile(
            r'%(\w+)\s*(?:\(([^)]*)\))?\s*;',
            re.IGNORECASE
        )

        changed = True
        passes = 0
        while changed and passes < 20:
            changed = False
            passes += 1

            def replace_call(match):
                nonlocal changed
                name     = match.group(1).upper()
                args_raw = match.group(2) or ""

                # Skip SAS built-in macro statements
                BUILTINS = {
                    'IF', 'THEN', 'ELSE', 'DO', 'END', 'LET', 'PUT',
                    'GLOBAL', 'LOCAL', 'SYMDEL', 'INCLUDE', 'MEND',
                    'MACRO', 'RETURN', 'ABORT', 'GOTO', 'LABEL',
                    'SYSEXEC', 'SYSCALL', 'RUN', 'QUIT'
                }
                if name in BUILTINS:
                    return match.group(0)

                if name in active_macros:
                    self.warnings.append(
                        f"⚠️ Recursive call to macro %{name} detected — safe reject."
                    )
                    return match.group(0)

                if name not in self.macro_library:
                    # Try dynamic resolution
                    resolved = self._try_resolve_dynamic_name(name)
                    if resolved and resolved in self.macro_library:
                        name = resolved
                    else:
                        self.warnings.append(
                            f"⚠️ Macro %{name} called but not defined — left as-is."
                        )
                        return match.group(0)

                macro    = self.macro_library[name]
                if not expand_path_b:
                    from macro_converter import classify_macro
                    cls_res  = classify_macro(name, macro, all_macro_defs=self.macro_library)
                    if cls_res == 'PATH_B':
                        # PATH_B is a reusable R utility — do NOT expand macro body into DATA/PROC step text!
                        return match.group(0)

                params   = macro["params"]
                defaults = macro.get("defaults", {})
                body     = macro["body"]
                local_let = {}

                # Parse arguments
                args_list = self._split_args(args_raw) if args_raw.strip() else []
                arg_dict = {}
                positional_vals = []

                for arg in args_list:
                    if '=' in arg:
                        k, v = arg.split('=', 1)
                        param_name = k.strip().lstrip('&').upper()
                        if param_name not in params:
                            self.warnings.append(
                                f"⚠️ Unrecognized parameter '{param_name}' for macro %{name} — left unexpanded."
                            )
                            return match.group(0)
                        arg_dict[param_name] = v.strip()
                    else:
                        positional_vals.append(arg.strip())

                if len(positional_vals) > len(params):
                    self.warnings.append(
                        f"⚠️ Parameter count mismatch for macro %{name}: expected at most {len(params)} positional arguments, got {len(positional_vals)} — left unexpanded."
                    )
                    return match.group(0)

                pos_idx = 0
                for param in params:
                    if param in arg_dict:
                        local_let[param] = arg_dict[param]
                    elif pos_idx < len(positional_vals):
                        local_let[param] = positional_vals[pos_idx]
                        pos_idx += 1
                    elif param in defaults:
                        local_let[param] = defaults[param]
                    else:
                        self.warnings.append(
                            f"⚠️ Missing required parameter '{param}' for macro %{name} — left unexpanded."
                        )
                        return match.group(0)

                # Substitute global & caller %let vars in local parameter values
                caller_vars = self._get_active_vars(local_vars)
                for k, v in list(local_let.items()):
                    local_let[k] = self._substitute_let_vars(str(v), caller_vars)

                # Push new invocation frame
                frame = MacroFrame(name)
                for k, v in local_let.items():
                    frame.set_var(k, v)
                self.frame_stack.append(frame)

                # Diagnostic logging for invocation parameter tracking
                p_str = ", ".join(f"{k.lower()}:{v}" for k, v in local_let.items())
                # print(f"MACRO INVOCATION: name={name} params={{{p_str}}}")

                scope_vars = self._get_active_vars()

                # Extract and apply scope statements (%local / %global) in macro body
                body_scoped = self._parse_scope_statements(body)
                body_scoped = self._remove_macro_definitions(body_scoped)

                # Extract and apply top-level %let inside macro body before %do loops (masking %do blocks)
                masked_body = body_scoped
                do_blocks = []
                while True:
                    m_do = re.search(r'%do\b', masked_body, re.IGNORECASE)
                    if not m_do:
                        break
                    block, end_pos = self._extract_do_end_block(masked_body, m_do.end())
                    if block is None:
                        break
                    placeholder = f"___DO_BLOCK_{len(do_blocks)}___"
                    do_blocks.append(masked_body[m_do.start():end_pos])
                    masked_body = masked_body[:m_do.start()] + placeholder + masked_body[end_pos:]

                for lm in re.finditer(r'%let\s+(\w+)\s*=\s*(.*?)\s*;', masked_body, re.IGNORECASE):
                    let_name = lm.group(1).upper()
                    let_val_raw = lm.group(2).strip()
                    let_val_sub = self._substitute_let_vars(let_val_raw, self._get_active_vars())
                    eval_val = self._evaluate_bounded_macro_functions(let_val_sub, self._get_active_vars())
                    if eval_val is not None:
                        let_val_sub = eval_val
                    self._set_var_in_scope(let_name, let_val_sub)

                masked_body = re.sub(r'%let\s+\w+\s*=\s*.*?;', '', masked_body, flags=re.IGNORECASE)
                for idx, blk in enumerate(do_blocks):
                    masked_body = masked_body.replace(f"___DO_BLOCK_{idx}___", blk)

                # Expand %do loops in body with updated scope vars
                expanded = self._expand_do_loops(masked_body, self._get_active_vars())

                # Retrieve updated scope vars after %let statements and %do loops
                scope_vars = self._get_active_vars()

                expanded = self._substitute_let_vars(expanded, scope_vars)
                expanded = self._evaluate_if_else(expanded, scope_vars)

                # Process %let statements revealed inside evaluated %if/%then/%else branches
                for lm in re.finditer(r'%let\s+(\w+)\s*=\s*(.*?)\s*;', expanded, re.IGNORECASE):
                    let_name = lm.group(1).upper()
                    let_val_raw = lm.group(2).strip()
                    let_val_sub = self._substitute_let_vars(let_val_raw, self._get_active_vars())
                    eval_val = self._evaluate_bounded_macro_functions(let_val_sub, self._get_active_vars())
                    if eval_val is not None:
                        let_val_sub = eval_val
                    self._set_var_in_scope(let_name, let_val_sub)

                expanded = re.sub(r'%let\s+\w+\s*=\s*.*?;', '', expanded, flags=re.IGNORECASE)

                # Re-substitute variables with updated scope vars after branch evaluation
                scope_vars = self._get_active_vars()
                expanded = self._substitute_let_vars(expanded, scope_vars)

                # Recurse for any newly introduced macro calls
                expanded = self._expand_macro_calls(
                    expanded,
                    depth=depth + 1,
                    local_vars=scope_vars,
                    active_macros=active_macros | {name}
                )

                self.frame_stack.pop()

                changed = True
                return expanded + "\n"

            code = call_pattern.sub(replace_call, code)

        if changed:
            code = self._expand_macro_calls(code, depth + 1, active_macros=active_macros)

        return code

    # ── HELPER: SPLIT MACRO ARGS ─────────────────────────────────

    def _split_args(self, args_raw: str) -> list[str]:
        """Split macro arguments by comma, respecting nested parentheses."""
        args = []
        depth = 0
        current = ""
        for ch in args_raw:
            if ch == '(':
                depth += 1
                current += ch
            elif ch == ')':
                depth -= 1
                current += ch
            elif ch == ',' and depth == 0:
                args.append(current.strip())
                current = ""
            else:
                current += ch
        if current.strip():
            args.append(current.strip())
        return args

    def _extract_do_end_block(self, code_str: str, start_offset: int) -> tuple[str | None, int | None]:
        """Extract balanced %do; ... %end; block respecting nested %do / %end."""
        depth = 1
        for m in re.finditer(r'(%do\b|%end\b)', code_str[start_offset:], re.IGNORECASE):
            tok = m.group(1).lower()
            if tok == '%do':
                depth += 1
            elif tok == '%end':
                depth -= 1
                if depth == 0:
                    block = code_str[start_offset : start_offset + m.start()]
                    end_pos = start_offset + m.end()
                    if code_str[end_pos:end_pos+1] == ';':
                        end_pos += 1
                    return block, end_pos
        return None, None

    # ── HELPER: EVALUATE %IF/%ELSE ───────────────────────────────

    def _evaluate_if_else(self, code: str, local_vars: dict) -> str:
        """
        Evaluate SAS macro IF-THEN-ELSE structures:
        %if cond %then %do; ... %end;
        %else %if cond2 %then %do; ... %end;
        %else %do; ... %end;
        """
        pos = 0
        while pos < len(code):
            m_if = re.search(r'%if\s+(.*?)\s*%then\s*%do\s*;', code[pos:], re.IGNORECASE)
            if not m_if:
                break

            start_pos = pos + m_if.start()
            curr = pos + m_if.end()
            branches = []
            default_block = None

            # 1. First %if
            cond = m_if.group(1).strip()
            block, curr = self._extract_do_end_block(code, curr)
            if block is None:
                pos = pos + m_if.end()
                continue
            branches.append((cond, block))
            end_pos = curr

            # 2. Subsequent %else %if or %else
            while curr < len(code):
                m_else_if = re.match(r'\s*%else\s*%if\s+(.*?)\s*%then\s*%do\s*;', code[curr:], re.IGNORECASE)
                if m_else_if:
                    cond_e = m_else_if.group(1).strip()
                    curr += m_else_if.end()
                    block_e, curr = self._extract_do_end_block(code, curr)
                    if block_e is None:
                        break
                    branches.append((cond_e, block_e))
                    end_pos = curr
                    continue

                m_else = re.match(r'\s*%else\s*%do\s*;', code[curr:], re.IGNORECASE)
                if m_else:
                    curr += m_else.end()
                    block_e, curr = self._extract_do_end_block(code, curr)
                    if block_e is None:
                        break
                    default_block = block_e
                    end_pos = curr
                    break

                break

            # Evaluate branches
            selected = ""
            matched = False
            failed_eval = False
            for b_cond, b_block in branches:
                eval_res = self._evaluate_condition(b_cond, local_vars)
                if eval_res is None:
                    self.warnings.append(f"⚠️ Unable to evaluate macro %IF condition '{b_cond}' — safe reject.")
                    selected = re.sub(r'\bset\b', 'set_unresolved', b_block, flags=re.IGNORECASE)
                    matched = True
                    failed_eval = True
                    break
                elif eval_res is True:
                    selected = b_block
                    for lm in re.finditer(r'%let\s+(\w+)\s*=\s*(.*?)\s*;', selected, re.IGNORECASE):
                        let_name = lm.group(1).upper()
                        let_val_raw = lm.group(2).strip()
                        let_val_sub = self._substitute_let_vars(let_val_raw, self._get_active_vars(local_vars))
                        eval_val = self._evaluate_bounded_macro_functions(let_val_sub, self._get_active_vars(local_vars))
                        if eval_val is not None:
                            let_val_sub = eval_val
                        self._set_var_in_scope(let_name, let_val_sub)
                    selected = re.sub(r'%let\s+\w+\s*=\s*.*?;', '', selected, flags=re.IGNORECASE)
                    matched = True
                    break
            if not matched and not failed_eval and default_block is not None:
                selected = default_block
                for lm in re.finditer(r'%let\s+(\w+)\s*=\s*(.*?)\s*;', selected, re.IGNORECASE):
                    let_name = lm.group(1).upper()
                    let_val_raw = lm.group(2).strip()
                    let_val_sub = self._substitute_let_vars(let_val_raw, self._get_active_vars(local_vars))
                    eval_val = self._evaluate_bounded_macro_functions(let_val_sub, self._get_active_vars(local_vars))
                    if eval_val is not None:
                        let_val_sub = eval_val
                    self._set_var_in_scope(let_name, let_val_sub)
                selected = re.sub(r'%let\s+\w+\s*=\s*.*?;', '', selected, flags=re.IGNORECASE)

            code = code[:start_pos] + selected + code[end_pos:]
            pos = start_pos

        # Single statement form: %if cond %then statement;
        single_pattern = re.compile(
            r'%if\s+(.*?)\s*%then\s+([^;]+;)'
            r'(?:\s*%else\s+([^;]+;))?',
            re.IGNORECASE
        )

        def eval_single(match):
            condition  = match.group(1).strip()
            then_stmt  = match.group(2) or ""
            else_stmt  = match.group(3) or ""
            eval_res = self._evaluate_condition(condition, local_vars)
            if eval_res is None:
                self.warnings.append(f"⚠️ Unable to evaluate macro %IF condition '{condition}' — safe reject.")
                return re.sub(r'\bset\b', 'set_unresolved', then_stmt, flags=re.IGNORECASE)
            elif eval_res is True:
                return then_stmt
            else:
                return else_stmt

        code = single_pattern.sub(eval_single, code)
        return code

    # ── HELPER: EVALUATE CONDITION ───────────────────────────────

    def _evaluate_condition(self, condition: str, local_vars: dict) -> bool | None:
        """
        Evaluate a simple SAS macro condition safely.
        Returns True/False for valid simple conditions, or None for un-evaluable/unsupported conditions.
        """
        # Reject unsupported macro functions or indirect references
        if '&&' in condition:
            return None

        active_vars = {**self.let_vars, **local_vars}
        cond = self._substitute_let_vars(condition, active_vars)

        # Evaluate bounded macro functions (%length, %substr, %scan, %index, %sysfunc)
        eval_fn = self._evaluate_bounded_macro_functions(cond, active_vars)
        if eval_fn is not None:
            cond = eval_fn

        # Reject any remaining %macro_function calls except allowed builtins if simple
        macro_func_calls = re.findall(r'%(\w+)', cond)
        for m_fn in macro_func_calls:
            if m_fn.upper() not in ('SYMEXIST', 'UPCASE', 'LOWCASE'):
                return None

        # Reject if unresolved macro variables remain
        if re.search(r'&\w+', cond):
            return None

        # Handle %upcase / %lowcase
        cond = re.sub(r'%upcase\s*\(\s*(.*?)\s*\)', lambda m: m.group(1).upper(), cond, flags=re.IGNORECASE)
        cond = re.sub(r'%lowcase\s*\(\s*(.*?)\s*\)', lambda m: m.group(1).lower(), cond, flags=re.IGNORECASE)

        # Handle %symexist(var)
        cond = re.sub(
            r'%symexist\s*\(\s*(\w+)\s*\)',
            lambda m: '1' if m.group(1).upper() in {**self.let_vars, **local_vars} else '0',
            cond, flags=re.IGNORECASE
        )

        # Normalize operators
        cond = re.sub(r'\bne\b',  '!=', cond, flags=re.IGNORECASE)
        cond = re.sub(r'\bgt\b',  '>',  cond, flags=re.IGNORECASE)
        cond = re.sub(r'\blt\b',  '<',  cond, flags=re.IGNORECASE)
        cond = re.sub(r'\bge\b',  '>=', cond, flags=re.IGNORECASE)
        cond = re.sub(r'\ble\b',  '<=', cond, flags=re.IGNORECASE)
        cond = re.sub(r'\band\b', ' and ', cond, flags=re.IGNORECASE)
        cond = re.sub(r'\bor\b',  ' or ',  cond, flags=re.IGNORECASE)
        cond = re.sub(r'\bnot\b', ' not ', cond, flags=re.IGNORECASE)
        cond = re.sub(r'\^=',     '!=', cond)
        cond = re.sub(r'(?<![<>!=])=(?!=)', '==', cond)

        # Normalize single/double quotes around words so 'SAFFL' and SAFFL tokenize uniformly
        cond = re.sub(r"['\"]([A-Za-z_]\w*)['\"]", r"\1", cond)

        # Convert SAS bare word comparison to Python quoted string literals
        def quote_bare_word(m):
            word = m.group(1)
            if word.lower() in ('and', 'or', 'not', 'true', 'false'):
                return word
            try:
                float(word)
                return word
            except ValueError:
                return f"'{word}'"

        cond_py = re.sub(r'\b([A-Za-z_]\w*)\b', quote_bare_word, cond)

        try:
            result = eval(cond_py, {"__builtins__": {}})
            if isinstance(result, (bool, int, float, str)):
                return bool(result)
            return None
        except Exception:
            return None

    # ── HELPER: DYNAMIC MACRO NAME RESOLUTION ───────────────────

    def _try_resolve_dynamic_name(self, name: str) -> str | None:
        """
        Try to resolve dynamic macro names like &prefix._process.
        If the resolved name matches a known macro, return it.
        """
        substituted = self._substitute_let_vars(name, self.let_vars)
        if substituted != name and substituted.upper() in self.macro_library:
            return substituted.upper()
        return None

    # ── STEP 9: CLEANUP ──────────────────────────────────────────

    def _cleanup(self, code: str) -> str:
        """Remove residual macro artifacts."""
        # Remove leftover %let statements
        code = re.sub(r'%let\s+\w+\s*=\s*[^;]*;', '', code, flags=re.IGNORECASE)
        # Remove leftover %put statements
        code = re.sub(r'%put\s+[^;]*;', '', code, flags=re.IGNORECASE)
        if '&&' in code:
            self.warnings.append("⚠️ Indirect macro variable reference (&&) is unsupported — left unexpanded.")
        # Record warnings for unresolved macro variables
        unresolved = re.findall(r'&[A-Za-z_]\w*', code)
        if unresolved:
            for var in set(unresolved):
                self.warnings.append(f"⚠️ Unresolved macro variable {var} — left unexpanded.")
            code = re.sub(r'\bset\b', 'set_unresolved', code, flags=re.IGNORECASE)
        return code


# ─────────────────────────────────────────────────────────────────
# CONVENIENCE FUNCTION (used by app.py)
# ─────────────────────────────────────────────────────────────────

def expand_sas_macros(sas_code: str, extra_files: list[str] = None, expand_path_b: bool = True) -> tuple[str, list, list]:
    """
    Convenience wrapper around SASMacroProcessor.

    Returns:
        (expanded_code, warnings, sql_hints)
    """
    processor = SASMacroProcessor()
    return processor.process(sas_code, extra_files=extra_files, expand_path_b=expand_path_b)


def has_macros(sas_code: str) -> bool:
    """Quick check — does this SAS code contain any macro definitions or calls?"""
    return bool(re.search(r'%macro\s+\w+|%\w+\s*[\(;]', sas_code, re.IGNORECASE))
