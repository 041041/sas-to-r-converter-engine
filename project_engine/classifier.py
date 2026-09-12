"""
project_engine/classifier.py
──────────────────────────────
Program Classifier for identifying SAS source category:
EXECUTABLE_PROGRAM, MACRO_LIBRARY, MIXED_PROGRAM, or INVALID_SOURCE.
"""

from __future__ import annotations
import re
from enum import Enum
from project_engine.dependency_parser import DependencyParser


class ProgramType(str, Enum):
    EXECUTABLE_PROGRAM = "Executable Program"
    MACRO_LIBRARY = "Macro Library"
    MIXED_PROGRAM = "Mixed Program"
    SUPPORTING_FILE = "Supporting File"
    INVALID_SOURCE = "Invalid Source"


class ProgramClassifier:
    """Classifies SAS source code into program type categories."""

    EXEC_STEP_PATTERN = re.compile(
        r"(?:^\s*data\s+|^\s*proc\s+|%\b(?!(?:macro|mend|let|put|include|if|then|else|do|end)\b)[a-zA-Z_]\w*\b)",
        re.IGNORECASE | re.MULTILINE
    )
    MACRO_DEF_PATTERN = re.compile(r"%macro\s+[a-zA-Z_]\w*", re.IGNORECASE)

    def classify_source(self, sas_code: str) -> ProgramType:
        """Classifies raw SAS source text."""
        if not sas_code or not sas_code.strip():
            return ProgramType.INVALID_SOURCE

        clean_code = DependencyParser.strip_comments(sas_code)
        if not clean_code.strip():
            return ProgramType.INVALID_SOURCE

        has_macro_defs = bool(self.MACRO_DEF_PATTERN.search(clean_code))
        outer_code = DependencyParser.strip_macro_definitions(clean_code)
        has_exec_steps = bool(self.EXEC_STEP_PATTERN.search(outer_code))

        if has_macro_defs and has_exec_steps:
            return ProgramType.MIXED_PROGRAM
        elif has_macro_defs and not has_exec_steps:
            return ProgramType.MACRO_LIBRARY
        elif not has_macro_defs and has_exec_steps:
            return ProgramType.EXECUTABLE_PROGRAM
        else:
            if re.search(r"[\w;]", clean_code):
                return ProgramType.MACRO_LIBRARY if has_macro_defs else ProgramType.EXECUTABLE_PROGRAM
            return ProgramType.INVALID_SOURCE
