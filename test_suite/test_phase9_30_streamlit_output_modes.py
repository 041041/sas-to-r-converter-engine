"""
test_phase9_30_streamlit_output_modes.py
──────────────────────────────────────────
Test suite for Phase 9.30 — Streamlit UI Integration & Output Modes.

Covers all 11 Phase 9.30 requirements:
 1. Default output mode is Single R File
 2. Existing single-file output still works
 3. Modular mode invokes RProjectAssembler
 4. Modular mode invokes RProjectZipExporter
 5. ZIP download data is non-empty
 6. ZIP contains main.R
 7. ZIP contains R/*.R
 8. ZIP does not contain test/scratch/repository files
 9. Existing R output remains unchanged
10. Clinical 3-macro project can generate both output modes
11. No conversion logic is duplicated in app.py
"""

import io
import os
import subprocess
import tempfile
import zipfile
import pytest

from macro_converter import parse_sas_source, HybridMacroConverter
from project_engine.output_handler import prepare_conversion_output, ConversionOutput
from project_engine.models import RProject
from project_engine.r_project_assembler import RProjectAssembler
from project_engine.r_project_zip import RProjectZipExporter


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


def get_clinical_conv_result():
    sas1, sas2, sas3 = get_clinical_macro_sources()
    combined_sas = sas3 + "\n\n" + sas2 + "\n\n" + sas1
    parsed = parse_sas_source(combined_sas)
    return HybridMacroConverter().convert_all(parsed['macro_definitions'], parsed['macro_calls'], 'Modern R (dplyr)')


def test_1_default_output_mode_is_single_r_file():
    conv_res = get_clinical_conv_result()
    out = prepare_conversion_output(conv_res)
    assert out.output_format == "Single R File"
    assert out.download_filename == "converted_pipeline.R"
    assert out.download_mime == "text/plain"


def test_2_existing_single_file_output_still_works():
    conv_res = get_clinical_conv_result()
    out = prepare_conversion_output(conv_res, output_format="Single R File")
    assert "util_chkvars <- function" in out.r_code_text
    assert "util_num_periods <- function" in out.r_code_text
    assert "gen_tp_join_adsl <- function" in out.r_code_text
    assert isinstance(out.download_bytes, bytes)
    assert out.download_bytes.decode("utf-8") == out.r_code_text


def test_3_modular_mode_invokes_r_project_assembler():
    conv_res = get_clinical_conv_result()
    out = prepare_conversion_output(conv_res, output_format="Modular R Project (.zip)")
    assert out.output_format == "Modular R Project (.zip)"
    assert isinstance(out.r_project, RProject)
    assert out.r_project.dependency_order == ["util_chkvars", "util_num_periods", "gen_tp_join_adsl"]


def test_4_modular_mode_invokes_r_project_zip_exporter():
    conv_res = get_clinical_conv_result()
    out = prepare_conversion_output(conv_res, output_format="Modular R Project (.zip)")
    assert isinstance(out.download_bytes, bytes)
    assert out.download_filename == "converted_project.zip"
    assert out.download_mime == "application/zip"


def test_5_zip_download_data_is_non_empty():
    conv_res = get_clinical_conv_result()
    out = prepare_conversion_output(conv_res, output_format="Modular R Project (.zip)")
    assert len(out.download_bytes) > 0


def test_6_zip_contains_main_r():
    conv_res = get_clinical_conv_result()
    out = prepare_conversion_output(conv_res, output_format="Modular R Project (.zip)")

    with zipfile.ZipFile(io.BytesIO(out.download_bytes)) as zf:
        names = zf.namelist()
        assert "converted_project/main.R" in names


def test_7_zip_contains_r_modules():
    conv_res = get_clinical_conv_result()
    out = prepare_conversion_output(conv_res, output_format="Modular R Project (.zip)")

    with zipfile.ZipFile(io.BytesIO(out.download_bytes)) as zf:
        names = zf.namelist()
        assert "converted_project/R/util_chkvars.R" in names
        assert "converted_project/R/util_num_periods.R" in names
        assert "converted_project/R/gen_tp_join_adsl.R" in names


def test_8_zip_does_not_contain_test_scratch_repo_files():
    conv_res = get_clinical_conv_result()
    out = prepare_conversion_output(conv_res, output_format="Modular R Project (.zip)")

    with zipfile.ZipFile(io.BytesIO(out.download_bytes)) as zf:
        for name in zf.namelist():
            assert not name.startswith("/"), f"Absolute path leakage: {name}"
            assert ".git" not in name
            assert "__pycache__" not in name
            assert "scratch/" not in name
            assert "test_suite/" not in name


def test_9_existing_r_output_remains_unchanged():
    conv_res = get_clinical_conv_result()
    single_out = prepare_conversion_output(conv_res, output_format="Single R File")
    raw_single_text = conv_res["r_functions"]
    if conv_res.get("r_calls", "").strip():
        raw_single_text += "\n\n" + conv_res["r_calls"].strip()

    assert single_out.r_code_text == raw_single_text


def test_10_clinical_3_macro_project_generates_both_output_modes():
    conv_res = get_clinical_conv_result()

    out_single = prepare_conversion_output(conv_res, output_format="Single R File")
    assert out_single.output_format == "Single R File"
    assert out_single.download_filename.endswith(".R")

    out_mod = prepare_conversion_output(conv_res, output_format="Modular R Project (.zip)")
    assert out_mod.output_format == "Modular R Project (.zip)"
    assert out_mod.download_filename.endswith(".zip")


def test_11_no_conversion_logic_duplicated_in_app():
    # Verify that prepare_conversion_output reuses RProjectAssembler and RProjectZipExporter
    assembler = RProjectAssembler()
    exporter = RProjectZipExporter()
    conv_res = get_clinical_conv_result()

    direct_proj = assembler.assemble(conv_res)
    direct_bytes = exporter.export_bytes(direct_proj)

    prep_out = prepare_conversion_output(conv_res, output_format="Modular R Project (.zip)")
    assert prep_out.download_bytes == direct_bytes


def test_12_modular_zip_execution_validation():
    conv_res = get_clinical_conv_result()
    out = prepare_conversion_output(conv_res, output_format="Modular R Project (.zip)")

    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "proj.zip")
        with open(zip_path, "wb") as f:
            f.write(out.download_bytes)

        extract_dir = os.path.join(tmpdir, "extracted")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)

        proj_dir = os.path.join(extract_dir, "converted_project")
        assert os.path.exists(proj_dir)

        # Rscript parse validation
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

        # Runtime execution against ADaM dataset
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
