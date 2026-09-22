"""
project_engine/r_project_zip.py
────────────────────────────────
ZIP exporter for modular RProject models.
Packaging layer only — hardened against path traversal attacks.
"""

from __future__ import annotations
import io
import zipfile
from pathlib import Path
from typing import Union
from .models import RProject


class RProjectZipExporter:
    """Packaging exporter for converting RProject instances to .zip archives."""

    def export(
        self,
        project: RProject,
        output_path: Union[str, Path]
    ) -> Path:
        """
        Exports the given RProject instance to a ZIP archive on disk.
        Returns absolute Path to the generated zip file.
        """
        out_path = Path(output_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        root_dir = (project.project_name or "converted_project").strip("/\\")
        if not root_dir:
            root_dir = "converted_project"

        with zipfile.ZipFile(out_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for rel_path, content in project.source_files.items():
                arcname = self._sanitize_arcname(root_dir, rel_path)
                zf.writestr(arcname, content.encode("utf-8"))

        return out_path

    def export_bytes(self, project: RProject) -> bytes:
        """
        Exports the given RProject instance to in-memory zip bytes.
        """
        buf = io.BytesIO()
        root_dir = (project.project_name or "converted_project").strip("/\\")
        if not root_dir:
            root_dir = "converted_project"

        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for rel_path, content in project.source_files.items():
                arcname = self._sanitize_arcname(root_dir, rel_path)
                zf.writestr(arcname, content.encode("utf-8"))

        return buf.getvalue()

    def _sanitize_arcname(self, root_dir: str, rel_path: str) -> str:
        """Sanitizes relative path to prevent directory traversal in ZIP entries."""
        cleaned = rel_path.lstrip("/\\")
        if ":" in cleaned:
            cleaned = cleaned.split(":", 1)[-1].lstrip("/\\")

        parts = [p for p in Path(cleaned).parts if p not in ("..", ".", "")]
        if not parts:
            parts = ["unnamed_file.R"]

        safe_rel = "/".join(parts)
        return f"{root_dir}/{safe_rel}"
