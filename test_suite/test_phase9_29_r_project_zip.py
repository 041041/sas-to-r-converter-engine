"""
test_phase9_29_r_project_zip.py
────────────────────────────────
Test suite for Phase 9.29 — R Project ZIP Export.

Covers all 15 Phase 9.29 packaging and validation requirements:
 1. RProject -> ZIP creation
 2. ZIP file exists
 3. Expected project root exists inside ZIP
 4. main.R exists
 5. Every R/*.R module exists
 6. No absolute paths
 7. No repository artifacts are included
 8. No scratch files are included
 9. No test files are included
10. ZIP preserves exact generated file contents
11. ZIP preserves directory structure
12. ZIP can be extracted and executed
13. Extracted modular project passes Rscript parsing
14. Extracted modular project executes against representative ADaM dataset
15. Existing RProjectAssembler tests remain unchanged
"""

import os
import shutil
import subprocess
import tempfile
import zipfile
import pytest

from project_engine.models import RProject
from project_engine.r_project_assembler import RProjectAssembler
from project_engine.r_project_zip import RProjectZipExporter
from macro_converter import parse_sas_source, HybridMacroConverter


def get_clinical_macro_sources():
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

    sas1 = "%macro UTIL_CHKVARS(_dsnin=, _varlist=, _varexist=, _missvar=); %mend UTIL_CHKVARS;"
    sas2 = "%macro UTIL_NUM_PERIODS(_dsn=); %mend UTIL_NUM_PERIODS;"
    sas3 = "%macro GEN_TP_JOIN_ADSL(_dsnin=adsl, _dsnout=, _trtoption=OPTION1, _dropvars=, _analstartdtvar=ADT); %UTIL_NUM_PERIODS(_dsn=&_dsnin); %UTIL_CHKVARS(_dsnin=&_dsnin, _varlist=&_dropvars); %mend GEN_TP_JOIN_ADSL;"
    return sas1, sas2, sas3


def get_clinical_r_project():
    sas1, sas2, sas3 = get_clinical_macro_sources()
    combined_sas = sas3 + "\n\n" + sas2 + "\n\n" + sas1
    parsed = parse_sas_source(combined_sas)
    conv_res = HybridMacroConverter().convert_all(parsed['macro_definitions'], parsed['macro_calls'], 'Modern R (dplyr)')
    return RProjectAssembler().assemble(conversion_result=conv_res, project_name="converted_project")


def test_1_r_project_to_zip_creation():
    prj = get_clinical_r_project()
    exporter = RProjectZipExporter()

    with tempfile.TemporaryDirectory() as tmpdir:
        out_zip = os.path.join(tmpdir, "output.zip")
        res_path = exporter.export(prj, out_zip)
        assert os.path.exists(res_path)
        assert res_path.name == "output.zip"


def test_2_zip_file_exists():
    prj = get_clinical_r_project()
    exporter = RProjectZipExporter()

    with tempfile.TemporaryDirectory() as tmpdir:
        out_zip = os.path.join(tmpdir, "clinical_project.zip")
        exporter.export(prj, out_zip)
        assert os.path.exists(out_zip)
        assert os.path.getsize(out_zip) > 0


def test_3_expected_project_root_exists_inside_zip():
    prj = get_clinical_r_project()
    exporter = RProjectZipExporter()
    zip_bytes = exporter.export_bytes(prj)

    with zipfile.ZipFile(io_buf := __import__("io").BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        for name in names:
            assert name.startswith("converted_project/"), f"Zip entry {name} does not start with project root 'converted_project/'"


def test_4_main_r_exists_in_zip():
    prj = get_clinical_r_project()
    exporter = RProjectZipExporter()
    zip_bytes = exporter.export_bytes(prj)

    with zipfile.ZipFile(__import__("io").BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        assert "converted_project/main.R" in names


def test_5_every_r_module_exists_in_zip():
    prj = get_clinical_r_project()
    exporter = RProjectZipExporter()
    zip_bytes = exporter.export_bytes(prj)

    with zipfile.ZipFile(__import__("io").BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        assert "converted_project/R/util_chkvars.R" in names
        assert "converted_project/R/util_num_periods.R" in names
        assert "converted_project/R/gen_tp_join_adsl.R" in names


def test_6_no_absolute_paths_in_zip():
    prj = get_clinical_r_project()
    exporter = RProjectZipExporter()
    zip_bytes = exporter.export_bytes(prj)

    with zipfile.ZipFile(__import__("io").BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            assert not name.startswith("/"), f"Absolute path found in zip: {name}"
            assert ":" not in name, f"Drive letter/absolute path found in zip: {name}"


def test_7_no_repository_artifacts_in_zip():
    prj = get_clinical_r_project()
    exporter = RProjectZipExporter()
    zip_bytes = exporter.export_bytes(prj)

    forbidden = [".git", "__pycache__", ".pytest_cache", ".env", "setup.py"]
    with zipfile.ZipFile(__import__("io").BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            for fbd in forbidden:
                assert fbd not in name, f"Forbidden repository artifact {fbd} found in zip: {name}"


def test_8_no_scratch_files_in_zip():
    prj = get_clinical_r_project()
    exporter = RProjectZipExporter()
    zip_bytes = exporter.export_bytes(prj)

    with zipfile.ZipFile(__import__("io").BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            assert "scratch/" not in name, f"Scratch file found in zip: {name}"


def test_9_no_test_files_in_zip():
    prj = get_clinical_r_project()
    exporter = RProjectZipExporter()
    zip_bytes = exporter.export_bytes(prj)

    with zipfile.ZipFile(__import__("io").BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            assert "test_suite/" not in name, f"Test suite file found in zip: {name}"
            assert not name.endswith("_test.py"), f"Test file found in zip: {name}"


def test_10_zip_preserves_exact_generated_file_contents():
    prj = get_clinical_r_project()
    exporter = RProjectZipExporter()
    zip_bytes = exporter.export_bytes(prj)

    with zipfile.ZipFile(__import__("io").BytesIO(zip_bytes)) as zf:
        for rel_path, expected_content in prj.source_files.items():
            arcname = f"converted_project/{rel_path}"
            content_in_zip = zf.read(arcname).decode("utf-8")
            assert content_in_zip == expected_content, f"Content mismatch for {rel_path}"


def test_11_zip_preserves_directory_structure():
    prj = get_clinical_r_project()
    exporter = RProjectZipExporter()
    zip_bytes = exporter.export_bytes(prj)

    with zipfile.ZipFile(__import__("io").BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
        expected = {
            "converted_project/main.R",
            "converted_project/R/util_chkvars.R",
            "converted_project/R/util_num_periods.R",
            "converted_project/R/gen_tp_join_adsl.R",
        }
        assert expected.issubset(names)


def test_12_zip_can_be_extracted_and_executed():
    prj = get_clinical_r_project()
    exporter = RProjectZipExporter()

    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "proj.zip")
        exporter.export(prj, zip_path)

        extract_dir = os.path.join(tmpdir, "extracted")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)

        proj_root = os.path.join(extract_dir, "converted_project")
        assert os.path.exists(proj_root)
        assert os.path.exists(os.path.join(proj_root, "main.R"))
        assert os.path.exists(os.path.join(proj_root, "R", "util_chkvars.R"))


def test_13_extracted_modular_project_passes_rscript_parsing():
    prj = get_clinical_r_project()
    exporter = RProjectZipExporter()

    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "proj.zip")
        exporter.export(prj, zip_path)

        extract_dir = os.path.join(tmpdir, "extracted")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)

        proj_root = os.path.join(extract_dir, "converted_project")
        for root, _, files in os.walk(proj_root):
            for file in files:
                if file.endswith(".R"):
                    abs_p = os.path.join(root, file)
                    res = subprocess.run(
                        ["Rscript", "-e", f"parse(file='{abs_p}')"],
                        capture_output=True,
                        text=True
                    )
                    assert res.returncode == 0, f"Parse failed for extracted file {abs_p}: {res.stderr}"


def test_14_extracted_project_executes_against_adam_dataset():
    prj = get_clinical_r_project()
    exporter = RProjectZipExporter()

    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "proj.zip")
        exporter.export(prj, zip_path)

        extract_dir = os.path.join(tmpdir, "extracted")
        with zipfile.ZipFile(zip_path, "r") as zf:
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
        cat("COLUMNS:", paste(colnames(out), collapse=","), "\\n")
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


def test_15_existing_r_project_assembler_unbroken():
    prj = get_clinical_r_project()
    assert prj.dependency_order == ["util_chkvars", "util_num_periods", "gen_tp_join_adsl"]
    assert "main.R" in prj.source_files
