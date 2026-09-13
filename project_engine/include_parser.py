"""
project_engine/include_parser.py
──────────────────────────────────
Static parser for discovering %INCLUDE directives in SAS source code without executing code.
"""

from __future__ import annotations
import re
import os
from project_engine.models import IncludeReference


class IncludeParser:
    """Parses SAS code statically to discover %INCLUDE directives."""

    INCLUDE_PATTERN = re.compile(
        r"%include\s+(?:\"([^\"]+)\"|'([^']+)'|([^\s;]+))\s*;",
        re.IGNORECASE
    )

    @classmethod
    def normalize_include_path(cls, raw_path: str) -> str:
        """
        Normalizes include target path to match ProjectFileRegistry keys.
        e.g. './setup.sas' -> 'setup.sas', '"./sub/setup.sas"' -> 'setup.sas'
        """
        clean = raw_path.strip().strip("'\"").strip()
        # Remove leading ./ or .\
        clean = re.sub(r"^\.[\/\\]", "", clean)
        # Take basename if path contains directories
        norm = os.path.basename(clean).strip()
        return norm

    def parse_includes(self, source_content: str, caller_filename: str) -> list[IncludeReference]:
        """Discovers all %INCLUDE directives in the provided SAS source content."""
        references = []
        seen = set()

        # Remove C-style /* ... */ comments before parsing
        code_no_comments = re.sub(r"/\*.*?\*/", "", source_content, flags=re.DOTALL)

        for match in self.INCLUDE_PATTERN.finditer(code_no_comments):
            raw_path = match.group(1) or match.group(2) or match.group(3)
            if not raw_path:
                continue

            norm_filename = self.normalize_include_path(raw_path)
            if not norm_filename:
                continue

            if norm_filename.lower() in seen:
                continue
            seen.add(norm_filename.lower())

            line_num = code_no_comments[:match.start()].count("\n") + 1
            ref = IncludeReference(
                caller_file=caller_filename,
                referenced_path=raw_path,
                normalized_filename=norm_filename,
                line_number=line_num
            )
            references.append(ref)

        return references
