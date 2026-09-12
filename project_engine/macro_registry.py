"""
project_engine/macro_registry.py
─────────────────────────────────
Macro Registry for discovering, indexing, and detecting duplicate SAS macro definitions.
"""

from __future__ import annotations
import re
from project_engine.models import MacroDefinition, MacroParameter, ProjectFile


class MacroRegistry:
    """Scans project files for macro definitions, normalizes names, and tracks duplicates."""

    MACRO_DEF_PATTERN = re.compile(
        r"%macro\s+([a-zA-Z_]\w*)(?:\s*\((.*?)\))?\s*;(.*?)%mend(?:\s+[a-zA-Z_]\w*)?\s*;",
        re.IGNORECASE | re.DOTALL
    )

    def __init__(self) -> None:
        self._macros: dict[str, MacroDefinition] = {}
        self._duplicates: dict[str, list[str]] = {}  # macro_name_upper -> list of filenames
        self._source_file_map: dict[str, list[str]] = {}  # macro_name_upper -> list of filenames

    @staticmethod
    def normalize_name(name: str) -> str:
        """Normalizes macro name to uppercase."""
        return name.strip().upper()

    def parse_parameters(self, param_str: str | None) -> list[MacroParameter]:
        """Parses macro parameter list into MacroParameter objects."""
        if not param_str or not param_str.strip():
            return []

        params = []
        raw_params = param_str.split(",")
        for p in raw_params:
            p = p.strip()
            if not p:
                continue
            if "=" in p:
                parts = p.split("=", 1)
                pname = parts[0].strip()
                pval = parts[1].strip() if len(parts) > 1 else ""
                params.append(MacroParameter(name=pname, default_value=pval, is_keyword=True))
            else:
                params.append(MacroParameter(name=p, default_value=None, is_keyword=False))
        return params

    def scan_file(self, project_file: ProjectFile) -> list[MacroDefinition]:
        """Scans a ProjectFile for all macro definitions."""
        found = []
        content = project_file.source_content
        filename = project_file.filename

        for match in self.MACRO_DEF_PATTERN.finditer(content):
            orig_name = match.group(1).strip()
            norm_name = self.normalize_name(orig_name)
            params_raw = match.group(2)
            body_full = match.group(0)

            # Compute line numbers
            start_line = content[:match.start()].count('\n') + 1
            end_line = content[:match.end()].count('\n') + 1

            params = self.parse_parameters(params_raw)

            macro_def = MacroDefinition(
                name=norm_name,
                original_name=orig_name,
                source_file=filename,
                start_line=start_line,
                end_line=end_line,
                source_content=body_full,
                parameters=params
            )

            # Track source files for duplicate detection
            if norm_name not in self._source_file_map:
                self._source_file_map[norm_name] = [filename]
            else:
                if filename not in self._source_file_map[norm_name]:
                    self._source_file_map[norm_name].append(filename)

            if len(self._source_file_map[norm_name]) > 1:
                self._duplicates[norm_name] = self._source_file_map[norm_name].copy()
            else:
                self._macros[norm_name] = macro_def

            found.append(macro_def)

        return found

    def register_macro(self, macro_def: MacroDefinition) -> None:
        """Manually registers a macro definition."""
        norm_name = self.normalize_name(macro_def.name)
        if norm_name not in self._source_file_map:
            self._source_file_map[norm_name] = [macro_def.source_file]
        else:
            if macro_def.source_file not in self._source_file_map[norm_name]:
                self._source_file_map[norm_name].append(macro_def.source_file)

        if len(self._source_file_map[norm_name]) > 1:
            self._duplicates[norm_name] = self._source_file_map[norm_name].copy()
        else:
            self._macros[norm_name] = macro_def

    def get_macro(self, name: str) -> MacroDefinition | None:
        """Retrieves a registered macro definition by name."""
        return self._macros.get(self.normalize_name(name))

    def has_duplicate(self, name: str) -> bool:
        """Checks if a macro name has duplicate definitions across files."""
        return self.normalize_name(name) in self._duplicates

    def get_duplicates(self) -> dict[str, list[str]]:
        """Returns all duplicate macro definitions."""
        return self._duplicates.copy()

    def all_macros(self) -> dict[str, MacroDefinition]:
        """Returns map of normalized macro names to definitions."""
        return self._macros.copy()

    def __len__(self) -> int:
        return len(self._macros)
