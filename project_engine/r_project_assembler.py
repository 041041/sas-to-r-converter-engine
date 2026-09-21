"""
project_engine/r_project_assembler.py
──────────────────────────────────────
Dedicated Project Assembler Layer for modular R project generation.
Transforms converted SAS macro/function results into a structured RProject representation.

Responsibility:
    converted macro/function results
            ↓
       RProjectAssembler
            ↓
    R project model (RProject) / file map
            ↓
       main.R + R/*.R
"""

from __future__ import annotations
import re
from pathlib import Path
from typing import Any, Optional
from project_engine.models import RProject, ProjectContext


class RProjectAssembler:
    """
    Assembles a modular R project representation (RProject) containing:
      - main.R (entrypoint & module sourcing)
      - R/<function_name>.R (one file per converted macro function)
    """

    def assemble(
        self,
        conversion_result: Optional[dict[str, Any]] = None,
        function_map: Optional[dict[str, str]] = None,
        r_functions_str: Optional[str] = None,
        dependency_order: Optional[list[str]] = None,
        macro_calls: Optional[list[str]] = None,
        project_name: str = "converted_project",
        entry_function: Optional[str] = None,
        project_context: Optional[ProjectContext] = None,
    ) -> RProject:
        """
        Main assembly entry point.
        Converts function results into an explicit RProject dataclass instance.
        """
        funcs: dict[str, str] = {}
        order: list[str] = []

        if function_map:
            funcs = dict(function_map)
        elif conversion_result and "function_map" in conversion_result and conversion_result["function_map"]:
            funcs = dict(conversion_result["function_map"])
        elif conversion_result and "r_functions" in conversion_result and conversion_result["r_functions"]:
            parsed_funcs, parsed_order = self._split_r_functions(conversion_result["r_functions"])
            funcs = parsed_funcs
            if not order and parsed_order:
                order = parsed_order
        elif r_functions_str:
            parsed_funcs, parsed_order = self._split_r_functions(r_functions_str)
            funcs = parsed_funcs
            if not order and parsed_order:
                order = parsed_order
        elif project_context and project_context.ordered_supporting_content:
            pass

        # Resolve dependency order
        if dependency_order:
            order = list(dependency_order)
        elif conversion_result and "ordered_macros" in conversion_result:
            order = list(conversion_result["ordered_macros"])
        elif not order:
            order = list(funcs.keys())

        # Ensure order includes any keys in funcs that might have been omitted
        for k in funcs.keys():
            if not any(k.upper() == o.upper() for o in order):
                order.append(k)

        source_files: dict[str, str] = {}
        r_module_paths: list[str] = []

        for name in order:
            # find matching key in funcs (case-insensitive fallback)
            key = name
            if name not in funcs:
                matched_key = None
                for fk in funcs.keys():
                    if fk.upper() == name.upper():
                        matched_key = fk
                        break
                if matched_key:
                    key = matched_key
                else:
                    continue

            code = funcs[key].strip()
            filename = self._macro_to_filename(key)
            rel_path = f"R/{filename}"

            if not code.endswith("\n"):
                code += "\n"

            source_files[rel_path] = code
            if rel_path not in r_module_paths:
                r_module_paths.append(rel_path)

        # 2. Extract calls
        calls_str = ""
        if macro_calls:
            calls_str = "\n".join(macro_calls)
        elif conversion_result and "r_calls" in conversion_result:
            calls_str = conversion_result.get("r_calls", "")

        # 3. Determine primary entry function
        if not entry_function and order:
            entry_function = order[-1].lower()

        # 4. Generate main.R content
        main_r_lines = [
            f"# {'─' * 60}",
            f"# Converted R Project Entrypoint: {project_name}",
            f"# {'─' * 60}",
            "",
        ]

        # Source statements in deterministic dependency order
        for rel_path in r_module_paths:
            main_r_lines.append(f'source("{rel_path}")')

        main_r_lines.append("")

        if calls_str and calls_str.strip():
            main_r_lines.append(f"# {'─' * 60}")
            main_r_lines.append("# Executable Calls")
            main_r_lines.append(f"# {'─' * 60}")
            main_r_lines.append(calls_str.strip())
            main_r_lines.append("")

        source_files["main.R"] = "\n".join(main_r_lines)

        meta = {
            "total_modules": len(r_module_paths),
            "modules": r_module_paths,
            "has_calls": bool(calls_str.strip()),
        }
        if conversion_result and "stats" in conversion_result:
            meta["stats"] = conversion_result["stats"]

        clean_order = [m.lower() for m in order]

        return RProject(
            project_name=project_name,
            main_file="main.R",
            source_files=source_files,
            entry_function=entry_function,
            dependency_order=clean_order,
            metadata=meta,
        )

    def _macro_to_filename(self, macro_name: str) -> str:
        """Derive safe R filename from SAS macro/function name."""
        clean = re.sub(r'[^a-zA-Z0-9_]', '', macro_name).lower()
        return f"{clean}.R"

    def _split_r_functions(self, r_functions_str: str) -> tuple[dict[str, str], list[str]]:
        """
        Parses a combined R functions string into an individual {macro_name: r_code} dict
        and an ordered list of macro names.
        """
        funcs = {}
        order = []

        # Split by separator headers if present
        blocks = re.split(r'(?=# ─{5,}\n# Macro: %)', r_functions_str)
        if len(blocks) > 1:
            for block in blocks:
                block = block.strip()
                if not block:
                    continue
                header_m = re.search(r'# Macro: %([A-Za-z0-9_]+)', block)
                if header_m:
                    m_name = header_m.group(1).upper()
                    funcs[m_name] = block
                    if m_name not in order:
                        order.append(m_name)
        else:
            # Fallback: search for top-level function declarations: name <- function
            pattern = re.compile(r'(?:^|\n)([a-zA-Z0-9_]+)\s*<-\s*function', re.MULTILINE)
            matches = list(pattern.finditer(r_functions_str))
            for idx, m in enumerate(matches):
                fn_name = m.group(1)
                start_pos = m.start()
                if idx + 1 < len(matches):
                    end_pos = matches[idx + 1].start()
                    code = r_functions_str[start_pos:end_pos].strip()
                else:
                    code = r_functions_str[start_pos:].strip()
                funcs[fn_name.upper()] = code
                if fn_name.upper() not in order:
                    order.append(fn_name.upper())

        return funcs, order
