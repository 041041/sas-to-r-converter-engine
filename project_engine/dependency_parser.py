"""
project_engine/dependency_parser.py
───────────────────────────────────
Dependency Parser for discovering macro calls and references in SAS source code.
"""

from __future__ import annotations
import re
from project_engine.models import MacroReference


class DependencyParser:
    """Parses SAS code to discover macro calls while ignoring built-in SAS macro keywords."""

    BUILTIN_MACROS = {
        "macro", "mend", "let", "if", "then", "else", "do", "end", "put",
        "global", "local", "include", "str", "nstr", "quote", "bquote",
        "eval", "sysevalf", "sysfunc", "goto", "return", "display", "window",
        "symdef", "symdel", "sysget", "superq", "qsysfunc", "tslit", "unquote",
        "upcase", "lowcase", "substr", "scan", "sysrc", "sysmsg", "syserr",
        "sysjobid", "sysdate", "sysdate9", "systime", "sysday", "sysver",
        "sysexec", "abort", "input", "index", "length", "left", "right"
    }

    MACRO_CALL_PATTERN = re.compile(r"%([a-zA-Z_]\w*)\b", re.IGNORECASE)
    MACRO_BLOCK_PATTERN = re.compile(
        r"%macro\s+[a-zA-Z_]\w*(?:\s*\([^)]*\))?\s*;.*?%mend(?:\s+[a-zA-Z_]\w*)?\s*;",
        re.IGNORECASE | re.DOTALL
    )
    MACRO_DEF_HEADER_PATTERN = re.compile(
        r"%macro\s+[a-zA-Z_]\w*(?:\s*\([^)]*\))?\s*;", re.IGNORECASE
    )
    MACRO_MEND_PATTERN = re.compile(
        r"%mend(?:\s+[a-zA-Z_]\w*)?\s*;", re.IGNORECASE
    )

    @classmethod
    def strip_comments(cls, code: str) -> str:
        """Removes C-style /* ... */ and SAS line * ... ; comments."""
        code_no_block = re.sub(r"/\*.*?\*/", "", code, flags=re.DOTALL)
        lines = []
        for line in code_no_block.splitlines():
            stripped = line.strip()
            if stripped.startswith("*") and stripped.endswith(";"):
                continue
            lines.append(line)
        return "\n".join(lines)

    @classmethod
    def strip_macro_definitions(cls, code: str) -> str:
        """Removes entire %macro ... %mend; blocks to leave only outer main program code."""
        clean = cls.strip_comments(code)
        return cls.MACRO_BLOCK_PATTERN.sub("", clean)

    @classmethod
    def strip_macro_headers(cls, code: str) -> str:
        """Removes %macro header and %mend statements within a macro body."""
        clean = cls.strip_comments(code)
        clean = cls.MACRO_DEF_HEADER_PATTERN.sub("", clean)
        clean = cls.MACRO_MEND_PATTERN.sub("", clean)
        return clean

    def parse_main_references(self, caller_name: str, source_content: str, source_file: str) -> list[MacroReference]:
        """Discovers macro calls in top-level code outside of %macro definitions."""
        outer_code = self.strip_macro_definitions(source_content)
        return self._find_matches(caller_name, outer_code, source_file)

    def parse_references(self, caller_name: str, source_content: str, source_file: str) -> list[MacroReference]:
        """Discovers all non-builtin macro calls inside a macro body or code snippet."""
        clean_code = self.strip_macro_headers(source_content)
        return self._find_matches(caller_name, clean_code, source_file)

    def _find_matches(self, caller_name: str, code: str, source_file: str) -> list[MacroReference]:
        references = []
        seen = set()

        for match in self.MACRO_CALL_PATTERN.finditer(code):
            raw_name = match.group(1)
            norm_name = raw_name.upper()

            if raw_name.lower() in self.BUILTIN_MACROS:
                continue

            if norm_name in seen:
                continue
            seen.add(norm_name)

            line_num = code[:match.start()].count("\n") + 1
            ref = MacroReference(
                caller=caller_name,
                referenced_macro=norm_name,
                source_file=source_file,
                line=line_num
            )
            references.append(ref)

        return references
