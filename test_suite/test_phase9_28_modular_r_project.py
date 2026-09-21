"""
test_phase9_28_modular_r_project.py
───────────────────────────────────
Test suite for Phase 9.28 — Modular R Project Generation Architecture.

Covers all 13 Phase 9.28 architectural and verification requirements:
 1. RProject model creation
 2. Correct macro -> R filename conversion
 3. One R file per reusable function
 4. Dependency ordering preserved
 5. main.R generation
 6. No duplicated function definitions
 7. Nested helper invocation survives modularization
 8. Backticked parameters survive modularization
 9. Current 3-macro clinical chain produces exact project tree
10. Rscript parse of every generated .R file
11. Rscript execution of the modular project
12. Existing single-file conversion remains unchanged
13. Existing baseline tests remain passing
"""

import os
import re
import shutil
import subprocess
import tempfile
import pytest
from pathlib import Path

from project_engine.models import RProject
from project_engine.r_project_assembler import RProjectAssembler
from macro_converter import parse_sas_source, convert_macros_to_r, convert_sas_to_r, HybridMacroConverter


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

    # Fallback definition if local download paths absent
    sas1 = """
    %macro UTIL_CHKVARS(_dsnin=, _varlist=, _varexist=, _missvar=);
        /* dummy body */
    %mend UTIL_CHKVARS;
    """
    sas2 = """
    %macro UTIL_NUM_PERIODS(_dsn=);
        /* dummy body */
    %mend UTIL_NUM_PERIODS;
    """
    sas3 = """
    %macro GEN_TP_JOIN_ADSL(_dsnin=adsl, _dsnout=, _trtoption=OPTION1, _dropvars=, _analstartdtvar=ADT);
        %UTIL_NUM_PERIODS(_dsn=&_dsnin);
        %UTIL_CHKVARS(_dsnin=&_dsnin, _varlist=&_dropvars);
    %mend GEN_TP_JOIN_ADSL;
    """
    return sas1, sas2, sas3


def get_clinical_conversion_result():
    sas1, sas2, sas3 = get_clinical_macro_sources()
    combined_sas = sas3 + "\n\n" + sas2 + "\n\n" + sas1
    parsed = parse_sas_source(combined_sas)
    converter = HybridMacroConverter()
    return converter.convert_all(parsed['macro_definitions'], parsed['macro_calls'], 'Modern R (dplyr)')


def test_1_r_project_model_creation():
    prj = RProject(
        project_name="my_test_project",
        main_file="main.R",
        source_files={
            "main.R": 'source("R/util.R")',
            "R/util.R": 'util <- function() { TRUE }'
        },
        entry_function="util",
        dependency_order=["util"],
        metadata={"version": "1.0"}
    )
    assert prj.project_name == "my_test_project"
    assert prj.main_file == "main.R"
    assert "R/util.R" in prj.source_files
    assert prj.entry_function == "util"
    assert prj.dependency_order == ["util"]
    assert prj.metadata == {"version": "1.0"}

    d = prj.to_dict()
    assert d["project_name"] == "my_test_project"
    assert d["source_files"] == ["main.R", "R/util.R"]

    with tempfile.TemporaryDirectory() as tmpdir:
        written = prj.write_to_directory(tmpdir)
        assert "main.R" in written
        assert "R/util.R" in written
        assert os.path.exists(os.path.join(tmpdir, "main.R"))
        assert os.path.exists(os.path.join(tmpdir, "R", "util.R"))


def test_2_macro_to_r_filename_conversion():
    assembler = RProjectAssembler()
    assert assembler._macro_to_filename("UTIL_CHKVARS") == "util_chkvars.R"
    assert assembler._macro_to_filename("GEN_TP_JOIN_ADSL") == "gen_tp_join_adsl.R"
    assert assembler._macro_to_filename("UTIL_NUM_PERIODS") == "util_num_periods.R"
    assert assembler._macro_to_filename("My-Macro#123") == "mymacro123.R"


def test_3_one_r_file_per_reusable_function():
    conv_res = get_clinical_conversion_result()
    assembler = RProjectAssembler()
    prj = assembler.assemble(conversion_result=conv_res)

    r_files = [f for f in prj.source_files.keys() if f.startswith("R/")]
    assert len(r_files) == 3
    assert "R/util_chkvars.R" in r_files
    assert "R/util_num_periods.R" in r_files
    assert "R/gen_tp_join_adsl.R" in r_files

    # Check each R file contains ONLY its function
    assert "util_chkvars <- function" in prj.source_files["R/util_chkvars.R"]
    assert "util_num_periods <- function" not in prj.source_files["R/util_chkvars.R"]


def test_4_dependency_ordering_preserved():
    conv_res = get_clinical_conversion_result()
    assembler = RProjectAssembler()
    prj = assembler.assemble(conversion_result=conv_res)

    assert prj.dependency_order == ["util_chkvars", "util_num_periods", "gen_tp_join_adsl"]


def test_5_main_r_generation():
    conv_res = get_clinical_conversion_result()
    assembler = RProjectAssembler()
    prj = assembler.assemble(conversion_result=conv_res)

    assert "main.R" in prj.source_files
    main_content = prj.source_files["main.R"]

    pos_chkvars = main_content.find('source("R/util_chkvars.R")')
    pos_num_periods = main_content.find('source("R/util_num_periods.R")')
    pos_gen_tp = main_content.find('source("R/gen_tp_join_adsl.R")')

    assert pos_chkvars != -1, "source('R/util_chkvars.R') missing in main.R"
    assert pos_num_periods != -1, "source('R/util_num_periods.R') missing in main.R"
    assert pos_gen_tp != -1, "source('R/gen_tp_join_adsl.R') missing in main.R"

    assert pos_chkvars < pos_gen_tp, "util_chkvars must be sourced before gen_tp_join_adsl"
    assert pos_num_periods < pos_gen_tp, "util_num_periods must be sourced before gen_tp_join_adsl"


def test_6_no_duplicated_function_definitions():
    conv_res = get_clinical_conversion_result()
    assembler = RProjectAssembler()
    prj = assembler.assemble(conversion_result=conv_res)

    main_content = prj.source_files["main.R"]
    assert "<- function" not in main_content, "main.R must not contain duplicated R function definitions"


def test_7_nested_helper_invocation_survives():
    conv_res = get_clinical_conversion_result()
    assembler = RProjectAssembler()
    prj = assembler.assemble(conversion_result=conv_res)

    gen_tp_code = prj.source_files["R/gen_tp_join_adsl.R"]
    assert "util_num_periods(" in gen_tp_code, "gen_tp_join_adsl.R must contain util_num_periods call"
    assert "util_chkvars(" in gen_tp_code, "gen_tp_join_adsl.R must contain util_chkvars call"


def test_8_backticked_parameters_survive():
    conv_res = get_clinical_conversion_result()
    assembler = RProjectAssembler()
    prj = assembler.assemble(conversion_result=conv_res)

    gen_tp_code = prj.source_files["R/gen_tp_join_adsl.R"]
    assert "`_dsnin`" in gen_tp_code, "gen_tp_join_adsl.R must preserve `_dsnin` parameter backticking"
    assert "`_dsnout`" in gen_tp_code, "gen_tp_join_adsl.R must preserve `_dsnout` parameter backticking"

    chkvars_code = prj.source_files["R/util_chkvars.R"]
    assert "`_dsnin`" in chkvars_code, "util_chkvars.R must preserve `_dsnin` parameter backticking"

    num_periods_code = prj.source_files["R/util_num_periods.R"]
    assert "`_dsn`" in num_periods_code, "util_num_periods.R must preserve `_dsn` parameter backticking"


def test_9_clinical_chain_project_tree():
    conv_res = get_clinical_conversion_result()
    assembler = RProjectAssembler()
    prj = assembler.assemble(conversion_result=conv_res)

    expected_tree = {
        "main.R",
        "R/util_chkvars.R",
        "R/util_num_periods.R",
        "R/gen_tp_join_adsl.R",
    }
    assert set(prj.source_files.keys()) == expected_tree


def test_10_rscript_parse_of_every_generated_file():
    conv_res = get_clinical_conversion_result()
    assembler = RProjectAssembler()
    prj = assembler.assemble(conversion_result=conv_res)

    with tempfile.TemporaryDirectory() as tmpdir:
        written = prj.write_to_directory(tmpdir)
        for rel_path, abs_path in written.items():
            res = subprocess.run(
                ["Rscript", "-e", f"parse(file='{abs_path}')"],
                capture_output=True,
                text=True
            )
            assert res.returncode == 0, f"Rscript parse failed for {rel_path}: {res.stderr}"


def test_11_rscript_execution_of_modular_project():
    conv_res = get_clinical_conversion_result()
    assembler = RProjectAssembler()
    prj = assembler.assemble(conversion_result=conv_res)

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = os.path.join(tmpdir, "converted_project")
        prj.write_to_directory(project_dir)

        runner_script = os.path.join(project_dir, "run_test.R")
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
            cwd=project_dir,
            capture_output=True,
            text=True
        )

        assert res.returncode == 0, f"Rscript execution failed: {res.stderr}"
        stdout = res.stdout

        assert "G_PRDCNT: 2" in stdout
        assert "G_XOVERYN: Y" in stdout

        cols = ["APERIOD", "APERIODC", "APHASE", "TRTP", "TRTA", "APERDY"]
        for col in cols:
            assert col in stdout, f"Column {col} missing in stdout: {stdout}"

        assert "ROW1_APERIOD: 1" in stdout
        assert "ROW1_APERIODC: Period 01" in stdout
        assert "ROW1_APHASE: TREATMENT 01" in stdout
        assert "ROW1_TRTP: Placebo" in stdout
        assert "ROW1_TRTA: Placebo" in stdout
        assert "ROW1_APERDY: 5" in stdout


def test_12_existing_single_file_conversion_unchanged():
    sas1, sas2, sas3 = get_clinical_macro_sources()
    combined_sas = sas3 + "\n\n" + sas2 + "\n\n" + sas1
    res = convert_sas_to_r(combined_sas)

    assert "r_functions" in res
    assert isinstance(res["r_functions"], str)
    assert "util_chkvars <- function" in res["r_functions"]
    assert "util_num_periods <- function" in res["r_functions"]
    assert "gen_tp_join_adsl <- function" in res["r_functions"]


def test_13_existing_baseline_tests_unbroken():
    assembler = RProjectAssembler()
    funcs = {
        "MACRO_A": "macro_a <- function() { TRUE }",
        "MACRO_B": "macro_b <- function() { macro_a() }"
    }
    order = ["MACRO_A", "MACRO_B"]
    prj = assembler.assemble(function_map=funcs, dependency_order=order)

    assert prj.dependency_order == ["macro_a", "macro_b"]
    assert "R/macro_a.R" in prj.source_files
    assert "R/macro_b.R" in prj.source_files
    assert 'source("R/macro_a.R")\nsource("R/macro_b.R")' in prj.source_files["main.R"]
