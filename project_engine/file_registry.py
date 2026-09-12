"""
project_engine/file_registry.py
────────────────────────────────
Project File Registry for registering and organizing uploaded SAS project files.
"""

from __future__ import annotations
import os
from project_engine.models import ProjectFile


class ProjectFileRegistry:
    """Manages uploaded project files, path normalization, and main/supporting classification."""

    def __init__(self) -> None:
        self._files: dict[str, ProjectFile] = {}
        self._main_key: str | None = None

    @staticmethod
    def normalize_key(filename: str) -> str:
        """Normalizes a filename/path for case-insensitive keying."""
        cleaned = os.path.basename(filename.strip())
        return cleaned.lower()

    def register_file(self, filename: str, content: str, is_main: bool = False) -> ProjectFile:
        """Registers a project file."""
        key = self.normalize_key(filename)
        ext = os.path.splitext(filename)[1].lstrip(".").lower() or "sas"

        pf = ProjectFile(
            filename=filename.strip(),
            normalized_path=key,
            file_type=ext,
            source_content=content,
            is_main=is_main
        )
        self._files[key] = pf

        if is_main or len(self._files) == 1:
            if not self._main_key or is_main:
                self.set_main_file(filename)

        return pf

    def set_main_file(self, filename: str) -> None:
        """Designates a file as the main SAS program."""
        target_key = self.normalize_key(filename)
        for key, pf in self._files.items():
            if key == target_key:
                pf.is_main = True
                self._main_key = key
            else:
                pf.is_main = False

    def get_file(self, filename: str) -> ProjectFile | None:
        """Retrieves a registered file by name."""
        return self._files.get(self.normalize_key(filename))

    def get_main_file(self) -> ProjectFile | None:
        """Returns the designated main program file."""
        if self._main_key and self._main_key in self._files:
            return self._files[self._main_key]
        return None

    def get_supporting_files(self) -> list[ProjectFile]:
        """Returns all non-main supporting files."""
        return [pf for key, pf in self._files.items() if not pf.is_main]

    def all_files(self) -> list[ProjectFile]:
        """Returns all registered project files."""
        return list(self._files.values())

    def __len__(self) -> int:
        return len(self._files)

    def to_dict(self) -> dict[str, ProjectFile]:
        return self._files.copy()
