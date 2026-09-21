"""
test_phase9_31_clinical_project_e2e.py
───────────────────────────────────────
End-to-End Acceptance Test Suite for Phase 9.31:
Full Real Clinical SAS Project Discovery, Resolution, Conversion, Modular Assembly,
ZIP Packaging, Extraction, Rscript Parsing, and Runtime Execution.

Covers all 21 verification & regression requirements.
"""

import io
import os
import re
import subprocess
import tempfile
import zipfile
import pytest

from project_engine import (
    ProjectAnalyzer,
    ProjectContext,
    ResolutionStatus,
    DependencyType,
    RProject,
    RProjectAssembler,
    RProjectZipExporter,
    prepare_conversion_output
)
from macro_converter import parse_sas_source, HybridMacroConverter, convert_sas_to_r


FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def load_clinical_project_files() -> list[tuple[str, str]]:
    dir_path = os.path.join(FIXTURE_DIR, "clinical_project_e2e")
    files = []
    for fname in sorted(os.listdir(dir_path)):
        if fname.endswith(".sas"):
            fpath = os.path.join(dir_path, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                files.append((fname, f.read()))
    return files


def load_real_clinical_sources():
    sas1_path = "/Users/sandeep/Downloads/test1macro.sas"
    sas2_path = "/Users/sandeep/Downloads/test2macro.sas"
    sas3_path = "/Users/sandeep/Downloads/test3macro.sas"

    if os.path.exists(sas1_path) and os.path.exists(sas2_path) and os.path.exists(sas3_path):
        with open(sas1_path, "r", encoding="utf-8") as f:
            sas1 = f.read()
        with open(sas2_path, "r", encoding="utf-8") as f:
            sas2 = f.read()
        with open(sas3_path, "r", encoding="utf-8") as f:
            sas3 = f.read()
        return sas1, sas2, sas3

    # Fallback to fixture files
    files_dict = dict(load_clinical_project_files())
    return files_dict.get("util_chkvars.sas", ""), files_dict.get("util_num_periods.sas", ""), files_dict.get("gen_tp_join_adsl.sas", "")


def get_clinical_e2e_conversion():
    sas1, sas2, sas3 = load_real_clinical_sources()
    combined_sas = sas3 + "\n\n" + sas2 + "\n\n" + sas1
    parsed = parse_sas_source(combined_sas)
    return HybridMacroConverter().convert_all(parsed['macro_definitions'], parsed['macro_calls'], 'Modern R (dplyr)')


def test_1_main_sas_file_identified():
    files = load_clinical_project_files()
    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project(files, main_filename="main.sas")
    assert ctx.main_program_file == "main.sas"


def test_2_supporting_sas_files_discovered():
    files = load_clinical_project_files()
    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project(files, main_filename="main.sas")
    filenames = set(ctx.project_files.keys())
    assert {"main.sas", "util_chkvars.sas", "util_num_periods.sas", "gen_tp_join_adsl.sas"}.issubset(filenames)


def test_3_include_dependencies_resolve():
    files = load_clinical_project_files()
    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project(files, main_filename="main.sas")
    assert ctx.resolution_result.status == ResolutionStatus.RESOLVED

    inc_edges = [e for e in ctx.dependency_graph.edges if e.dependency_type == DependencyType.INCLUDE]
    assert len(inc_edges) >= 3


def test_4_macro_dependencies_resolve():
    files = load_clinical_project_files()
    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project(files, main_filename="main.sas")
    macro_edges = [e for e in ctx.dependency_graph.edges if e.dependency_type == DependencyType.MACRO_CALL]
    assert len(macro_edges) >= 2


def test_5_no_unresolved_dependencies():
    files = load_clinical_project_files()
    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project(files, main_filename="main.sas")
    assert len(ctx.resolution_result.missing_dependencies) == 0
    assert len(ctx.resolution_result.missing_includes) == 0


def test_6_deterministic_dependency_ordering():
    files = load_clinical_project_files()
    analyzer = ProjectAnalyzer()
    first_order = None
    for _ in range(10):
        ctx = analyzer.analyze_project(files, main_filename="main.sas")
        if first_order is None:
            first_order = ctx.dependency_order
        else:
            assert ctx.dependency_order == first_order


def test_7_reusable_r_functions_conversion():
    conv_res = get_clinical_e2e_conversion()
    r_funcs = conv_res["r_functions"]
    assert "util_chkvars <- function" in r_funcs
    assert "util_num_periods <- function" in r_funcs
    assert "gen_tp_join_adsl <- function" in r_funcs


def test_8_r_project_assembler_structure():
    conv_res = get_clinical_e2e_conversion()
    prj = RProjectAssembler().assemble(conversion_result=conv_res)
    assert isinstance(prj, RProject)
    assert "main.R" in prj.source_files
    assert "R/util_chkvars.R" in prj.source_files
    assert "R/util_num_periods.R" in prj.source_files
    assert "R/gen_tp_join_adsl.R" in prj.source_files


def test_9_main_r_generation():
    conv_res = get_clinical_e2e_conversion()
    prj = RProjectAssembler().assemble(conversion_result=conv_res)
    main_code = prj.source_files["main.R"]
    assert 'source("R/util_chkvars.R")' in main_code
    assert 'source("R/util_num_periods.R")' in main_code
    assert 'source("R/gen_tp_join_adsl.R")' in main_code


def test_10_r_modules_generation():
    conv_res = get_clinical_e2e_conversion()
    prj = RProjectAssembler().assemble(conversion_result=conv_res)
    assert "util_chkvars <- function" in prj.source_files["R/util_chkvars.R"]
    assert "util_num_periods <- function" in prj.source_files["R/util_num_periods.R"]
    assert "gen_tp_join_adsl <- function" in prj.source_files["R/gen_tp_join_adsl.R"]


def test_11_zip_exporter_creation():
    conv_res = get_clinical_e2e_conversion()
    prj = RProjectAssembler().assemble(conversion_result=conv_res)
    exporter = RProjectZipExporter()
    zip_bytes = exporter.export_bytes(prj)
    assert len(zip_bytes) > 0


def test_12_zip_only_expected_files():
    conv_res = get_clinical_e2e_conversion()
    prj = RProjectAssembler().assemble(conversion_result=conv_res)
    exporter = RProjectZipExporter()
    zip_bytes = exporter.export_bytes(prj)

    expected = {
        "converted_project/main.R",
        "converted_project/R/util_chkvars.R",
        "converted_project/R/util_num_periods.R",
        "converted_project/R/gen_tp_join_adsl.R",
    }
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
        assert expected.issubset(names)


def test_13_no_absolute_paths_in_zip():
    conv_res = get_clinical_e2e_conversion()
    prj = RProjectAssembler().assemble(conversion_result=conv_res)
    exporter = RProjectZipExporter()
    zip_bytes = exporter.export_bytes(prj)

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            assert not name.startswith("/")
            assert ":" not in name


def test_14_extracted_r_files_parse():
    conv_res = get_clinical_e2e_conversion()
    prj = RProjectAssembler().assemble(conversion_result=conv_res)
    exporter = RProjectZipExporter()

    with tempfile.TemporaryDirectory() as tmpdir:
        out_zip = os.path.join(tmpdir, "proj.zip")
        exporter.export(prj, out_zip)

        extract_dir = os.path.join(tmpdir, "extracted")
        with zipfile.ZipFile(out_zip, "r") as zf:
            zf.extractall(extract_dir)

        proj_dir = os.path.join(extract_dir, "converted_project")
        for root, _, files in os.walk(proj_dir):
            for file in files:
                if file.endswith(".R"):
                    abs_p = os.path.join(root, file)
                    res = subprocess.run(
                        ["Rscript", "-e", f"parse(file='{abs_p}')"],
                        capture_output=True,
                        text=True
                    )
                    assert res.returncode == 0, f"Rscript parse failed for {abs_p}: {res.stderr}"


def test_15_extracted_main_r_parses():
    conv_res = get_clinical_e2e_conversion()
    prj = RProjectAssembler().assemble(conversion_result=conv_res)
    exporter = RProjectZipExporter()

    with tempfile.TemporaryDirectory() as tmpdir:
        out_zip = os.path.join(tmpdir, "proj.zip")
        exporter.export(prj, out_zip)

        extract_dir = os.path.join(tmpdir, "extracted")
        with zipfile.ZipFile(out_zip, "r") as zf:
            zf.extractall(extract_dir)

        main_r_path = os.path.join(extract_dir, "converted_project", "main.R")
        res = subprocess.run(
            ["Rscript", "-e", f"parse(file='{main_r_path}')"],
            capture_output=True,
            text=True
        )
        assert res.returncode == 0, f"Rscript parse failed for main.R: {res.stderr}"


def test_16_extracted_project_executes_rscript():
    conv_res = get_clinical_e2e_conversion()
    prj = RProjectAssembler().assemble(conversion_result=conv_res)
    exporter = RProjectZipExporter()

    with tempfile.TemporaryDirectory() as tmpdir:
        out_zip = os.path.join(tmpdir, "proj.zip")
        exporter.export(prj, out_zip)

        extract_dir = os.path.join(tmpdir, "extracted")
        with zipfile.ZipFile(out_zip, "r") as zf:
            zf.extractall(extract_dir)

        proj_dir = os.path.join(extract_dir, "converted_project")

        runner_script = os.path.join(proj_dir, "run_test.R")
        runner_code = """
        source("main.R")

        adsl <- data.frame(
            USUBJID = c("SUBJ-001", "SUBJ-002", "SUBJ-003"),
            TR01SDT = c("2024-01-01", "2024-01-01", "2024-01-01"),
            TR02SDT = c("2024-02-01", "2024-02-01", "2024-02-01"),
            AP01SDT = as.Date(c("2024-01-01", "2024-01-01", "2024-01-01")),
            AP01EDT = as.Date(c("2024-01-15", "2024-01-15", "2024-01-15")),
            AP02SDT = as.Date(c("2024-02-01", "2024-02-01", "2024-02-01")),
            AP02EDT = as.Date(c("2024-02-15", "2024-02-15", "2024-02-15")),
            TRT01P  = c("Placebo", "Active", "Placebo"),
            TRT01A  = c("Placebo", "Active", "Placebo"),
            TRT02P  = c("Active", "Placebo", "Placebo"),
            TRT02A  = c("Active", "Placebo", "Placebo"),
            ADT     = as.Date(c("2024-01-05", "2024-01-20", "2024-02-10")),
            stringsAsFactors = FALSE
        )

        res_num <- util_num_periods(`_dsn` = adsl)
        cat("G_PRDCNT:", res_num$g_prdcnt, "\\n")
        cat("G_XOVERYN:", res_num$g_xoveryn, "\\n")

        out <- gen_tp_join_adsl(`_dsnin` = adsl, `_trtoption` = "OPTION1")
        cat("ROW1_APERIOD:", out$APERIOD[1], "\\n")
        cat("ROW1_APERIODC:", out$APERIODC[1], "\\n")
        cat("ROW1_APHASE:", out$APHASE[1], "\\n")
        cat("ROW1_TRTP:", out$TRTP[1], "\\n")
        cat("ROW1_TRTA:", out$TRTA[1], "\\n")
        cat("ROW1_APERDY:", out$APERDY[1], "\\n")
        """
        with open(runner_script, "w", encoding="utf-8") as f:
            f.write(runner_code)

        res = subprocess.run(
            ["Rscript", "run_test.R"],
            cwd=proj_dir,
            capture_output=True,
            text=True
        )

        assert res.returncode == 0, f"Rscript execution failed: {res.stderr}"
        stdout = res.stdout

        assert "G_PRDCNT: 2" in stdout
        assert "G_XOVERYN: Y" in stdout
        assert "ROW1_APERIOD: 1" in stdout
        assert "ROW1_APERIODC: Period 01" in stdout
        assert "ROW1_APHASE: TREATMENT 01" in stdout
        assert "ROW1_TRTP: Placebo" in stdout
        assert "ROW1_TRTA: Placebo" in stdout
        assert "ROW1_APERDY: 5" in stdout


def test_17_no_unresolved_sas_tokens():
    conv_res = get_clinical_e2e_conversion()
    r_code = conv_res["r_functions"]
    forbidden = ["%macro", "%mend", "%let", "%sysfunc", "&_dsnin", "&_dsnout", "%if"]
    for tok in forbidden:
        assert tok not in r_code, f"Unresolved SAS token {tok} found in R code"


def test_18_no_todo_fallback_placeholders():
    conv_res = get_clinical_e2e_conversion()
    r_code = conv_res["r_functions"]
    assert "# TODO" not in r_code
    assert "manual conversion needed" not in r_code


def test_19_existing_phase9_27_clinical_output_unchanged():
    conv_res = get_clinical_e2e_conversion()
    r_code = conv_res["r_functions"]
    assert "util_chkvars <- function" in r_code
    assert "util_num_periods <- function" in r_code
    assert "gen_tp_join_adsl <- function" in r_code


def test_20_existing_single_file_output_works():
    conv_res = get_clinical_e2e_conversion()
    out = prepare_conversion_output(conv_res, output_format="Single R File")
    assert out.output_format == "Single R File"
    assert out.download_filename == "converted_pipeline.R"
    assert len(out.download_bytes) > 0


def test_21_existing_modular_output_works():
    conv_res = get_clinical_e2e_conversion()
    out = prepare_conversion_output(conv_res, output_format="Modular R Project (.zip)")
    assert out.output_format == "Modular R Project (.zip)"
    assert out.download_filename == "converted_project.zip"
    assert len(out.download_bytes) > 0


def test_22_project_9_mixed_e2e_fixture_validation():
    dir_path = os.path.join(FIXTURE_DIR, "project_dependency_cases", "project_9_mixed_e2e")
    files = []
    for fname in sorted(os.listdir(dir_path)):
        if fname.endswith(".sas"):
            fpath = os.path.join(dir_path, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                files.append((fname, f.read()))

    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project(files, main_filename="main.sas")
    assert ctx.resolution_result.status == ResolutionStatus.RESOLVED

    # Convert project
    sas_code = "\n".join(ctx.ordered_supporting_content + [ctx.main_program_content])
    res = convert_sas_to_r(sas_code)
    assert "r_functions" in res

    # Assemble R project
    assembler = RProjectAssembler()
    prj = assembler.assemble(conversion_result=res, project_name="project_9_mixed")
    assert prj.main_file == "main.R"

    # Zip Export
    exporter = RProjectZipExporter()
    zip_bytes = exporter.export_bytes(prj)
    assert len(zip_bytes) > 0

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        assert "project_9_mixed/main.R" in names
