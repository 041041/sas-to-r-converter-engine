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
