"""
rule_engine.py
──────────────
Deterministic Rule-Based Conversion Engine for SAS Modernization Engine.
Translates standard SAS constructs (PROC SORT, PROC FREQ, PROC SQL, %LET, %DO loops, DATA steps)
to Base R or Modern R (tidyverse) deterministically with high confidence.
"""

from __future__ import annotations
import re
from typing import Optional, Tuple
from sas_ast import ProgramStep, MacroIR


class RuleEngine:
    """
    Deterministic rule translator for SAS statements.
    """

    def __init__(self, dialect: str = "Modern R (tidyverse)"):
        self.dialect = dialect.lower()
        self.is_tidyverse = "tidyverse" in self.dialect or "modern" in self.dialect

    def translate_step(self, step: ProgramStep) -> Tuple[Optional[str], float, str]:
        """
        Attempts to translate a ProgramStep using deterministic rules.
        Returns: (translated_r_code, confidence_score, rule_name)
        """
        code = step.source_code.strip()
        
        # 1. %LET Assignment Rule
        if code.lower().startswith("%let"):
            r_code = self._translate_let(code)
            if r_code: return r_code, 1.0, "Rule_LetAssignment"
            
        # 2. PROC SORT Rule
        if re.search(r"proc\s+sort", code, re.I):
            r_code = self._translate_proc_sort(code)
            if r_code: return r_code, 0.95, "Rule_ProcSort"
            
        # 3. PROC FREQ Rule
        if re.search(r"proc\s+freq", code, re.I):
            r_code = self._translate_proc_freq(code)
            if r_code: return r_code, 0.90, "Rule_ProcFreq"
            
        # 4. Standard DATA Step Filtering Rule
        if code.lower().startswith("data"):
            r_code = self._translate_data_step_filter(code)
            if r_code: return r_code, 0.85, "Rule_DataStepFilter"

        # 5. PROC SQL Rule (Aggregations, Group By, Having, Order By, Joins)
        if re.search(r"proc\s+sql", code, re.I):
            r_code = self._translate_proc_sql(code)
            if r_code: return r_code, 0.95, "Rule_ProcSQL"
            
        # No deterministic rule matched
        return None, 0.0, "NoRuleMatched"

    def translate_macro_loop(self, loop_dict: dict) -> Tuple[Optional[str], float]:
        """
        Translates %DO %TO, %DO %WHILE, and %DO %UNTIL macro loops to R loops.
        """
        ltype = loop_dict.get("type")
        if ltype == "DO_TO":
            var = loop_dict.get("var", "i").lower()
            start = loop_dict.get("start", "1")
            end = loop_dict.get("end", "10")
            return f"for ({var} in {start}:{end})", 0.95
        elif ltype == "DO_WHILE":
            cond = loop_dict.get("condition", "TRUE")
            return f"while ({cond})", 0.90
        elif ltype == "DO_UNTIL":
            cond = loop_dict.get("condition", "FALSE")
            return f"while (!({cond}))", 0.90
        return None, 0.0

    # ─────────────────────────────────────────────────────────────────
    # RULE IMPLEMENTATIONS
    # ─────────────────────────────────────────────────────────────────

    def _translate_let(self, code: str) -> Optional[str]:
        m = re.search(r"%let\s+(\w+)\s*=\s*(.*?);", code, re.I)
        if not m: return None
        var_name = m.group(1).lower()
        val = m.group(2).strip()
        # Clean quotes or numeric assignment
        if val.isdigit() or re.match(r'^-?\d+(\.\d+)?$', val):
            return f"{var_name} <- {val}"
        else:
            val_clean = val.strip('"\'')
            return f'{var_name} <- "{val_clean}"'

    def _translate_proc_sort(self, code: str) -> Optional[str]:
        in_m = re.search(r"data\s*=\s*([\w.]+)", code, re.I)
        out_m = re.search(r"out\s*=\s*([\w.]+)", code, re.I)
        by_m = re.search(r"by\s+([^;]+);", code, re.I)
        
        if not in_m or not by_m: return None
        
        in_ds = in_m.group(1).split('.')[-1].upper()
        out_ds = out_m.group(1).split('.')[-1].upper() if out_m else in_ds
        
        by_vars_raw = by_m.group(1).strip().split()
        
        # Check descending flags
        sort_terms = []
        is_desc = False
        for token in by_vars_raw:
            if token.upper() == "DESCENDING":
                is_desc = True
                continue
            v_name = token.strip()
            if self.is_tidyverse:
                sort_terms.append(f"desc({v_name})" if is_desc else v_name)
            else:
                sort_terms.append(f"-{out_ds}${v_name}" if is_desc else f"{out_ds}${v_name}")
            is_desc = False
            
        if self.is_tidyverse:
            cols_str = ", ".join(sort_terms)
            return f"{out_ds} <- {in_ds} %>%\n  arrange({cols_str})\n{out_ds}"
        else:
            cols_str = ", ".join(sort_terms)
            return f"{out_ds} <- {in_ds}[order({cols_str}), ]\n{out_ds}"

    def _translate_proc_freq(self, code: str) -> Optional[str]:
        in_m = re.search(r"data\s*=\s*([\w.]+)", code, re.I)
        tables_m = re.search(r"tables\s+([^;]+);", code, re.I)
        if not in_m or not tables_m: return None
        
        in_ds = in_m.group(1).split('.')[-1].upper()
        raw_tables = tables_m.group(1).strip()
        
        # Handle var1*var2
        vars_list = [v.strip() for v in raw_tables.replace('*', ' ').split()]
        
        if self.is_tidyverse:
            vars_str = ", ".join(vars_list)
            return f"df <- {in_ds} %>%\n  count({vars_str}) %>%\n  rename(COUNT = n)\ndf"
        else:
            vars_refs = ", ".join(f"{in_ds}${v}" for v in vars_list)
            vars_quoted = ", ".join(f"'{v}'" for v in vars_list)
            return (
                f"df <- as.data.frame(table({vars_refs}))\n"
                f"names(df) <- c({vars_quoted}, 'COUNT')\n"
                f"df <- df[df$COUNT > 0, ]\n"
                f"df"
            )

    def _translate_data_step_filter(self, code: str) -> Optional[str]:
        out_m = re.search(r"^\s*data\s+([\w.]+)", code, re.I | re.M)
        set_m = re.search(r"set\s+([\w.]+)", code, re.I)
        if not out_m or not set_m: return None
        
        out_ds = out_m.group(1).split('.')[-1].upper()
        in_ds = set_m.group(1).split('.')[-1].upper()
        
        # Simple IF condition like `if age >= 18;` or `where age >= 18;`
        filter_m = re.search(r"(?:if|where)\s+(.*?);", code, re.I)
        if not filter_m: return None
        
        sas_cond = filter_m.group(1).strip()
        r_cond = re.sub(r'(?<![<>!=])=(?!=)', '==', sas_cond)
        r_cond = re.sub(r'\band\b', '&&', r_cond, flags=re.I)
        r_cond = re.sub(r'\bor\b', '||', r_cond, flags=re.I)
        
        if self.is_tidyverse:
            return f"{out_ds} <- {in_ds} %>%\n  filter({r_cond})\n{out_ds}"
        else:
            return f"{out_ds} <- {in_ds}[{in_ds}${r_cond}, ]\n{out_ds}"

    def _translate_proc_sql(self, code: str) -> Optional[str]:
        if not re.search(r"proc\s+sql", code, re.I):
            return None

        # Clean code block
        code_clean = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
        code_clean = re.sub(r';\s*quit;', ';', code_clean, flags=re.I)

        # 1. Output dataset
        out_m = re.search(r"create\s+table\s+([\w.]+)\s+as", code_clean, re.I)
        out_ds = out_m.group(1).split('.')[-1].upper() if out_m else "RESULT"

        # 2. Input dataset
        from_m = re.search(r"\bfrom\s+([\w.]+)(?:\s+(\w+))?", code_clean, re.I)
        if not from_m:
            return None
        in_ds = from_m.group(1).split('.')[-1].upper()

        # Check for JOIN
        join_m = re.search(r"(left|right|inner|full)?\s*join\s+([\w.]+)(?:\s+(?:as\s+)?\w+)?\s+on\s+(.*?)(?=\bwhere\b|\bgroup\s+by\b|\bhaving\b|\border\s+by\b|;|\bquit\b)", code_clean, re.I | re.DOTALL)
        join_ds = None
        join_type = "left_join"
        join_on = None
        if join_m:
            jtype = (join_m.group(1) or "left").lower()
            join_type = f"{jtype}_join"
            join_ds = join_m.group(2).split('.')[-1].upper()
            join_on_raw = join_m.group(3).strip()
            on_match = re.search(r"(?:\w+\.)?(\w+)\s*=\s*(?:\w+\.)?(\w+)", join_on_raw, re.I)
            if on_match:
                join_on = f'"{on_match.group(1).lower()}"'

        # 3. SELECT clause items & Alias Mapping
        select_m = re.search(r"\bselect\s+(.*?)\s+\bfrom\b", code_clean, re.I | re.DOTALL)
        if not select_m:
            return None
        select_str = select_m.group(1).strip()

        # Parse select items & build alias_map (e.g. "sum(amount)" -> "total_spent")
        summarise_items = []
        alias_map = {}  # { "sum(amount)": "total_spent", ... }
        select_parts = [p.strip() for p in select_str.split(',') if p.strip()]

        for item in select_parts:
            if item == '*' or item.lower().endswith('.*'):
                continue

            alias = None
            alias_m = re.search(r'^(.*?)\s+as\s+(\w+)$', item, re.I) or re.search(r'^(.*?)\s+(\w+)$', item, re.I)
            if alias_m:
                expr_candidate = alias_m.group(1).strip()
                alias_candidate = alias_m.group(2).strip()
                if alias_candidate.lower() not in ("from", "where", "group", "by", "having", "order", "as"):
                    expr = expr_candidate
                    alias = alias_candidate
                else:
                    expr = item
            else:
                expr = item

            expr_clean = re.sub(r'\s+', '', expr.lower())

            # Check aggregate functions
            if re.search(r'count\s*\(\s*\*\s*\)', expr, re.I):
                a_name = alias or "total_orders"
                summarise_items.append(f"{a_name} = n()")
                alias_map["count(*)"] = a_name
                alias_map[expr_clean] = a_name
            elif re.search(r'count\s*\(\s*(\w+)\s*\)', expr, re.I):
                c_var = re.search(r'count\s*\(\s*(\w+)\s*\)', expr, re.I).group(1)
                a_name = alias or f"count_{c_var}"
                summarise_items.append(f"{a_name} = sum(!is.na({c_var}))")
                alias_map[f"count({c_var.lower()})"] = a_name
                alias_map[expr_clean] = a_name
            elif re.search(r'sum\s*\(\s*([\w.]+)\s*\)', expr, re.I):
                s_var = re.search(r'sum\s*\(\s*([\w.]+)\s*\)', expr, re.I).group(1).split('.')[-1]
                a_name = alias or f"total_{s_var}"
                summarise_items.append(f"{a_name} = sum({s_var}, na.rm = TRUE)")
                alias_map[f"sum({s_var.lower()})"] = a_name
                alias_map[expr_clean] = a_name
            elif re.search(r'(?:avg|mean)\s*\(\s*([\w.]+)\s*\)', expr, re.I):
                m_var = re.search(r'(?:avg|mean)\s*\(\s*([\w.]+)\s*\)', expr, re.I).group(1).split('.')[-1]
                a_name = alias or f"avg_{m_var}"
                summarise_items.append(f"{a_name} = mean({m_var}, na.rm = TRUE)")
                alias_map[f"avg({m_var.lower()})"] = a_name
                alias_map[f"mean({m_var.lower()})"] = a_name
                alias_map[expr_clean] = a_name
            elif re.search(r'max\s*\(\s*([\w.]+)\s*\)', expr, re.I):
                mx_var = re.search(r'max\s*\(\s*([\w.]+)\s*\)', expr, re.I).group(1).split('.')[-1]
                a_name = alias or f"max_{mx_var}"
                summarise_items.append(f"{a_name} = max({mx_var}, na.rm = TRUE)")
                alias_map[f"max({mx_var.lower()})"] = a_name
                alias_map[expr_clean] = a_name
            elif re.search(r'min\s*\(\s*([\w.]+)\s*\)', expr, re.I):
                mn_var = re.search(r'min\s*\(\s*([\w.]+)\s*\)', expr, re.I).group(1).split('.')[-1]
                a_name = alias or f"min_{mn_var}"
                summarise_items.append(f"{a_name} = min({mn_var}, na.rm = TRUE)")
                alias_map[f"min({mn_var.lower()})"] = a_name
                alias_map[expr_clean] = a_name

        # 4. WHERE clause
        where_m = re.search(r"\bwhere\s+(.*?)(?=\bgroup\s+by\b|\bhaving\b|\border\s+by\b|;|\bquit\b)", code_clean, re.I | re.DOTALL)
        where_cond = None
        if where_m:
            w_raw = where_m.group(1).strip()
            w_raw = re.sub(r'^\w+\.', '', w_raw)
            w_raw = re.sub(r'(?<![<>!=])=(?!=)', '==', w_raw)
            where_cond = w_raw.strip()

        # 5. GROUP BY clause
        group_m = re.search(r"\bgroup\s+by\s+(.*?)(?=\bhaving\b|\border\s+by\b|;|\bquit\b)", code_clean, re.I | re.DOTALL)
        group_vars = []
        if group_m:
            g_raw = group_m.group(1).strip()
            group_vars = [re.sub(r'^\w+\.', '', v.strip()) for v in g_raw.split(',') if v.strip()]

        # 6. HAVING clause with Aggregate Alias Resolution
        having_m = re.search(r"\bhaving\s+(.*?)(?=\border\s+by\b|;|\bquit\b)", code_clean, re.I | re.DOTALL)
        having_cond = None
        if having_m:
            h_raw = having_m.group(1).strip()
            h_raw = re.sub(r'\bcalculated\s+', '', h_raw, flags=re.I)
            h_raw = re.sub(r'^\w+\.', '', h_raw)
            
            # Resolve aggregate expressions in HAVING to their SELECT aliases
            for agg_expr, a_name in alias_map.items():
                pattern = re.escape(agg_expr).replace(r'\ ', r'\s*')
                h_raw = re.sub(pattern, a_name, h_raw, flags=re.I)
                # Also handle with spaces e.g. sum( amount )
                no_space_agg = agg_expr.replace(' ', '')
                if '(' in no_space_agg:
                    func_name, var_part = no_space_agg.split('(', 1)
                    pattern_spaced = rf'\b{func_name}\s*\(\s*{re.escape(var_part.rstrip(")"))}\s*\)'
                    h_raw = re.sub(pattern_spaced, a_name, h_raw, flags=re.I)

            h_raw = re.sub(r'(?<![<>!=])=(?!=)', '==', h_raw)
            having_cond = h_raw.strip()

        # 7. ORDER BY clause with Aggregate Alias Resolution
        order_m = re.search(r"\border\s+by\s+(.*?)(?:;|\bquit\b)", code_clean, re.I | re.DOTALL)
        order_terms = []
        if order_m:
            o_raw = order_m.group(1).strip()
            o_raw = re.sub(r'\bcalculated\s+', '', o_raw, flags=re.I)
            for item in o_raw.split(','):
                item = item.strip()
                if not item: continue
                is_desc = bool(re.search(r'\bdesc\b', item, re.I))
                clean_var = re.sub(r'\bdesc\b', '', item, flags=re.I).strip()
                clean_var = re.sub(r'^\w+\.', '', clean_var)

                # Resolve aggregate expression in ORDER BY if needed
                clean_var_no_space = clean_var.lower().replace(' ', '')
                if clean_var_no_space in alias_map:
                    clean_var = alias_map[clean_var_no_space]

                if is_desc:
                    order_terms.append(f"desc({clean_var})")
                else:
                    order_terms.append(clean_var)

        lines = [f"{out_ds} <- {in_ds}"]

        if join_ds:
            if join_on:
                lines.append(f"  dplyr::{join_type}({join_ds}, by = {join_on})")
            else:
                lines.append(f"  dplyr::{join_type}({join_ds})")

        if where_cond:
            lines.append(f"  dplyr::filter({where_cond})")

        if group_vars:
            g_str = ", ".join(group_vars)
            lines.append(f"  dplyr::group_by({g_str})")

        if summarise_items:
            s_str = ",\n    ".join(summarise_items)
            lines.append(f"  dplyr::summarise(\n    {s_str},\n    .groups = \"drop\"\n  )")

        if having_cond:
            lines.append(f"  dplyr::filter({having_cond})")

        if order_terms:
            o_str = ", ".join(order_terms)
            lines.append(f"  dplyr::arrange({o_str})")

        if len(lines) == 1:
            return None

        pipeline = " %>%\n".join(lines)
        return f"{pipeline}\n{out_ds}"
