"""
sas_parser.py
─────────────
Lexer, Parser, and AST Builder for the Enterprise SAS Modernization Engine.
Parses SAS code into ProgramAST, MacroIR, InfraIR, and DatasetLineage structures.
"""

from __future__ import annotations
import re
from typing import Optional, Any
from sas_ast import (
    ProgramAST, MacroIR, InfraIR, MacroParameter,
    DatasetLineage, ProgramStep, ComplexityMetrics
)


def _strip_comments(code: str) -> str:
    """Remove SAS block comments /* ... */ and * ... ; line comments."""
    # Block comments /* ... */
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
    # Line comments starting with * or comment; at statement start
    code = re.sub(r'^\s*\*[^;]*;', '', code, flags=re.MULTILINE)
    code = re.sub(r'^\s*comment\s+[^;]*;', '', code, flags=re.MULTILINE | re.IGNORECASE)
    return code


def parse_sas_program(sas_code: str) -> ProgramAST:
    """
    Main entry point. Parses raw SAS program code into a fully populated ProgramAST.
    """
    clean_code = _strip_comments(sas_code)
    
    ast = ProgramAST(raw_sas_code=sas_code)
    
    # 1. Parse Infrastructure constructs (LIBNAME, FILENAME, %INCLUDE, OPTIONS, TITLE/FOOTNOTE)
    ast.infrastructure = _parse_infrastructure(clean_code)
    
    # 2. Parse Macro definitions (%MACRO ... %MEND)
    ast.macros = _parse_macros(clean_code)
    
    # 3. Parse Program Execution Steps (DATA steps & PROC steps)
    ast.steps = _parse_program_steps(clean_code)
    
    # 4. Extract Dataset Lineage
    ast.lineage = _extract_lineage(ast.steps)
    
    # 5. Calculate Program Complexity Metrics
    ast.complexity = _calculate_complexity(ast)
    
    return ast


# ─────────────────────────────────────────────────────────────────
# INFRASTRUCTURE PARSER
# ─────────────────────────────────────────────────────────────────

def _parse_infrastructure(code: str) -> InfraIR:
    infra = InfraIR()
    
    # LIBNAME parsing
    # libname source "/path/to/dir" [engine]; or libname source odbc ...;
    for m in re.finditer(r'libname\s+(\w+)\s+(?:["\']([^"\']+)["\']|([^;]+));', code, re.I):
        libref = m.group(1).upper()
        path_or_conn = m.group(2) or m.group(3).strip()
        infra.libnames[libref] = path_or_conn
        if "odbc" in path_or_conn.lower() or "oracle" in path_or_conn.lower() or "postgres" in path_or_conn.lower():
            infra.review_items.append(f"Database connection in LIBNAME {libref}: {path_or_conn}")
            
    # FILENAME parsing
    for m in re.finditer(r'filename\s+(\w+)\s+["\']([^"\']+)["\'];', code, re.I):
        fileref = m.group(1).upper()
        path = m.group(2)
        infra.filenames[fileref] = path
        
    # %INCLUDE parsing
    for m in re.finditer(r'%include\s+(?:["\']([^"\']+)["\']|(\w+)(?:\([^)]*\))?)\s*;', code, re.I):
        inc_target = m.group(1) or m.group(2)
        infra.includes.append(inc_target)
        infra.review_items.append(f"External %INCLUDE directive: {inc_target}")
        
    # OPTIONS parsing
    for m in re.finditer(r'options\s+([^;]+);', code, re.I):
        opts_str = m.group(1).strip()
        for opt in opts_str.split():
            if '=' in opt:
                k, v = opt.split('=', 1)
                infra.options[k.strip().lower()] = v.strip()
            else:
                infra.options[opt.strip().lower()] = "TRUE"
                
    # TITLE & FOOTNOTE parsing
    for m in re.finditer(r'(?:title|footnote)\d*\s+["\']([^"\']+)["\'];', code, re.I):
        infra.titles_footnotes.append(m.group(0).strip())
        
    # PROC FORMAT parsing
    for m in re.finditer(r'proc\s+format\s*;(.*?)run\s*;', code, re.I | re.DOTALL):
        fmt_body = m.group(1)
        for val_match in re.finditer(r'value\s+(\$?\w+)\s+(.*?);', fmt_body, re.I | re.DOTALL):
            fmt_name = val_match.group(1).upper()
            fmt_mapping = val_match.group(2).strip()
            infra.user_formats[fmt_name] = {"raw_mapping": fmt_mapping}
            
    return infra


# ─────────────────────────────────────────────────────────────────
# MACRO PARSER
# ─────────────────────────────────────────────────────────────────

def _parse_macros(code: str) -> dict[str, MacroIR]:
    macros = {}
    
    # Recursively find all %macro <name> ... %mend blocks
    pos = 0
    while pos < len(code):
        macro_start = re.search(r'%macro\s+(\w+)(?:\s*\(([^)]*)\))?\s*;', code[pos:], re.I)
        if not macro_start:
            break
            
        start_idx = pos + macro_start.start()
        name = macro_start.group(1).upper().strip()
        raw_params = macro_start.group(2) or ""
        body_start_idx = pos + macro_start.end()
        
        # Find matching %mend for this macro
        depth = 1
        curr_p = body_start_idx
        body_end_idx = None
        
        for m_tok in re.finditer(r'(%macro\b|%mend\b)', code[body_start_idx:], re.I):
            tok = m_tok.group(1).lower()
            if tok == '%macro':
                depth += 1
            elif tok == '%mend':
                depth -= 1
                if depth == 0:
                    # Find semicolon after %mend
                    semicolon_idx = code.find(';', body_start_idx + m_tok.end())
                    if semicolon_idx != -1:
                        body_end_idx = body_start_idx + m_tok.start()
                        pos = semicolon_idx + 1
                    else:
                        body_end_idx = body_start_idx + m_tok.start()
                        pos = body_start_idx + m_tok.end()
                    break
                    
        if body_end_idx is None:
            pos = body_start_idx
            continue
            
        body = code[body_start_idx:body_end_idx].strip()
        
        # Parse Macro Parameters
        params = []
        if raw_params.strip():
            for p in raw_params.split(','):
                p = p.strip()
                if not p: continue
                if '=' in p:
                    pname, default_val = p.split('=', 1)
                    params.append(MacroParameter(
                        name=pname.strip().lstrip('&').upper(),
                        default_value=default_val.strip(),
                        is_keyword=True
                    ))
                else:
                    params.append(MacroParameter(
                        name=p.strip().lstrip('&').upper(),
                        default_value=None,
                        is_keyword=False
                    ))
                    
        # Parse %LET variables inside macro
        local_vars = []
        for let_match in re.finditer(r'%let\s+(\w+)\s*=', body, re.I):
            local_vars.append(let_match.group(1).upper())
            
        # Parse nested macro invocations (%name)
        nested_macros = []
        for call_match in re.finditer(r'%(\w+)\s*\(', body, re.I):
            sub_name = call_match.group(1).upper()
            if sub_name not in ("MACRO", "MEND", "LET", "IF", "THEN", "ELSE", "DO", "END", "SYSFUNC", "EVAL", "STR", "QUOTE", "NRSTR"):
                nested_macros.append(sub_name)
                
        # Parse %IF / %THEN / %ELSE structures
        conditions = []
        for if_match in re.finditer(r'%if\s+(.*?)\s*%then\s+(.*?);', body, re.I | re.DOTALL):
            conditions.append({
                "condition": if_match.group(1).strip(),
                "action": if_match.group(2).strip()
            })
            
        # Parse %DO loops (%DO %TO, %DO %WHILE, %DO %UNTIL)
        loops = []
        for do_to in re.finditer(r'%do\s+(\w+)\s*=\s*(.*?)\s*%to\s*(.*?);(.*?)%end\s*;', body, re.I | re.DOTALL):
            loops.append({
                "type": "DO_TO",
                "var": do_to.group(1).upper(),
                "start": do_to.group(2).strip(),
                "end": do_to.group(3).strip(),
            })
        for do_while in re.finditer(r'%do\s+%while\s*\((.*?)\)\s*;(.*?)%end\s*;', body, re.I | re.DOTALL):
            loops.append({
                "type": "DO_WHILE",
                "condition": do_while.group(1).strip(),
            })
        for do_until in re.finditer(r'%do\s+%until\s*\((.*?)\)\s*;(.*?)%end\s*;', body, re.I | re.DOTALL):
            loops.append({
                "type": "DO_UNTIL",
                "condition": do_until.group(1).strip(),
            })
            
        has_dynamic_naming = bool(re.search(r'&\w+\._?&\w+|&\w+_\d+', body))
        has_indirect_refs = bool(re.search(r'&&\w+', body))
        
        input_ds = list(set([d.upper() for d in re.findall(r'(?:set|from|join|data\s*=)\s+([\w.]+)', body, re.I)]))
        output_ds = list(set([d.upper() for d in re.findall(r'(?:^\s*data\s+|out\s*=\s*|create\s+table\s+)([\w.]+)', body, re.I | re.M)]))
        procs_used = list(set([p.upper() for p in re.findall(r'proc\s+(\w+)', body, re.I)]))
        
        score = 10.0 + len(params)*2 + len(nested_macros)*10 + len(conditions)*5 + len(loops)*8
        if has_dynamic_naming: score += 15
        if has_indirect_refs: score += 20
        
        macros[name] = MacroIR(
            name=name,
            parameters=params,
            local_vars=local_vars,
            nested_macros=nested_macros,
            conditions=conditions,
            loops=loops,
            input_datasets=input_ds,
            output_datasets=output_ds,
            procs_used=procs_used,
            complexity_score=min(score, 100.0),
            has_dynamic_naming=has_dynamic_naming,
            has_indirect_refs=has_indirect_refs,
            raw_body=body
        )
        
        # Also parse any nested macros defined inside body
        if "%macro" in body.lower():
            nested_parsed = _parse_macros(body)
            macros.update(nested_parsed)

    return macros


# ─────────────────────────────────────────────────────────────────
# PROGRAM STEP PARSER
# ─────────────────────────────────────────────────────────────────

def _parse_program_steps(code: str) -> list[ProgramStep]:
    steps = []
    
    # Extract executable statements (DATA step or PROC step)
    step_matches = re.finditer(r"((?:data|proc)\s+.*?;.*?(?:run|quit);)", code, re.DOTALL | re.I)
    
    for idx, match in enumerate(step_matches):
        step_code = match.group(1).strip()
        
        # Determine step type & name
        if step_code.lower().startswith("data"):
            step_type = "DATA_STEP"
            out_match = re.search(r"^\s*data\s+([\w.]+)", step_code, re.I | re.M)
            name = out_match.group(1).split('.')[-1].upper() if out_match else f"DATA_STEP_{idx+1}"
        else:
            step_type = "PROC_STEP"
            proc_match = re.search(r"proc\s+(\w+)", step_code, re.I)
            proc_name = proc_match.group(1).upper() if proc_match else "UNKNOWN"
            name = f"PROC {proc_name}"
            
        # Extract inputs & outputs
        inputs = list(set([d.split('.')[-1].upper() for d in re.findall(r"(?:set|from|join|data\s*=)\s+([\w.]+)", step_code, re.I)]))
        outputs = list(set([d.split('.')[-1].upper() for d in re.findall(r"(?:^\s*data\s+|out\s*=\s*|create\s+table\s+)([\w.]+)", step_code, re.I | re.M)]))
        
        steps.append(ProgramStep(
            step_index=idx + 1,
            step_type=step_type,
            name=name,
            source_code=step_code,
            input_datasets=inputs,
            output_datasets=outputs
        ))
        
    return steps


# ─────────────────────────────────────────────────────────────────
# LINEAGE PARSER
# ─────────────────────────────────────────────────────────────────

def _extract_lineage(steps: list[ProgramStep]) -> list[DatasetLineage]:
    lineage = []
    for s in steps:
        for out in s.output_datasets:
            lineage.append(DatasetLineage(
                dataset_name=out,
                source_datasets=s.input_datasets,
                operation_type=s.name,
                created_by_step=s.step_index
            ))
    return lineage


# ─────────────────────────────────────────────────────────────────
# COMPLEXITY CALCULATOR
# ─────────────────────────────────────────────────────────────────

def _calculate_complexity(ast: ProgramAST) -> ComplexityMetrics:
    macro_cnt = len(ast.macros)
    proc_cnt = sum(1 for s in ast.steps if s.step_type == "PROC_STEP")
    data_cnt = sum(1 for s in ast.steps if s.step_type == "DATA_STEP")
    
    dyn_cnt = sum(1 for m in ast.macros.values() if m.has_dynamic_naming)
    ind_cnt = sum(1 for m in ast.macros.values() if m.has_indirect_refs)
    infra_cnt = len(ast.infrastructure.libnames) + len(ast.infrastructure.filenames) + len(ast.infrastructure.includes)
    
    score = (data_cnt * 5) + (proc_cnt * 8) + (macro_cnt * 15) + (dyn_cnt * 20) + (ind_cnt * 25) + (infra_cnt * 5)
    score_clamped = min(float(score), 100.0)
    
    if score_clamped >= 60.0:
        risk = "High"
    elif score_clamped >= 30.0:
        risk = "Medium"
    else:
        risk = "Low"
        
    return ComplexityMetrics(
        score=score_clamped,
        macro_count=macro_cnt,
        proc_count=proc_cnt,
        data_step_count=data_cnt,
        dynamic_name_count=dyn_cnt,
        indirect_ref_count=ind_cnt,
        infra_count=infra_cnt,
        risk_level=risk
    )
