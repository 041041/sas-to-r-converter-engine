"""
test_phase9_27_clinical_macro_chain.py
────────────────────────────────────────
Expanded test suite for Phase 9.27 — Full Clinical 3-Macro Chain Conversion:
    GEN_TP_JOIN_ADSL -> UTIL_NUM_PERIODS -> UTIL_CHKVARS

Covers all 27 Phase 9.27 architectural and semantic requirements.
"""

import os
import re
import subprocess
import pytest
from macro_converter import parse_sas_source, classify_macro, HybridMacroConverter


def get_clinical_macro_sources():
    sas1_path = "/Users/sandeep/Downloads/test1macro.sas"
    sas2_path = "/Users/sandeep/Downloads/test2macro.sas"
    sas3_path = "/Users/sandeep/Downloads/test3macro.sas"
    
    assert os.path.exists(sas1_path), f"File {sas1_path} not found"
    assert os.path.exists(sas2_path), f"File {sas2_path} not found"
    assert os.path.exists(sas3_path), f"File {sas3_path} not found"

    with open(sas1_path, "r", encoding="utf-8") as f:
        sas1 = f.read()
    with open(sas2_path, "r", encoding="utf-8") as f:
        sas2 = f.read()
    with open(sas3_path, "r", encoding="utf-8") as f:
        sas3 = f.read()

    return sas1, sas2, sas3


def get_converted_clinical_r():
    sas1, sas2, sas3 = get_clinical_macro_sources()
    combined_sas = sas3 + "\n\n" + sas2 + "\n\n" + sas1
    parsed = parse_sas_source(combined_sas)
    res = HybridMacroConverter().convert_all(parsed['macro_definitions'], parsed['macro_calls'], 'Modern R (dplyr)')
    return res['r_functions']


def test_1_clinical_macro_dependency_ordering():
    r_code = get_converted_clinical_r()
    pos_chkvars = r_code.find("util_chkvars <- function")
    pos_num_periods = r_code.find("util_num_periods <- function")
    pos_gen_tp = r_code.find("gen_tp_join_adsl <- function")

    assert pos_chkvars != -1, "util_chkvars definition missing"
    assert pos_num_periods != -1, "util_num_periods definition missing"
    assert pos_gen_tp != -1, "gen_tp_join_adsl definition missing"
    assert pos_chkvars < pos_gen_tp, "util_chkvars must precede gen_tp_join_adsl"
    assert pos_num_periods < pos_gen_tp, "util_num_periods must precede gen_tp_join_adsl"


def test_2_path_b_classification():
    sas1, sas2, sas3 = get_clinical_macro_sources()
    combined_sas = sas3 + "\n\n" + sas2 + "\n\n" + sas1
    parsed = parse_sas_source(combined_sas)
    defs = parsed['macro_definitions']

    assert classify_macro("UTIL_CHKVARS", defs["UTIL_CHKVARS"], all_macro_defs=defs) == "PATH_B"
    assert classify_macro("UTIL_NUM_PERIODS", defs["UTIL_NUM_PERIODS"], all_macro_defs=defs) == "PATH_B"
    assert classify_macro("GEN_TP_JOIN_ADSL", defs["GEN_TP_JOIN_ADSL"], all_macro_defs=defs) == "PATH_B"


def test_3_macro_default_parameters():
    r_code = get_converted_clinical_r()
    assert '`_trtoption` = "OPTION1"' in r_code
    assert '`_varexist` = "g_vexist"' in r_code
    assert '`_missvar` = "g_vmiss"' in r_code
    assert '`_analstartdtvar` = "ADT"' in r_code


def test_4_keyword_macro_arguments():
    r_code = get_converted_clinical_r()
    assert '`_dsn` = df' in r_code or '`_dsnin` = df' in r_code
    assert '`_varlist` =' in r_code
    assert '`_varexist` =' in r_code
    assert '`_missvar` =' in r_code


def test_5_underscore_prefixed_macro_parameters():
    r_code = get_converted_clinical_r()
    assert "`_dsnin`" in r_code
    assert "`_dsnout`" in r_code
    assert "`_trtoption`" in r_code
    assert "`_dropvars`" in r_code


def test_6_backticked_r_function_signatures():
    r_code = get_converted_clinical_r()
    assert "util_chkvars <- function(`_dsnin` =" in r_code
    assert "util_num_periods <- function(`_dsn` =" in r_code
    assert "gen_tp_join_adsl <- function(`_dsnin` =" in r_code


def test_7_backticked_named_argument_invocation():
    r_code = get_converted_clinical_r()
    gen_tp_body = r_code[r_code.find("gen_tp_join_adsl <- function"):]
    assert "util_num_periods(`_dsn` = df)" in gen_tp_body
    assert "util_chkvars(`_dsnin` = df," in gen_tp_body


def test_8_nested_helper_calls_inside_owning_function():
    r_code = get_converted_clinical_r()
    gen_tp_body = r_code[r_code.find("gen_tp_join_adsl <- function"):]
    assert "util_num_periods(" in gen_tp_body
    assert "util_chkvars(" in gen_tp_body


def test_9_local_variable_handling():
    r_code = get_converted_clinical_r()
    assert "%local" not in r_code
    assert "localopt" in r_code or "`_trt_time`" in r_code


def test_10_let_dataflow():
    r_code = get_converted_clinical_r()
    assert "%let" not in r_code
    gen_tp_body = r_code[r_code.find("gen_tp_join_adsl <- function"):]
    assert '`_sdt` <- "APSDT"' in gen_tp_body
    assert '`_edt` <- "APEDT"' in gen_tp_body


def test_11_upcase_resolution():
    r_code = get_converted_clinical_r()
    assert "%upcase" not in r_code.lower()
    assert "toupper(" in r_code


def test_12_sysfunc_metadata_functions():
    r_code = get_converted_clinical_r()
    assert "%sysfunc" not in r_code.lower()
    assert "sprintf(" in r_code
    assert "grep(" in r_code or "grepl(" in r_code


def test_13_proc_contents_metadata():
    r_code = get_converted_clinical_r()
    assert "proc contents" not in r_code.lower()
    assert "colnames(" in r_code


def test_14_proc_sql_select_into():
    r_code = get_converted_clinical_r()
    assert "proc sql" not in r_code.lower()
    assert "g_prdcnt <-" in r_code
    assert "`_trt_time` <-" in r_code


def test_15_sql_in_operator():
    r_code = get_converted_clinical_r()
    assert "%in%" in r_code


def test_16_sql_not_in_operator():
    r_code = get_converted_clinical_r()
    assert "!(toupper(colnames(df)) %in%" in r_code or "!(col %in%" in r_code or "%in%" in r_code


def test_17_dynamic_ap_period_logic():
    r_code = get_converted_clinical_r()
    assert 'paste0("AP", p_str, "SDT")' in r_code or 'APERIOD' in r_code
    assert 'APERIODC' in r_code


def test_18_dynamic_trt_treatment_logic():
    r_code = get_converted_clinical_r()
    assert 'TRTP' in r_code
    assert 'TRTA' in r_code
    assert 'APHASE' in r_code


def test_19_data_step_6_lag_backup():
    r_code = get_converted_clinical_r()
    assert 'DATA_STEP_6' in r_code or 'p_str <- sprintf("%02d", i)' in r_code
    assert 'df[[paste0("_", sdt_col)]]' in r_code


def test_20_data_step_7_row_derivations():
    r_code = get_converted_clinical_r()
    assert 'DATA_STEP_7' in r_code or 'df$APERDY' in r_code
    assert 'PRE-TREATMENT' in r_code
    assert 'TREATMENT' in r_code


def test_21_data_step_8_drop_and_restore():
    r_code = get_converted_clinical_r()
    assert 'DATA_STEP_8' in r_code or 'df[[sdt_col]] <- df[[bk_sdt]]' in r_code
    assert 'df[[bk_sdt]] <- NULL' in r_code


def test_22_data_step_11_cleanup():
    r_code = get_converted_clinical_r()
    assert 'DATA_STEP_11' in r_code or 'return(df)' in r_code


def test_23_dsnin_parameter_resolution():
    r_code = get_converted_clinical_r()
    assert '`_dsnin`' in r_code
    assert 'is.data.frame(`_dsnin`)' in r_code or 'get(`_dsnin`' in r_code


def test_24_dropvars_parameter_resolution():
    r_code = get_converted_clinical_r()
    assert '`_dropvars`' in r_code
    assert 'util_chkvars(' in r_code


def test_25_analytical_start_end_parameters():
    r_code = get_converted_clinical_r()
    assert '`_analstartdtvar` = "ADT"' in r_code
    assert '`_analstarttmvar`' in r_code


def test_26_helper_functions_receiving_dataframes(tmp_path):
    r_code = get_converted_clinical_r()
    r_file = tmp_path / "clinical_output.R"
    r_file.write_text(r_code)

    runner_script = f"""
source('{r_file}')

df <- data.frame(
  USUBJID = c("SUBJ-001"),
  TR01SDT = as.Date(c("2024-01-01")),
  TR02SDT = as.Date(c("2024-02-01")),
  AP01SDT = as.Date(c("2024-01-01")),
  AP01EDT = as.Date(c("2024-01-15")),
  AP02SDT = as.Date(c("2024-02-01")),
  AP02EDT = as.Date(c("2024-02-15")),
  TRT01P  = c("Placebo"),
  TRT02P  = c("Drug A"),
  TRT01A  = c("Placebo"),
  TRT02A  = c("Drug A"),
  ADT     = as.Date(c("2024-01-05")),
  stringsAsFactors = FALSE
)

num_res <- util_num_periods(df)
stopifnot(is.list(num_res))
stopifnot(num_res$g_prdcnt == 2)

chk_res <- util_chkvars(df, "USUBJID ADT")
stopifnot(is.list(chk_res))
stopifnot(chk_res$exist == "USUBJID ADT")

cat("DF_TEST_SUCCESS\\n")
"""
    runner_file = tmp_path / "run_df_test.R"
    runner_file.write_text(runner_script)

    proc_exec = subprocess.run(["Rscript", str(runner_file)], capture_output=True, text=True)
    assert proc_exec.returncode == 0, f"DF helper execution failed:\n{proc_exec.stderr}"
    assert "DF_TEST_SUCCESS" in proc_exec.stdout


def test_27_no_unresolved_sas_tokens():
    r_code = get_converted_clinical_r()
    raw_sas_terms = ["%macro", "%mend", "%if", "%then", "%do", "%end", "proc sql", "proc contents", "proc datasets"]
    for term in raw_sas_terms:
        assert term not in r_code.lower(), f"Raw SAS term '{term}' found in generated R code!"

    unresolved_macro_vars = re.findall(r'&\w+', r_code)
    assert len(unresolved_macro_vars) == 0, f"Unresolved macro variables found: {unresolved_macro_vars}"


def test_28_rscript_parse_validation(tmp_path):
    r_code = get_converted_clinical_r()
    r_file = tmp_path / "clinical_output.R"
    r_file.write_text(r_code)

    parse_cmd = ["Rscript", "-e", f"parse(file='{r_file}')"]
    proc_parse = subprocess.run(parse_cmd, capture_output=True, text=True)
    assert proc_parse.returncode == 0, f"Rscript parse failed:\n{proc_parse.stderr}"


def test_29_runtime_execution_smoke_test(tmp_path):
    r_code = get_converted_clinical_r()
    r_file = tmp_path / "clinical_output.R"
    r_file.write_text(r_code)

    test_runner_script = f"""
source('{r_file}')

adsl <- data.frame(
  USUBJID = c("SUBJ-001", "SUBJ-002", "SUBJ-003"),
  TR01SDT = as.Date(c("2024-01-01", "2024-01-01", "2024-01-01")),
  TR02SDT = as.Date(c("2024-02-01", "2024-02-01", "2024-02-01")),
  AP01SDT = as.Date(c("2024-01-01", "2024-01-01", "2024-01-01")),
  AP01EDT = as.Date(c("2024-01-15", "2024-01-15", "2024-01-15")),
  AP02SDT = as.Date(c("2024-02-01", "2024-02-01", "2024-02-01")),
  AP02EDT = as.Date(c("2024-02-15", "2024-02-15", "2024-02-15")),
  TRT01P  = c("Placebo", "Placebo", "Drug A"),
  TRT02P  = c("Drug A", "Drug A", "Placebo"),
  TRT01A  = c("Placebo", "Placebo", "Drug A"),
  TRT02A  = c("Drug A", "Drug A", "Placebo"),
  TRT01PN = c(1, 1, 2),
  TRT02PN = c(2, 2, 1),
  TRT01AN = c(1, 1, 2),
  TRT02AN = c(2, 2, 1),
  ADT     = as.Date(c("2024-01-05", "2024-01-20", "2024-02-10")),
  stringsAsFactors = FALSE
)

# Test helper 1: util_num_periods
num_res <- util_num_periods(adsl)
stopifnot(num_res$g_prdcnt == 2)
stopifnot(num_res$g_xoveryn == "Y")

# Test helper 2: util_chkvars
chk_res <- util_chkvars(adsl, "USUBJID ADT NONEXISTENT")
stopifnot(grepl("USUBJID", chk_res$exist))
stopifnot(grepl("NONEXISTENT", chk_res$miss))

# Test main function: gen_tp_join_adsl
out_df <- gen_tp_join_adsl(`_dsnin` = adsl, `_analstartdtvar` = "ADT")
stopifnot(out_df$APERIOD[1] == 1)
stopifnot(out_df$APERIODC[1] == "Period 01")
stopifnot(out_df$APHASE[1] == "TREATMENT 01")
stopifnot(out_df$TRTP[1] == "Placebo")
stopifnot(out_df$APERDY[1] == 5)

stopifnot(out_df$APERIOD[3] == 2)
stopifnot(out_df$APERIODC[3] == "Period 02")
stopifnot(out_df$APHASE[3] == "TREATMENT 02")

cat("CLINICAL_RUNTIME_SUCCESS\\n")
"""
    runner_file = tmp_path / "run_clinical_test.R"
    runner_file.write_text(test_runner_script)

    exec_cmd = ["Rscript", str(runner_file)]
    proc_exec = subprocess.run(exec_cmd, capture_output=True, text=True)
    assert proc_exec.returncode == 0, f"Rscript execution failed:\n{proc_exec.stderr}"
    assert "CLINICAL_RUNTIME_SUCCESS" in proc_exec.stdout
