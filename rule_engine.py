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

        # 1b. Standalone Macro Call Rule (%macro_name(...))
        if step.step_type == "MACRO_CALL" or (code.startswith("%") and re.match(r"%([a-zA-Z_]\w*)\s*\(", code)):
            r_code = self._translate_macro_call(code)
            if r_code: return r_code, 0.95, "Rule_MacroCall"
            
        # 2. PROC SORT Rule
        if re.search(r"proc\s+sort", code, re.I):
            r_code = self._translate_proc_sort(code)
            if r_code: return r_code, 0.95, "Rule_ProcSort"
            
        # 3. PROC FREQ Rule
        if re.search(r"proc\s+freq", code, re.I):
            r_code = self._translate_proc_freq(code)
            if r_code: return r_code, 0.90, "Rule_ProcFreq"
            
        # 4. DATALINES / CARDS Inline Data Rule
        if re.search(r"datalines|cards", code, re.I):
            r_code = self._translate_datalines(code)
            if r_code: return r_code, 1.0, "Rule_DatalinesToDataFrame"

        # 5. DATA STEP DO LOOP (bounded simple subset)
        if re.search(r"\bdo\s+\w+\s*=\s*\d+\s+to\s+\d+", code, re.I):
            r_code = self._translate_data_step_do_loop(code)
            if r_code:
                return r_code, 0.85, "Rule_DataStepDoLoop"
        # 6. Standard DATA Step Filtering & Merge Rules
        if code.lower().startswith("data"):
            if re.search(r"\bmerge\b", code, re.I):
                r_code = self._translate_data_step_merge(code)
                if r_code: return r_code, 0.90, "Rule_DataStepMerge"
            if re.search(r"\bby\s+", code, re.I) or re.search(r"\b(first|last)\.", code, re.I):
                r_code = self._translate_data_step_by_group(code)
                if r_code:
                    return r_code, 0.90, "Rule_DataStepByGroup"
                else:
                    return None, 0.0, "NoRuleMatched"
            if re.search(r"\bretain\b", code, re.I):
                r_code = self._translate_data_step_retain(code)
                if r_code:
                    return r_code, 0.90, "Rule_DataStepRetain"
                else:
                    return None, 0.0, "NoRuleMatched"
            if re.search(r"\b(lag\d*|dif\d*)\s*\(", code, re.I):
                r_code = self._translate_data_step_lag(code)
                if r_code:
                    return r_code, 0.90, "Rule_DataStepLag"
                else:
                    return None, 0.0, "NoRuleMatched"
            if re.search(r"\bselect\b", code, re.I):
                r_code = self._translate_data_step_select_when(code)
                if r_code:
                    return r_code, 0.90, "Rule_DataStepSelectWhen"
                else:
                    return None, 0.0, "NoRuleMatched"
            if re.search(r"\bif\s+(.*?)\s+then\s+delete\s*;", code, re.I):
                r_code = self._translate_data_step_delete(code)
                if r_code:
                    return r_code, 0.90, "Rule_DataStepDelete"
                else:
                    return None, 0.0, "NoRuleMatched"
            if re.search(r"\b(drop|keep|rename)\b", code, re.I):
                r_code = self._translate_data_step_schema_rename(code)
                if r_code:
                    return r_code, 0.90, "Rule_DataStepSchemaRename"
                else:
                    return None, 0.0, "NoRuleMatched"
            r_code = self._translate_data_step_filter(code)
            if r_code: return r_code, 0.85, "Rule_DataStepFilter"

        # 6. PROC SQL Rule (Aggregations, Group By, Having, Order By, Joins)
        if re.search(r"proc\s+sql", code, re.I):
            r_code = self._translate_proc_sql(code)
            if r_code: return r_code, 0.95, "Rule_ProcSQL"
            
        # No deterministic rule matched
        return None, 0.0, "NoRuleMatched"

    @staticmethod
    def _normalize_sas_date_literals(expr: str) -> str:
        """
        Normalizes valid SAS date literals 'DDMMMYYYY'd or "DDMMMYYYY"d into R as.Date("YYYY-MM-DD").
        Rejects malformed dates (e.g., '99JAN2024'd, '01XYZ2024'd, invalid leap years) by keeping them unchanged.
        """
        import datetime

        month_map = {
            "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
            "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12
        }

        def _replace_date(m):
            day_str, mon_str, year_str = m.group(1), m.group(2).upper(), m.group(3)
            if mon_str not in month_map:
                return m.group(0)
            try:
                day = int(day_str)
                year = int(year_str)
                mon = month_map[mon_str]
                dt = datetime.date(year, mon, day)
                return f'as.Date("{dt.strftime("%Y-%m-%d")}")'
            except ValueError:
                return m.group(0)

        pattern = r"""['"](\d{1,2})([A-Za-z]{3})(\d{4})['"]d\b"""
        return re.sub(pattern, _replace_date, expr, flags=re.I)

    @staticmethod
    def _normalize_sas_char_missing(expr: str) -> str:
        """
        Translates SAS empty character string comparison operators into R equivalents that handle both NA and empty string.
        - var ne '' or var NE '' or var != '' or var != "" or var ^= '' -> !is.na(var) & var != ""
        - var eq '' or var EQ '' or var = '' or var == '' or var == "" -> is.na(var) | var == ""
        """
        # 1. Handle NE / ne / != / ^= with empty string
        expr = re.sub(
            r'\b([a-zA-Z_]\w*)\s+(?:ne|NE|!=|\^=)\s*[\'"][\'"]',
            r'!is.na(\1) & \1 != ""',
            expr
        )
        # 2. Handle EQ / eq / = / == with empty string
        expr = re.sub(
            r'\b([a-zA-Z_]\w*)\s+(?:eq|EQ|==|=)\s*[\'"][\'"]',
            r'is.na(\1) | \1 == ""',
            expr
        )
        return expr

    @staticmethod
    def _normalize_sas_elementwise_functions(expr: str) -> str:
        """
        Normalizes 6 bounded SAS elementwise functions into exact R equivalents:
        1. abs(A) -> abs(A)
        2. missing(A) -> is.na(A)
        3. coalesce(A, B) -> dplyr::coalesce(A, B)
        4. round(A) -> round(A), round(A, 0.1) -> round(A, 1)
        5. sum(A, B) -> ifelse(is.na(A) & is.na(B), NA_real_, dplyr::coalesce(A, 0) + dplyr::coalesce(B, 0))
        6. mean(A, B) -> ifelse(is.na(A) & is.na(B), NA_real_, (dplyr::coalesce(A, 0) + dplyr::coalesce(B, 0)) / (!is.na(A) + !is.na(B)))
        """
        # 1. missing(var) -> is.na(var)
        expr = re.sub(r'\bmissing\s*\(\s*(\w+)\s*\)', r'is.na(\1)', expr, flags=re.I)
        
        # 2. coalesce(var1, var2) -> dplyr::coalesce(var1, var2)
        expr = re.sub(r'\bcoalesce\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)', r'dplyr::coalesce(\1, \2)', expr, flags=re.I)

        # 3. sum(var1, var2)
        expr = re.sub(
            r'\bsum\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)',
            r'ifelse(is.na(\1) & is.na(\2), NA_real_, dplyr::coalesce(\1, 0) + dplyr::coalesce(\2, 0))',
            expr, flags=re.I
        )

        # 4. mean(var1, var2)
        expr = re.sub(
            r'\bmean\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)',
            r'ifelse(is.na(\1) & is.na(\2), NA_real_, (dplyr::coalesce(\1, 0) + dplyr::coalesce(\2, 0)) / (!is.na(\1) + !is.na(\2)))',
            expr, flags=re.I
        )

        # 5. round(var, step) -> round(var, digits) if step is e.g. 0.1 -> 1, 0.01 -> 2
        def _replace_round(m):
            v = m.group(1)
            step_str = m.group(2) if m.group(2) else None
            if not step_str:
                return f"round({v})"
            try:
                step_flt = float(step_str)
                if step_flt == 0.1: digits = 1
                elif step_flt == 0.01: digits = 2
                elif step_flt == 0.001: digits = 3
                elif step_flt.is_integer(): digits = int(step_flt)
                else: return m.group(0)
                return f"round({v}, {digits})"
            except ValueError:
                return m.group(0)

        expr = re.sub(r'\bround\s*\(\s*(\w+)(?:\s*,\s*([\d.]+))?\s*\)', _replace_round, expr, flags=re.I)

        return expr

    @staticmethod
    def _normalize_sas_condition(expr: str) -> str:
        """
        Normalizes a SAS condition expression into valid R syntax by applying in order:
        1. SAS date literal normalization ('DDMMMYYYY'd -> as.Date("YYYY-MM-DD"))
        2. SAS character missing/empty string normalization (ne '' -> !is.na(x) & x != "")
        3. SAS comparison & logical operator normalization (ne, ^=, eq, gt, ge, lt, le, =, and, or)
        preserving quoted string contents intact.
        """
        expr = RuleEngine._normalize_sas_date_literals(expr)
        expr = RuleEngine._normalize_sas_char_missing(expr)

        # Handle SAS missing() function
        expr = re.sub(r'\bnot\s+missing\s*\(\s*([a-zA-Z_]\w*)\s*\)', r'!is.na(\1)', expr, flags=re.I)
        expr = re.sub(r'\bmissing\s*\(\s*([a-zA-Z_]\w*)\s*\)', r'is.na(\1)', expr, flags=re.I)

        # Handle numeric missing . comparison
        expr = re.sub(r'\b([a-zA-Z_]\w*)\s+(?:ne|NE|!=|\^=)\s*\.', r'!is.na(\1)', expr)
        expr = re.sub(r'\b([a-zA-Z_]\w*)\s+(?:eq|EQ|==|=)\s*\.', r'is.na(\1)', expr)

        pattern = r"('(?:''|[^'])*'|\"(?:\"\"|[^\"])*\")|(\^=|!=|>=|<=|==|\b(?:ne|eq|gt|ge|lt|le|and|or)\b)|(?<![<>!=^])=(?!=)"

        def replacer(match):
            quoted = match.group(1)
            if quoted:
                return quoted
            op_group = match.group(2)
            if op_group:
                op = op_group.lower()
                if op in ('ne', '^='):
                    return '!='
                elif op in ('eq', '=='):
                    return '=='
                elif op == 'gt':
                    return '>'
                elif op == 'ge':
                    return '>='
                elif op == 'lt':
                    return '<'
                elif op == 'le':
                    return '<='
                elif op == 'and':
                    return '&'
                elif op == 'or':
                    return '|'
                return match.group(2)
            return '=='

        return re.sub(pattern, replacer, expr, flags=re.I)

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

    def _translate_datalines(self, code: str) -> Optional[str]:
        """Translates DATA step with DATALINES or CARDS into a deterministic R data.frame(...) creation."""
        if not re.search(r"datalines|cards", code, re.I):
            return None

        out_m = re.search(r"^\s*data\s+([\w.]+)", code, re.I | re.M)
        input_m = re.search(r"input\s+([^;]+);", code, re.I)
        lines_m = re.search(r"(?:datalines|cards)\s*;\s*\n(.*?)\n\s*;", code, re.DOTALL | re.I)

        if not out_m or not input_m or not lines_m:
            return None

        out_ds = out_m.group(1).split('.')[-1].upper()

        # Parse INPUT column names and data types ($ indicates character column)
        raw_input_tokens = input_m.group(1).strip().split()
        cols = []
        col_types = []  # "char" or "num"

        for token in raw_input_tokens:
            if token == "$":
                if col_types:
                    col_types[-1] = "char"
            elif not token.startswith(":") and not token.startswith("$"):
                cols.append(token.lstrip("$"))
                col_types.append("num")

        if not cols:
            return None

        # Parse inline data rows
        raw_rows = [l.strip() for l in lines_m.group(1).split('\n') if l.strip()]
        col_data = {c: [] for c in cols}

        for row in raw_rows:
            if row.startswith(";") or row.lower() == "run;":
                continue
            tokens = row.split()
            for idx, col in enumerate(cols):
                if idx < len(tokens):
                    val = tokens[idx]
                    if col_types[idx] == "char":
                        clean_val = val.strip('"\'')
                        col_data[col].append(f'"{clean_val}"')
                    else:
                        if val == "." or val.upper() == "NA":
                            col_data[col].append("NA")
                        else:
                            col_data[col].append(val)

        if not any(col_data.values()):
            return None

        # Construct R data.frame(...)
        col_assigns = []
        for c in cols:
            vals_str = ", ".join(col_data[c])
            col_assigns.append(f"{c} = c({vals_str})")

        r_code = (
            f"{out_ds} <- data.frame(\n  " +
            ",\n  ".join(col_assigns) +
            ",\n  stringsAsFactors = FALSE\n)\n" +
            f"{out_ds}"
        )
        return r_code

    def _translate_data_step_merge(self, code: str) -> Optional[str]:
        """
        Translates a bounded 2-dataset DATA step MERGE with BY clause and optional IN= flags
        into a deterministic dplyr join (inner_join, left_join, right_join, full_join).
        """
        out_m = re.search(r"^\s*data\s+([\w.]+)", code, re.I | re.M)
        merge_m = re.search(r"\bmerge\s+([^;]+);", code, re.I)
        by_m = re.search(r"\bby\s+([^;]+);", code, re.I)

        if not out_m or not merge_m or not by_m:
            return None

        out_ds = out_m.group(1).split('.')[-1].upper()
        merge_clause = merge_m.group(1).strip()

        # Extract dataset items: e.g. DM(in=a) or SDTM.DM(in=a) or AE
        ds_matches = re.findall(r"([\w.]+)(?:\s*\(\s*in\s*=\s*(\w+)\s*\))?", merge_clause, re.I)
        if len(ds_matches) != 2:
            return None

        ds1_raw, flag1 = ds_matches[0]
        ds2_raw, flag2 = ds_matches[1]

        ds1 = ds1_raw.split('.')[-1].upper()
        ds2 = ds2_raw.split('.')[-1].upper()
        flag1 = flag1.lower() if flag1 else None
        flag2 = flag2.lower() if flag2 else None

        # BY variable check
        by_vars = by_m.group(1).strip().split()
        if len(by_vars) != 1:
            return None
        by_key = by_vars[0].strip()

        # Unhandled complex statement check
        for unhandled in ["output", "do", "retain", "delete", "stop", "abort", "sum", "mean", "coalesce", "missing", "abs", "round"]:
            if re.search(rf"\b{unhandled}\b", code, re.I):
                return None
        if re.search(r"\b(lag\d*|dif\d*)\b", code, re.I):
            return None

        # IF statement parsing
        if_m = re.search(r"\bif\s+([^;]+);", code, re.I)
        if if_m:
            if_stmt = if_m.group(1).strip().lower()
            if flag1 and flag2 and if_stmt in (f"{flag1} and {flag2}", f"{flag2} and {flag1}", f"{flag1} & {flag2}", f"{flag2} & {flag1}"):
                join_type = "inner_join"
            elif flag1 and if_stmt in (flag1, f"{flag1} and not {flag2}", f"{flag1} & !{flag2}"):
                join_type = "left_join"
            elif flag2 and if_stmt in (flag2, f"{flag2} and not {flag1}", f"{flag2} & !{flag1}"):
                join_type = "right_join"
            else:
                return None
        else:
            join_type = "full_join"

        if self.is_tidyverse:
            return (
                f"{out_ds} <- {ds1} %>%\n"
                f"  dplyr::{join_type}(\n"
                f"    {ds2},\n"
                f'    by = "{by_key}"\n'
                f"  )\n"
                f"{out_ds}"
            )
        else:
            all_opt = "TRUE" if join_type in ("full_join", "right_join") else "FALSE"
            all_x_opt = "TRUE" if join_type in ("full_join", "left_join") else "FALSE"
            return f"{out_ds} <- merge({ds1}, {ds2}, by = '{by_key}', all.x = {all_x_opt}, all.y = {all_opt})\n{out_ds}"

    def _translate_data_step_by_group(self, code: str) -> Optional[str]:
        """Translate a DATA step with single-level BY-group / FIRST. / LAST. processing.
        Supported patterns:
        - BY <var>; IF FIRST.<var>;
        - BY <var>; IF LAST.<var>;
        - BY <var>; IF FIRST.<var> THEN <flag>='Y'; [ELSE <flag>='N';]
        - BY <var>; IF LAST.<var> THEN <flag>='Y'; [ELSE <flag>='N';]
        - Combined FIRST + LAST assignments in same step.
        Returns R code string or None for unsupported patterns.
        """
        # Reject unsupported features immediately
        unsupported = [
            r"\bmerge\b", r"\bretain\b", r"\blag\b", r"\bdatalines\b", r"\bcards\b",
            r"\bproc\b", r"\bdo\b", r"\barray\b", r"\boutput\b", r"\bmodify\b",
            r"\bupdate\b", r"\bpoint\s*=", r"\bkey\s*=", r"\bnotsorted\b", r"\bdescending\b"
        ]
        for pat in unsupported:
            if re.search(pat, code, re.I):
                return None

        # Parse output and input dataset
        out_m = re.search(r"^\s*data\s+([\w.]+)", code, re.I | re.M)
        set_m = re.search(r"^\s*set\s+([\w.]+)", code, re.I | re.M)
        if not out_m or not set_m:
            return None

        out_ds = out_m.group(1).split('.')[-1].upper()
        in_ds = set_m.group(1).split('.')[-1].upper()

        # Parse BY statement
        by_m = re.search(r"^\s*by\s+([^;]+);", code, re.I | re.M)
        if not by_m:
            return None

        # Reject NOTSORTED or DESCENDING
        if re.search(r"\b(notsorted|descending)\b", code, re.I):
            return None

        by_str = by_m.group(1).strip()
        by_vars = [v.upper() for v in by_str.split()]
        if not by_vars:
            return None

        by_var_str = ", ".join(by_vars)
        by_vars_pat = "|".join(by_vars)

        # Split code into clean statement lines
        lines_raw = [l.strip() for l in code.split(";") if l.strip()]
        stmts = [
            l for l in lines_raw
            if not l.lower().startswith(("data ", "data\t", "set ", "set\t", "by ", "by\t", "run"))
        ]

        # Classify statements into supported FIRST/LAST patterns
        first_filt_var = None
        last_filt_var = None
        first_assigns = []  # list of (var_name, true_val, false_val, target_by_var)
        last_assigns = []   # list of (var_name, true_val, false_val, target_by_var)

        idx = 0
        while idx < len(stmts):
            stmt = stmts[idx]

            # 1. FIRST Filter: if first.<by_var>; or where first.<by_var>;
            m_ff = re.match(rf"^(?:if|where)\s+first\.(\w+)$", stmt, re.I)
            if m_ff:
                v = m_ff.group(1).upper()
                if v not in by_vars:
                    return None
                first_filt_var = v
                idx += 1
                continue

            # 2. LAST Filter: if last.<by_var>; or where last.<by_var>;
            m_lf = re.match(rf"^(?:if|where)\s+last\.(\w+)$", stmt, re.I)
            if m_lf:
                v = m_lf.group(1).upper()
                if v not in by_vars:
                    return None
                last_filt_var = v
                idx += 1
                continue

            # 3. FIRST Assignment: if first.<by_var> then <var>='Y'; [else <var>='N';]
            m_fa = re.match(
                rf"^if\s+first\.(\w+)\s+then\s+(\w+)\s*=\s*(['\"][^'\"]+['\"]|\w+)"
                rf"(?:\s*else\s+\2\s*=\s*(['\"][^'\"]+['\"]|\w+))?$",
                stmt, re.I
            )
            if m_fa:
                by_target = m_fa.group(1).upper()
                if by_target not in by_vars:
                    return None
                v_name = m_fa.group(2).upper()
                t_val = m_fa.group(3)
                f_val = m_fa.group(4) if m_fa.group(4) else "'N'"
                if not m_fa.group(4) and idx + 1 < len(stmts):
                    m_else_next = re.match(rf"^else\s+{v_name}\s*=\s*(['\"][^'\"]+['\"]|\w+)$", stmts[idx + 1], re.I)
                    if m_else_next:
                        f_val = m_else_next.group(1)
                        idx += 1
                first_assigns.append((v_name, t_val, f_val, by_target))
                idx += 1
                continue

            # 4. LAST Assignment: if last.<by_var> then <var>='Y'; [else <var>='N';]
            m_la = re.match(
                rf"^if\s+last\.(\w+)\s+then\s+(\w+)\s*=\s*(['\"][^'\"]+['\"]|\w+)"
                rf"(?:\s*else\s+\2\s*=\s*(['\"][^'\"]+['\"]|\w+))?$",
                stmt, re.I
            )
            if m_la:
                by_target = m_la.group(1).upper()
                if by_target not in by_vars:
                    return None
                v_name = m_la.group(2).upper()
                t_val = m_la.group(3)
                f_val = m_la.group(4) if m_la.group(4) else "'N'"
                if not m_la.group(4) and idx + 1 < len(stmts):
                    m_else_next = re.match(rf"^else\s+{v_name}\s*=\s*(['\"][^'\"]+['\"]|\w+)$", stmts[idx + 1], re.I)
                    if m_else_next:
                        f_val = m_else_next.group(1)
                        idx += 1
                last_assigns.append((v_name, t_val, f_val, by_target))
                idx += 1
                continue

            # Unrecognized statement in BY-group DATA step -> SAFE REJECT
            return None

        # Check for invalid combinations
        if not (first_filt_var or last_filt_var or first_assigns or last_assigns):
            return None
        if (first_filt_var or last_filt_var) and (first_assigns or last_assigns):
            return None
        if first_filt_var and last_filt_var:
            return None

        def _grp_vars_str(target_var):
            target_idx = by_vars.index(target_var)
            return ", ".join(by_vars[:target_idx + 1])

        # Emit R code according to matched pattern
        if first_filt_var:
            grp_str = _grp_vars_str(first_filt_var)
            return (
                f"{out_ds} <- {in_ds} %>%\n"
                f"  dplyr::arrange({by_var_str}) %>%\n"
                f"  dplyr::group_by({grp_str}) %>%\n"
                f"  dplyr::slice_head(n = 1) %>%\n"
                f"  dplyr::ungroup()\n"
                f"{out_ds}"
            )
        elif last_filt_var:
            grp_str = _grp_vars_str(last_filt_var)
            return (
                f"{out_ds} <- {in_ds} %>%\n"
                f"  dplyr::arrange({by_var_str}) %>%\n"
                f"  dplyr::group_by({grp_str}) %>%\n"
                f"  dplyr::slice_tail(n = 1) %>%\n"
                f"  dplyr::ungroup()\n"
                f"{out_ds}"
            )
        elif first_assigns or last_assigns:
            pipe_parts = [f"{out_ds} <- {in_ds}", f"  dplyr::arrange({by_var_str})"]

            all_assigns = []
            for fa in first_assigns:
                all_assigns.append((fa[0], fa[1], fa[2], fa[3], "first"))
            for la in last_assigns:
                all_assigns.append((la[0], la[1], la[2], la[3], "last"))

            current_grp = None
            mut_lines = []

            for v_name, t_val, f_val, by_target, mode in all_assigns:
                g_str = _grp_vars_str(by_target)
                if current_grp != g_str:
                    if mut_lines:
                        mut_str = ",\n".join(mut_lines)
                        pipe_parts.append(f"  dplyr::mutate(\n{mut_str}\n  )")
                        mut_lines = []
                    pipe_parts.append(f"  dplyr::group_by({g_str})")
                    current_grp = g_str

                cond_expr = "row_number() == 1" if mode == "first" else "row_number() == n()"
                mut_lines.append(f"    {v_name} = ifelse({cond_expr}, {t_val}, {f_val})")

            if mut_lines:
                mut_str = ",\n".join(mut_lines)
                pipe_parts.append(f"  dplyr::mutate(\n{mut_str}\n  )")

            pipe_parts.append("  dplyr::ungroup()")
            return " %>%\n".join(pipe_parts) + f"\n{out_ds}"

        return None

        return None

    def _translate_data_step_retain(self, code: str) -> Optional[str]:
        """Translate a DATA step with simple bounded RETAIN processing.
        Supported patterns:
        - Pattern A: retain <var> 0; <var> = <var> + 1; (Cumulative row counter)
        - Pattern B: retain <var> <init_val>; (Static initialization)
        - Pattern C: retain <var>; if <src> ne . then <var> = <src>; (LOCF carry forward)
        Returns R code string or None for unsupported patterns.
        """
        # Reject unsupported features immediately
        unsupported = [
            r"\bmerge\b", r"\bby\b", r"\bfirst\.", r"\blast\.", r"\blag\b",
            r"\bdatalines\b", r"\bcards\b", r"\bproc\b", r"\bdo\b", r"\barray\b",
            r"\boutput\b", r"\bmodify\b", r"\bupdate\b", r"\bpoint\s*=", r"\bkey\s*="
        ]
        for pat in unsupported:
            if re.search(pat, code, re.I):
                return None

        out_m = re.search(r"^\s*data\s+([\w.]+)", code, re.I | re.M)
        set_m = re.search(r"^\s*set\s+([\w.]+)", code, re.I | re.M)
        if not out_m or not set_m:
            return None

        out_ds = out_m.group(1).split('.')[-1].upper()
        in_ds = set_m.group(1).split('.')[-1].upper()

        lines_raw = [l.strip() for l in code.split(";") if l.strip()]
        stmts = [
            l for l in lines_raw
            if not l.lower().startswith(("data ", "data\t", "set ", "set\t", "run"))
        ]

        if not stmts:
            return None

        # Parse RETAIN statement
        retain_stmt = stmts[0]
        m_ret = re.match(r"^retain\s+(\w+)(?:\s+(.+))?$", retain_stmt, re.I)
        if not m_ret:
            return None

        ret_var = m_ret.group(1).upper()
        init_val = m_ret.group(2).strip() if m_ret.group(2) else None

        remaining_stmts = stmts[1:]

        # Pattern B: Only RETAIN statement with initial value, no further statements
        if not remaining_stmts and init_val is not None:
            return (
                f"{out_ds} <- {in_ds} %>%\n"
                f"  dplyr::mutate(\n"
                f"    {ret_var} = {init_val}\n"
                f"  )\n"
                f"{out_ds}"
            )

        # Pattern A: Cumulative counter: <var> = <var> + 1;
        if len(remaining_stmts) == 1:
            m_cnt = re.match(rf"^{ret_var}\s*=\s*{ret_var}\s*\+\s*1$", remaining_stmts[0], re.I)
            if m_cnt and (init_val is None or init_val in ("0", "1")):
                return (
                    f"{out_ds} <- {in_ds} %>%\n"
                    f"  dplyr::mutate(\n"
                    f"    {ret_var} = dplyr::row_number()\n"
                    f"  )\n"
                    f"{out_ds}"
                )

        # Pattern C: Carry Forward (LOCF): if <src> ne . then <var> = <src>;
        if len(remaining_stmts) == 1:
            m_locf = re.match(
                rf"^(?:if\s+(?:not\s+missing\((\w+)\)|(\w+)\s*(?:ne|!=)\s*\.)\s+then\s+)?{ret_var}\s*=\s*(\w+)$",
                remaining_stmts[0], re.I
            )
            if m_locf:
                src_var = (m_locf.group(1) or m_locf.group(2) or m_locf.group(3)).upper()
                return (
                    f"{out_ds} <- {in_ds} %>%\n"
                    f"  dplyr::mutate(\n"
                    f"    {ret_var} = {src_var}\n"
                    f"  ) %>%\n"
                    f"  tidyr::fill({ret_var}, .direction = \"down\")\n"
                    f"{out_ds}"
                )

        # All other RETAIN patterns -> SAFE REJECT
        return None

    def _translate_data_step_lag(self, code: str) -> Optional[str]:
        """Translate a DATA step with bounded unconditional LAGn() or DIF() processing.
        Supports:
        - PREV_AGE = lag(AGE); / PREV2 = lag2(AGE); / PREV3 = lag3(AGE);
        - DIFF = dif(AGE);
        - Multiple independent assignments: P1 = lag2(A); P2 = lag3(B);
        - Simple arithmetic with 1 lagN/dif call: DIFF = AGE - lag2(AGE);
        Returns R code string or None for unsupported patterns.
        """
        # Reject unsupported features and non-deterministic DIFn / dynamic LAG distance
        if re.search(r"\bdif\d+\s*\(", code, re.I) or re.search(r"\blag0+\s*\(", code, re.I) or re.search(r"\blag\d*\s*\(\s*[^)]*&", code, re.I):
            return None

        unsupported = [
            r"\bmerge\b", r"\bby\b", r"\bfirst\.", r"\blast\.", r"\bretain\b",
            r"\bdatalines\b", r"\bcards\b", r"\bproc\b", r"\bdo\b", r"\barray\b",
            r"\boutput\b", r"\bmodify\b", r"\bupdate\b", r"\bpoint\s*=", r"\bkey\s*=",
            r"\bif\b", r"\bwhere\b", r"\bthen\b", r"\belse\b"
        ]
        for pat in unsupported:
            if re.search(pat, code, re.I):
                return None

        out_m = re.search(r"^\s*data\s+([\w.]+)", code, re.I | re.M)
        set_m = re.search(r"^\s*set\s+([\w.]+)", code, re.I | re.M)
        if not out_m or not set_m:
            return None

        out_ds = out_m.group(1).split('.')[-1].upper()
        in_ds = set_m.group(1).split('.')[-1].upper()

        lines_raw = [l.strip() for l in code.split(";") if l.strip()]
        stmts = [
            l for l in lines_raw
            if not l.lower().startswith(("data ", "data\t", "set ", "set\t", "run"))
        ]

        if not stmts:
            return None

        mutate_lines = []

        def _r_lag_expr(call_str):
            m_l = re.match(r"^lag(\d*)\s*\(\s*(\w+)\s*\)$", call_str, re.I)
            m_d = re.match(r"^dif\s*\(\s*(\w+)\s*\)$", call_str, re.I)
            if m_l:
                n_str = m_l.group(1)
                v = m_l.group(2).upper()
                if not n_str or n_str == "1":
                    return f"dplyr::lag({v})"
                else:
                    n_val = int(n_str)
                    if n_val <= 0: return None
                    return f"dplyr::lag({v}, {n_val})"
            elif m_d:
                v = m_d.group(1).upper()
                return f"{v} - dplyr::lag({v})"
            return None

        for stmt in stmts:
            m_assign = re.match(r"^(\w+)\s*=\s*(.+)$", stmt, re.I)
            if not m_assign:
                return None

            target_var = m_assign.group(1).strip().upper()
            expr = m_assign.group(2).strip()

            lag_or_dif_calls = re.findall(r"\b(?:lag\d*|dif)\s*\(", expr, re.I)
            if len(lag_or_dif_calls) == 0:
                mutate_lines.append(f"    {target_var} = {expr}")
                continue
            elif len(lag_or_dif_calls) > 1:
                return None

            # Must NOT be nested: lag(lag(x)) or dif(dif(x)) or lag(dif(x))
            if re.search(r"\b(?:lag\d*|dif)\s*\(\s*(?:lag\d*|dif)\s*\(", expr, re.I):
                return None

            # Pattern 1: Simple lagN or dif call
            m_simple = re.match(r"^(lag\d*|dif)\s*\(\s*(\w+)\s*\)$", expr, re.I)
            # Pattern 2: Arithmetic: var op (lagN|dif)
            m_arith_1 = re.match(r"^(\w+)\s*([-+*/])\s*((?:lag\d*|dif)\s*\(\s*\w+\s*\))$", expr, re.I)
            # Pattern 3: Arithmetic: (lagN|dif) op var
            m_arith_2 = re.match(r"^((?:lag\d*|dif)\s*\(\s*\w+\s*\))\s*([-+*/])\s*(\w+)$", expr, re.I)

            if m_simple:
                r_expr = _r_lag_expr(expr)
                if not r_expr: return None
            elif m_arith_1:
                left_var = m_arith_1.group(1).upper()
                op = m_arith_1.group(2)
                r_sub = _r_lag_expr(m_arith_1.group(3))
                if not r_sub: return None
                r_expr = f"{left_var} {op} {r_sub}"
            elif m_arith_2:
                r_sub = _r_lag_expr(m_arith_2.group(1))
                op = m_arith_2.group(2)
                right_var = m_arith_2.group(3).upper()
                if not r_sub: return None
                r_expr = f"{r_sub} {op} {right_var}"
            else:
                return None

            mutate_lines.append(f"    {target_var} = {r_expr}")

        mut_str = ",\n".join(mutate_lines)
        return (
            f"{out_ds} <- {in_ds} %>%\n"
            f"  dplyr::mutate(\n"
            f"{mut_str}\n"
            f"  )\n"
            f"{out_ds}"
        )

    def _translate_data_step_select_when(self, code: str) -> Optional[str]:
        """Translate a DATA step with bounded SELECT/WHEN/OTHERWISE structure.
        Supports:
        select; when (cond1) VAR=val1; when (cond2) VAR=val2; otherwise VAR=val_def; end;
        select(EXPR); when ('val1') VAR=val1; otherwise VAR=val_def; end;
        """
        unsupported = [
            r"\bmerge\b", r"\bby\b", r"\bfirst\.", r"\blast\.", r"\bretain\b", r"\blag\b",
            r"\bdatalines\b", r"\bcards\b", r"\bproc\b", r"\bdo\b", r"\barray\b",
            r"\boutput\b", r"\bmodify\b", r"\bupdate\b", r"\bpoint\s*=", r"\bkey\s*="
        ]
        for pat in unsupported:
            if re.search(pat, code, re.I):
                return None

        out_m = re.search(r"^\s*data\s+([\w.]+)", code, re.I | re.M)
        set_m = re.search(r"^\s*set\s+([\w.]+)", code, re.I | re.M)
        if not out_m or not set_m:
            return None

        out_ds = out_m.group(1).split('.')[-1].upper()
        in_ds = set_m.group(1).split('.')[-1].upper()

        m_sel = re.search(r"\bselect\s*(\([^)]*\))?\s*;(.*?)end\s*;", code, re.I | re.DOTALL)
        if not m_sel:
            return None

        sel_expr_raw = m_sel.group(1)
        sel_var = sel_expr_raw.strip()[1:-1].strip() if sel_expr_raw else None
        block_content = m_sel.group(2).strip()

        when_matches = re.findall(r"when\s*\(([^)]+)\)\s*(\w+)\s*=\s*(.*?);", block_content, re.I)
        m_oth = re.search(r"otherwise\s+(\w+)\s*=\s*(.*?);", block_content, re.I)

        if not when_matches:
            when_matches = re.findall(r"when\s*\((['\"][^'\"]+['\"]|\w+)\)\s*(\w+)\s*=\s*(.*?);", block_content, re.I)

        if not when_matches:
            return None

        target_vars = {m[1].upper() for m in when_matches}
        if m_oth:
            target_vars.add(m_oth.group(1).upper())
        if len(target_vars) != 1:
            return None
        target_var = list(target_vars)[0]

        cases = []
        for w_cond, w_var, w_val in when_matches:
            w_val_norm = self._normalize_sas_elementwise_functions(w_val.strip())
            w_val_norm = self._normalize_sas_date_literals(w_val_norm)
            if sel_var:
                cond_str = f"{sel_var} == {w_cond.strip()}"
            else:
                cond_str = self._normalize_sas_condition(w_cond.strip())
            cases.append(f"      {cond_str} ~ {w_val_norm}")

        if m_oth:
            oth_val = self._normalize_sas_elementwise_functions(m_oth.group(2).strip())
            oth_val = self._normalize_sas_date_literals(oth_val)
            cases.append(f"      TRUE ~ {oth_val}")

        case_str = ",\n".join(cases)

        return (
            f"{out_ds} <- {in_ds} %>%\n"
            f"  dplyr::mutate(\n"
            f"    {target_var} = dplyr::case_when(\n"
            f"{case_str}\n"
            f"    )\n"
            f"  )\n"
            f"{out_ds}"
        )

    def _translate_data_step_delete(self, code: str) -> Optional[str]:
        """Translate a DATA step with single conditional DELETE statement: if cond then delete;"""
        unsupported = [
            r"\bmerge\b", r"\bby\b", r"\bfirst\.", r"\blast\.", r"\bretain\b", r"\blag\b",
            r"\bdatalines\b", r"\bcards\b", r"\bproc\b", r"\bdo\b", r"\barray\b",
            r"\boutput\b", r"\bmodify\b", r"\bupdate\b", r"\bpoint\s*=", r"\bkey\s*="
        ]
        for pat in unsupported:
            if re.search(pat, code, re.I):
                return None

        out_m = re.search(r"^\s*data\s+([\w.]+)", code, re.I | re.M)
        set_m = re.search(r"^\s*set\s+([\w.]+)", code, re.I | re.M)
        if not out_m or not set_m:
            return None

        out_ds = out_m.group(1).split('.')[-1].upper()
        in_ds = set_m.group(1).split('.')[-1].upper()

        m_del = re.search(r"\bif\s+(.*?)\s+then\s+delete\s*;", code, re.I)
        if not m_del:
            return None

        del_cond = m_del.group(1).strip()
        norm_cond = self._normalize_sas_condition(del_cond)

        return (
            f"{out_ds} <- {in_ds} %>%\n"
            f"  dplyr::filter(!({norm_cond}))\n"
            f"{out_ds}"
        )

    def _translate_data_step_schema_rename(self, code: str) -> Optional[str]:
        """Translate a DATA step with drop, keep, and/or rename statements.
        Important: Applied at END of pipeline after any assignments.
        """
        unsupported = [
            r"\bmerge\b", r"\bby\b", r"\bfirst\.", r"\blast\.", r"\bretain\b", r"\blag\b",
            r"\bdatalines\b", r"\bcards\b", r"\bproc\b", r"\bdo\b", r"\barray\b",
            r"\boutput\b", r"\bmodify\b", r"\bupdate\b", r"\bpoint\s*=", r"\bkey\s*="
        ]
        for pat in unsupported:
            if re.search(pat, code, re.I):
                return None

        out_m = re.search(r"^\s*data\s+([\w.]+)", code, re.I | re.M)
        set_m = re.search(r"^\s*set\s+([\w.]+)", code, re.I | re.M)
        if not out_m or not set_m:
            return None

        out_ds = out_m.group(1).split('.')[-1].upper()
        in_ds = set_m.group(1).split('.')[-1].upper()

        # Reject conflicting DROP + KEEP
        if re.search(r"\bdrop\b", code, re.I) and re.search(r"\bkeep\b", code, re.I):
            return None

        lines_raw = [l.strip() for l in code.split(";") if l.strip()]
        stmts = [
            l for l in lines_raw
            if not l.lower().startswith(("data ", "data\t", "set ", "set\t", "run"))
        ]

        pipe_steps = [f"{out_ds} <- {in_ds}"]
        mutates = []
        schema_step = None
        rename_step = None

        filters = []
        for stmt in stmts:
            m_drop = re.match(r"^drop\s+(.+)$", stmt, re.I)
            m_keep = re.match(r"^keep\s+(.+)$", stmt, re.I)
            m_rename = re.match(r"^rename\s+(.+)$", stmt, re.I)
            m_if_not_missing = re.match(r"^if\s+not\s+missing\s*\((.+)\)$", stmt, re.I)
            m_if_cond = re.match(r"^if\s+(.+)$", stmt, re.I)
            m_assign = re.match(r"^(\w+)\s*=\s*(.+)$", stmt, re.I)

            if m_drop:
                drop_vars = [v.upper() for v in m_drop.group(1).split()]
                drop_str = ", ".join(f"-{v}" for v in drop_vars)
                schema_step = f"  dplyr::select({drop_str})"
            elif m_keep:
                keep_vars = [v.upper() for v in m_keep.group(1).split()]
                keep_str = ", ".join(keep_vars)
                schema_step = f"  dplyr::select({keep_str})"
            elif m_rename:
                pairs = m_rename.group(1).split()
                ren_pairs = []
                for p in pairs:
                    if "=" not in p:
                        return None
                    old_v, new_v = p.split("=")
                    ren_pairs.append(f"{new_v.strip().upper()} = {old_v.strip().upper()}")
                rename_str = ", ".join(ren_pairs)
                rename_step = f"  dplyr::rename({rename_str})"
            elif m_if_not_missing:
                col = m_if_not_missing.group(1).strip().upper()
                filters.append(f"  dplyr::filter(!is.na({col}))")
            elif m_if_cond:
                cond = m_if_cond.group(1).strip()
                cond_r = self._normalize_sas_condition(cond)
                filters.append(f"  dplyr::filter({cond_r})")
            elif m_assign:
                var_n = m_assign.group(1).upper()
                val_e = self._normalize_sas_elementwise_functions(m_assign.group(2))
                val_e = self._normalize_sas_date_literals(val_e)
                val_e = self._normalize_sas_char_missing(val_e)
                mutates.append(f"    {var_n} = {val_e}")
            else:
                return None

        if filters:
            pipe_steps.extend(filters)
        if mutates:
            mut_str = ",\n".join(mutates)
            pipe_steps.append(f"  dplyr::mutate(\n{mut_str}\n  )")
        if schema_step:
            pipe_steps.append(schema_step)
        if rename_step:
            pipe_steps.append(rename_step)

        if len(pipe_steps) == 1:
            return None

        return " %>%\n".join(pipe_steps) + f"\n{out_ds}"

    def _translate_data_step_filter(self, code: str) -> Optional[str]:
        out_m = re.search(r"^\s*data\s+([\w.]+)", code, re.I | re.M)
        set_m = re.search(r"set\s+([\w.]+)", code, re.I)
        if not out_m or not set_m: return None

        out_ds = out_m.group(1).split('.')[-1].upper()
        in_ds = set_m.group(1).split('.')[-1].upper()
        code_clean = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
        stmts = [re.sub(r'\s+', ' ', s.strip()) for s in code_clean.split(';') if s.strip()]
        code_clean = '\n'.join(s + ';' for s in stmts)

        # 1. Collect all subsetting IF / WHERE statements (ending with semicolon, without THEN)
        filters = []
        for f_match in re.finditer(r'(?:if|where)\s+([^;]+?);', code_clean, re.I):
            stmt = f_match.group(1).strip()
            if not re.search(r'\bthen\b', stmt, re.I):
                r_cond = self._normalize_sas_condition(stmt)
                filters.append(r_cond.strip())

        # 2. Collect simple variable assignments (e.g. STUDY = "STUDY001";)
        mutates = []
        for a_match in re.finditer(r'^\s*(\w+)\s*=\s*([^;]+);', code_clean, re.I | re.M):
            var_name = a_match.group(1).strip().upper()
            val_expr = a_match.group(2).strip()
            if var_name not in ("SET", "DATA", "LENGTH", "KEEP", "DROP", "RENAME") and not re.search(r'^(if|where|proc|run)\b', var_name, re.I):
                val_expr = self._normalize_sas_elementwise_functions(val_expr)
                val_expr = self._normalize_sas_date_literals(val_expr)
                val_expr = self._normalize_sas_char_missing(val_expr)
                if "%sysfunc" in val_expr.lower() or "today()" in val_expr.lower():
                    mutates.append(f'{var_name} = Sys.Date()')
                else:
                    mutates.append(f'{var_name} = {val_expr}')

        # 3. Collect IF-THEN-ELSE derivation chains
        lines_code = [l.strip() for l in code_clean.split('\n') if l.strip()]
        idx = 0
        while idx < len(lines_code):
            line = lines_code[idx]
            m_if = re.match(r'if\s+(.*?)\s+then\s+(\w+)\s*=\s*(.*?);', line, re.I)
            if m_if:
                cond1 = m_if.group(1).strip()
                var_name = m_if.group(2).strip().upper()
                val1 = m_if.group(3).strip()
                cases = [(cond1, val1)]
                default_val = None

                j = idx + 1
                while j < len(lines_code):
                    next_line = lines_code[j]
                    m_else_if = re.match(r'else\s+if\s+(.*?)\s+then\s+' + var_name + r'\s*=\s*(.*?);', next_line, re.I)
                    if m_else_if:
                        cases.append((m_else_if.group(1).strip(), m_else_if.group(2).strip()))
                        j += 1
                        continue

                    m_else = re.match(r'else\s+' + var_name + r'\s*=\s*(.*?);', next_line, re.I)
                    if m_else:
                        default_val = m_else.group(1).strip()
                        j += 1
                        break
                    break

                idx = j
                cw_parts = []
                for c, v in cases:
                    rc = self._normalize_sas_condition(c)
                    cw_parts.append(f'{rc} ~ {v}')
                if default_val is not None:
                    def_v = "NA_real_" if default_val in ('.', 'NA') else default_val
                    cw_parts.append(f'TRUE ~ {def_v}')

                mutates.append(f'{var_name} = case_when(' + ', '.join(cw_parts) + ')')
                continue
            idx += 1

        pipe_lines = [f"{out_ds} <- {in_ds}"]
        if filters:
            pipe_lines.append("  filter(" + ", ".join(filters) + ")")
        if mutates:
            pipe_lines.append("  mutate(\n    " + ",\n    ".join(mutates) + "\n  )")

        if self.is_tidyverse and len(pipe_lines) > 1:
            return " %>%\n".join(pipe_lines) + f"\n{out_ds}"
        elif not self.is_tidyverse:
            return f"{out_ds} <- {in_ds}\n{out_ds}"
        
        # Simple fallback filter if single filter
        if filters:
            return f"{out_ds} <- {in_ds} %>%\n  filter({filters[0]})\n{out_ds}"
        return f"{out_ds} <- {in_ds}\n{out_ds}"
    def _translate_data_step_do_loop(self, code: str) -> Optional[str]:
        """Translate a DATA step containing a single bounded DO loop.
        Supported pattern (exactly one loop, numeric bounds, simple assignments, single OUTPUT):
            data <out>;
            set <in>;
            do <idx> = <start> to <end>;
                <var> = <expr>;
                ...
                output;
            end;
        Returns R code using tidyverse pipeline or None for unsupported patterns.
        """
        # 1. Detect output dataset
        out_m = re.search(r"^\s*data\s+([\w.]+)", code, re.I | re.M)
        if not out_m:
            return None
        out_ds = out_m.group(1).split('.')[-1].upper()

        # 2. Optional input dataset (SET) and MERGE guard
        set_m = re.search(r"set\s+([\w.]+)", code, re.I)
        in_ds = set_m.group(1).split('.')[-1].upper() if set_m else None
        # Reject if MERGE is present, as DO-loop rule should not apply to merge steps
        if re.search(r"\bmerge\b", code, re.I):
            return None
        # 3. Single DO loop with numeric bounds
        do_pattern = r"do\s+(\w+)\s*=\s*(\d+)\s+to\s+(\d+);(.*?)output;\s*end;"
        do_match = re.search(do_pattern, code, re.I | re.DOTALL)
        if not do_match:
            return None
        loop_var, start_str, end_str, body = do_match.groups()
        start = int(start_str)
        end = int(end_str)
        if start > end:
            return None

        # Ensure only one DO loop in the whole step
        if len(re.findall(r"\bdo\b", code, re.I)) != 1:
            return None

        # 4. Extract simple assignments from loop body (excluding OUTPUT)
        assignments = []
        stmts = [s.strip() for s in body.split(';') if s.strip()]
        for stmt in stmts:
            assign_match = re.match(r"^(\w+)\s*=\s*(.+)$", stmt, re.I)
            if not assign_match:
                return None
            var_name = assign_match.group(1).strip().upper()
            expr = assign_match.group(2).strip()
            expr = self._normalize_sas_date_literals(expr)
            expr = self._normalize_sas_char_missing(expr)
            expr = self._normalize_sas_condition(expr)
            assignments.append(f"{var_name} = {expr}")

        if not assignments:
            return None

        # 5. Build R pipeline (tidyverse style)
        r_code = (
            f"{out_ds} <- data.frame({loop_var.lower()} = {start}:{end}) %>%\n"
            f"  dplyr::mutate(\n    " + ",\n    ".join(assignments) + "\n  )\n"
            f"{out_ds}"
        )
        return r_code
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
        join_m = re.search(r"(left|right|inner|full)?\s*join\s+([\w.]+)(?:\s+(?:as\s+)?(\w+))?\s+on\s+(.*?)(?=\bwhere\b|\bgroup\s+by\b|\bhaving\b|\border\s+by\b|;|\bquit\b)", code_clean, re.I | re.DOTALL)
        join_ds = None
        join_type = "left_join"
        join_on = None
        right_alias = None
        join_key = None

        if join_m:
            jtype = (join_m.group(1) or "left").lower()
            join_type = f"{jtype}_join"
            join_ds = join_m.group(2).split('.')[-1].upper()
            right_alias = join_m.group(3) or join_ds
            join_on_raw = join_m.group(4).strip() if join_m.group(4) else ""
            on_match = re.search(r"(?:\w+\.)?(\w+)\s*=\s*(?:\w+\.)?(\w+)", join_on_raw, re.I)
            if on_match:
                join_key = on_match.group(1)
                join_on = f'"{join_key}"'

        # 3. SELECT clause items & Alias Mapping
        select_m = re.search(r"\bselect\s+(.*?)\s+\bfrom\b", code_clean, re.I | re.DOTALL)
        if not select_m:
            return None
        select_str = select_m.group(1).strip()

        # FAIL-CLOSED Safety Gate: Reject queries with unhandled CASE statements
        total_cases = len(re.findall(r'\bcase\b', select_str, re.I))
        sum_cases = len(re.findall(r'sum\s*\(\s*case\s+when', select_str, re.I))

        keywords = ("else", "end", "from", "where", "group", "by", "having", "order", "as", "select", "then", "when", "case")

        nested_case_pat = r'\bcase\s+when\s+((?:(?!\bcase\b|\bwhen\b|\bthen\b).)+)\s+then\s+case\s+when\s+((?:(?!\bcase\b|\bwhen\b|\bthen\b).)+)\s+then\s+((?:(?!\bcase\b|\bwhen\b|\belse\b).)+)\s+else\s+((?:(?!\bcase\b|\bwhen\b|\bend\b).)+)\s+end\s+else\s+((?:(?!\bcase\b|\bwhen\b|\bend\b).)+)\s+end(?:\s+as)?\s+([a-zA-Z_]\w*)'
        nested_case_matches = []
        select_str_for_scalar = select_str
        for m in re.finditer(nested_case_pat, select_str, re.I | re.DOTALL):
            if m.group(6).strip().lower() not in keywords:
                nested_case_matches.append(m)
                select_str_for_scalar = select_str_for_scalar.replace(m.group(0), '')

        scalar_case_pat = r'\bcase\s+when\s+((?:(?!\bcase\b|\bwhen\b|\bthen\b).)+)\s+then\s+((?:(?!\bcase\b|\bwhen\b|\belse\b).)+)\s+else\s+((?:(?!\bcase\b|\bwhen\b|\bend\b).)+)\s+end(?:\s+as)?\s+([a-zA-Z_]\w*)'
        scalar_case_matches = []
        for m in re.finditer(scalar_case_pat, select_str_for_scalar, re.I | re.DOTALL):
            if m.group(4).strip().lower() not in keywords:
                scalar_case_matches.append(m)

        scalar_cases = len(scalar_case_matches)
        nested_cases = len(nested_case_matches)

        supported_cases = sum_cases + scalar_cases + (nested_cases * 2)
        if total_cases > supported_cases:
            return None

        # Parse select items & build alias_map (e.g. "sum(amount)" -> "total_spent")
        summarise_items = []
        mutate_items = []
        alias_map = {}  # { "sum(amount)": "total_spent", ... }

        for match in scalar_case_matches:
            cond_raw = match.group(1).strip()
            then_val = match.group(2).strip()
            else_val = match.group(3).strip()
            alias_name = match.group(4).strip()

            cond_clean = re.sub(r'\b[a-zA-Z_]\w*\.', '', cond_raw)
            cond_clean = re.sub(r'(?<![<>!=])=(?!=)', '==', cond_clean)
            cond_clean = re.sub(r'\s*\band\b\s*', ' & ', cond_clean, flags=re.I)
            cond_clean = re.sub(r'\s*\bor\b\s*', ' | ', cond_clean, flags=re.I)
            cond_clean = cond_clean.strip()

            mutate_items.append(f"{alias_name} = dplyr::case_when(\n      {cond_clean} ~ {then_val},\n      TRUE ~ {else_val}\n    )")

        for match in nested_case_matches:
            cond1_raw = match.group(1).strip()
            cond2_raw = match.group(2).strip()
            val2 = match.group(3).strip()
            val3 = match.group(4).strip()
            val4 = match.group(5).strip()
            alias_name = match.group(6).strip()

            cond1_clean = re.sub(r'\b[a-zA-Z_]\w*\.', '', cond1_raw)
            cond1_clean = re.sub(r'(?<![<>!=])=(?!=)', '==', cond1_clean)
            cond1_clean = re.sub(r'\s*\band\b\s*', ' & ', cond1_clean, flags=re.I)
            cond1_clean = re.sub(r'\s*\bor\b\s*', ' | ', cond1_clean, flags=re.I).strip()

            cond2_clean = re.sub(r'\b[a-zA-Z_]\w*\.', '', cond2_raw)
            cond2_clean = re.sub(r'(?<![<>!=])=(?!=)', '==', cond2_clean)
            cond2_clean = re.sub(r'\s*\band\b\s*', ' & ', cond2_clean, flags=re.I)
            cond2_clean = re.sub(r'\s*\bor\b\s*', ' | ', cond2_clean, flags=re.I).strip()

            mutate_items.append(f"{alias_name} = dplyr::case_when(\n      {cond1_clean} & {cond2_clean} ~ {val2},\n      {cond1_clean} ~ {val3},\n      TRUE ~ {val4}\n    )")

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

            # Check conditional sum e.g. sum(case when serious = "Y" then 1 else 0 end) or sum(case when AGE >= 65 and SEX = "F" then 1 else 0 end)
            case_sum_m = re.search(r'sum\s*\(\s*case\s+when\s+(.*?)\s+then\s+1\s+else\s+0\s+end\s*\)', expr, re.I | re.DOTALL)
            cdist_m = re.search(r'count\s*\(\s*distinct\s+([\w.]+)\s*\)', expr, re.I | re.DOTALL)

            if case_sum_m:
                cond_raw = case_sum_m.group(1).strip()
                cond_clean = re.sub(r'\b[a-zA-Z_]\w*\.', '', cond_raw)
                cond_clean = re.sub(r'(?<![<>!=])=(?!=)', '==', cond_clean)
                cond_clean = re.sub(r'\s*\band\b\s*', ' & ', cond_clean, flags=re.I)
                cond_clean = re.sub(r'\s*\bor\b\s*', ' | ', cond_clean, flags=re.I)
                cond_clean = cond_clean.strip()
                a_name = alias or "sum_case_val"
                summarise_items.append(f"{a_name} = sum(if_else({cond_clean}, 1, 0), na.rm = TRUE)")
                alias_map[expr_clean] = a_name
            elif cdist_m:
                c_var = cdist_m.group(1).split('.')[-1]
                a_name = alias or f"count_distinct_{c_var}"
                summarise_items.append(f"{a_name} = dplyr::n_distinct({c_var})")
                alias_map[expr_clean] = a_name
                alias_map[f"count(distinct{c_var.lower()})"] = a_name
            # Check aggregate functions
            elif re.search(r'count\s*\(\s*\*\s*\)', expr, re.I):
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

            # Handle scalar subqueries (avg, max, min) in WHERE clause
            if re.search(r'\(\s*select\s+', w_raw, re.I):
                sub_match = re.search(r'\(\s*select\s+(avg|max|min)\s*\(\s*([\w\.]+)\s*\)\s+from\s+([\w\.]+)\s*\)', w_raw, re.I)
                if not sub_match:
                    return None  # Unsupported subquery pattern -> fail closed
                agg_func = sub_match.group(1).lower()
                col_name = sub_match.group(2).split('.')[-1]
                if agg_func == 'avg':
                    replacement = f"mean({col_name}, na.rm = TRUE)"
                elif agg_func == 'max':
                    replacement = f"max({col_name}, na.rm = TRUE)"
                elif agg_func == 'min':
                    replacement = f"min({col_name}, na.rm = TRUE)"
                else:
                    return None
                w_raw = re.sub(r'\(\s*select\s+(?:avg|max|min)\s*\(\s*[\w\.]+\s*\)\s+from\s+[\w\.]+\s*\)', replacement, w_raw, flags=re.I)

            # Check if right-side JOIN KEY is checked for NULL / IS NOT NULL in WHERE clause
            if join_ds and join_type == "left_join" and right_alias and join_key:
                is_not_null_pat = rf"\b({right_alias}|{join_ds})\.{join_key}\s+is\s+not\s+null\b"
                is_null_pat = rf"\b({right_alias}|{join_ds})\.{join_key}\s+is\s+null\b"

                if re.search(is_not_null_pat, w_raw, re.I):
                    join_type = "inner_join"
                    w_raw = re.sub(is_not_null_pat, "", w_raw, flags=re.I).strip()
                    w_raw = re.sub(r"^\s*(and|or)\s+", "", w_raw, flags=re.I).strip()
                    w_raw = re.sub(r"\s+(and|or)\s*$", "", w_raw, flags=re.I).strip()
                    w_raw = re.sub(r"\s+(and|or)\s+(and|or)\s+", " \\1 ", w_raw, flags=re.I).strip()
                elif re.search(is_null_pat, w_raw, re.I):
                    join_type = "anti_join"
                    w_raw = re.sub(is_null_pat, "", w_raw, flags=re.I).strip()
                    w_raw = re.sub(r"^\s*(and|or)\s+", "", w_raw, flags=re.I).strip()
                    w_raw = re.sub(r"\s+(and|or)\s*$", "", w_raw, flags=re.I).strip()
                    w_raw = re.sub(r"\s+(and|or)\s+(and|or)\s+", " \\1 ", w_raw, flags=re.I).strip()

            if w_raw:
                w_raw = re.sub(r'\b[a-zA-Z_]\w*\.', '', w_raw)
                w_raw = re.sub(r'(\w+)\s+is\s+not\s+null\b', r'!is.na(\1)', w_raw, flags=re.I)
                w_raw = re.sub(r'(\w+)\s+is\s+null\b', r'is.na(\1)', w_raw, flags=re.I)
                w_raw = self._normalize_sas_date_literals(w_raw)
                w_raw = self._normalize_sas_char_missing(w_raw)
                w_raw = re.sub(r'(?<![<>!=])=(?!=)', '==', w_raw)
                w_raw = re.sub(r'\band\b', ' & ', w_raw, flags=re.I)
                w_raw = re.sub(r'\bor\b', ' | ', w_raw, flags=re.I)
                where_cond = w_raw.strip() if w_raw.strip() else None

        # 5. GROUP BY clause
        group_m = re.search(r"\bgroup\s+by\s+(.*?)(?=\bhaving\b|\border\s+by\b|;|\bquit\b)", code_clean, re.I | re.DOTALL)
        group_vars = []
        if group_m:
            g_raw = group_m.group(1).strip()
            group_vars = [re.sub(r'^\w+\.', '', v.strip()) for v in g_raw.split(',') if v.strip()]

        # Collect non-aggregate explicit select columns if no aggregate summarise_items and no group_vars
        select_cols = []
        if not summarise_items and not group_vars:
            select_str_plain = select_str
            for m in scalar_case_matches:
                select_str_plain = select_str_plain.replace(m.group(0), '')
            for m in nested_case_matches:
                select_str_plain = select_str_plain.replace(m.group(0), '')

            plain_items = [p.strip() for p in select_str_plain.split(',') if p.strip()]
            for item in plain_items:
                item_clean = item.strip()
                if item_clean == '*' or item_clean.lower().endswith('.*'):
                    select_cols = []
                    break
                # Skip aggregate functions, they are handled elsewhere
                if re.search(r'\b(count|sum|avg|mean|max|min|case)\b', item_clean, re.I):
                    continue
                # Remove any table prefixes
                col_name = re.sub(r'^\w+\.', '', item_clean)
                select_cols.append(col_name)

            for m in scalar_case_matches:
                alias_name = m.group(4).strip()
                if alias_name not in select_cols:
                    select_cols.append(alias_name)
            for m in nested_case_matches:
                alias_name = m.group(6).strip()
                if alias_name not in select_cols:
                    select_cols.append(alias_name)

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

        if mutate_items:
            m_str = ",\n    ".join(mutate_items)
            lines.append(f"  dplyr::mutate(\n    {m_str}\n  )")

        if select_cols:
            s_cols_str = ", ".join(select_cols)
            lines.append(f"  dplyr::select({s_cols_str})")
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

    def _translate_macro_call(self, code: str) -> Optional[str]:
        m = re.match(r'%([a-zA-Z_]\w*)\s*(?:\(([^)]*)\))?\s*;?', code.strip(), re.I)
        if not m:
            return None
        m_name = m.group(1).lower()
        if m_name.startswith('unknown') or m_name in ('rec', 'recursive'):
            return None
        args_str = m.group(2) or ""
        parts = [p.strip() for p in args_str.split(',') if p.strip()]
        if m_name == 'flag' and len(parts) < 2 and not any(p.startswith('out') for p in parts):
            return None

        target_ds = None
        r_args = []
        for part in args_str.split(','):
            part = part.strip()
            if not part:
                continue
            if '=' in part:
                k, v = part.split('=', 1)
                k = k.strip().lower()
                v = v.strip()
                if k in ('out', 'output'):
                    target_ds = v
                else:
                    if v.isdigit() or (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                        v_r = v
                    elif v.isupper() and len(v) <= 8 and re.match(r'^[A-Za-z_]\w*$', v) and k not in ('data', 'input', 'dataset'):
                        v_r = f'"{v}"'
                    else:
                        v_r = v
                    r_args.append(v_r)
            else:
                if part.isdigit() or (part.startswith('"') and part.endswith('"')) or (part.startswith("'") and part.endswith("'")):
                    v_r = part
                elif part.isupper() and len(part) <= 8 and re.match(r'^[A-Za-z_]\w*$', part):
                    v_r = f'"{part}"'
                else:
                    v_r = part
                r_args.append(v_r)

        call_str = f"{m_name}({', '.join(r_args)})"
        if target_ds:
            return f"{target_ds} <- {call_str}"
        return call_str
