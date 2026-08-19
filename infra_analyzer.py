"""
infra_analyzer.py
──────────────────
Infrastructure & Environment Analyzer for Enterprise SAS Modernization Engine.
Translates SAS LIBNAME, FILENAME, %INCLUDE, OPTIONS, and TITLE/FOOTNOTE statements
into structured R data-source configurations and environment setup scripts.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from sas_ast import InfraIR


@dataclass
class InfraRConfig:
    r_config_code: str
    lib_mappings: dict[str, str] = field(default_factory=dict)
    file_mappings: dict[str, str] = field(default_factory=dict)
    manual_review_items: list[str] = field(default_factory=list)


class InfrastructureAnalyzer:
    """
    Analyzes InfraIR and produces R environment configurations.
    """

    def analyze(self, infra: InfraIR) -> InfraRConfig:
        config_lines = ["# ── SAS Environment & Infrastructure Setup ──"]
        lib_map = {}
        file_map = {}
        manual_items = list(infra.review_items)

        # 1. LIBNAME Translation
        for libref, path_or_conn in infra.libnames.items():
            lib_var = f"lib_{libref.lower()}"
            if "odbc" in path_or_conn.lower() or "oracle" in path_or_conn.lower() or "postgres" in path_or_conn.lower():
                config_lines.append(f"# WARNING: Database LIBNAME '{libref}' requires DBI/odbc credentials setup.")
                config_lines.append(f"{lib_var} <- NULL  # TODO: Configure DBI::dbConnect(...)")
                lib_map[libref] = f"{lib_var}"
            else:
                config_lines.append(f'{lib_var} <- "{path_or_conn}"')
                lib_map[libref] = f"{lib_var}"

        # 2. FILENAME Translation
        for fileref, path in infra.filenames.items():
            file_var = f"file_{fileref.lower()}"
            config_lines.append(f'{file_var} <- "{path}"')
            file_map[fileref] = f"{file_var}"

        # 3. OPTIONS Translation
        if infra.options:
            config_lines.append("# R Global Options")
            config_lines.append("options(stringsAsFactors = FALSE, check.names = FALSE)")

        # 4. %INCLUDE Directives
        for inc in infra.includes:
            if inc.endswith(".sas"):
                r_inc = inc[:-4] + ".R"
                config_lines.append(f'# %INCLUDE translation:\nif (file.exists("{r_inc}")) source("{r_inc}")')
            else:
                config_lines.append(f'# %INCLUDE: source("{inc}")')

        # 5. Titles & Footnotes
        for tf in infra.titles_footnotes:
            config_lines.append(f'# {tf}')

        r_code = "\n".join(config_lines)
        return InfraRConfig(
            r_config_code=r_code,
            lib_mappings=lib_map,
            file_mappings=file_map,
            manual_review_items=manual_items
        )
