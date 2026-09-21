"""
project_engine/output_handler.py
─────────────────────────────────
Application-layer output preparation helper for Single R File vs. Modular R Project ZIP.
Provides clean separation between conversion, output packaging, and UI rendering.
Hardened for invalid or non-dict inputs.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional
from project_engine.models import RProject
from project_engine.r_project_assembler import RProjectAssembler
from project_engine.r_project_zip import RProjectZipExporter


@dataclass
class ConversionOutput:
    """Encapsulates prepared output for display and download in Streamlit or API callers."""
    output_format: str  # "Single R File" | "Modular R Project (.zip)"
    r_code_text: str    # R source string for text display
    download_bytes: bytes
    download_filename: str
    download_mime: str
    r_project: Optional[RProject] = None


def prepare_conversion_output(
    conversion_result: Optional[dict[str, Any]],
    output_format: str = "Single R File",
    project_name: str = "converted_project",
    single_filename: str = "converted_pipeline.R"
) -> ConversionOutput:
    """
    Transforms a raw conversion_result dictionary into a ConversionOutput object.
    Supports both 'Single R File' and 'Modular R Project (.zip)' modes.
    Safely handles None, non-dict, or empty inputs.
    """
    if not isinstance(conversion_result, dict):
        conversion_result = {}

    r_func_text = conversion_result.get("r_functions", "") or ""
    r_calls_text = conversion_result.get("r_calls", "") or ""
    full_single_text = r_func_text
    if r_calls_text and r_calls_text.strip():
        if full_single_text:
            full_single_text += "\n\n" + r_calls_text.strip()
        else:
            full_single_text = r_calls_text.strip()

    if output_format == "Modular R Project (.zip)":
        assembler = RProjectAssembler()
        project = assembler.assemble(
            conversion_result=conversion_result,
            project_name=project_name
        )
        exporter = RProjectZipExporter()
        zip_bytes = exporter.export_bytes(project)

        display_text = project.source_files.get("main.R", full_single_text)

        return ConversionOutput(
            output_format="Modular R Project (.zip)",
            r_code_text=display_text,
            download_bytes=zip_bytes,
            download_filename=f"{project_name}.zip",
            download_mime="application/zip",
            r_project=project
        )

    # Default: Single R File
    single_bytes = full_single_text.encode("utf-8")
    return ConversionOutput(
        output_format="Single R File",
        r_code_text=full_single_text,
        download_bytes=single_bytes,
        download_filename=single_filename,
        download_mime="text/plain",
        r_project=None
    )
