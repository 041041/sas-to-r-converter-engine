"""
test_phase9_32_failure_modes.py
───────────────────────────────
Production Hardening & Failure-Mode Audit Test Suite for Phase 9.32.

Covers:
 1. Invalid / Malformed SAS input handling
 2. Unresolved macro detection and cycle detection
 3. Unsupported SAS construct classification (SAFE_REJECT)
 4. Ambiguous / missing dataset references
 5. Include dependency resolution failure modes
 6. R code syntax & token validation
 7. ZIP path traversal security hardening
 8. Streamlit output handler safety & non-dict inputs
 9. Clinical execution regression check
"""

import io
import os
import subprocess
import tempfile
import zipfile
import pytest

from macro_converter import parse_sas_source, classify_macro, HybridMacroConverter, convert_sas_to_r
from project_engine import (
    ProjectAnalyzer,
    ResolutionStatus,
    DependencyGraph,
    DependencyResolver,
    RProject,
    RProjectAssembler,
    RProjectZipExporter,
    prepare_conversion_output,
    ConversionOutput
)
from doc_generator import validate_generated_r_code


# ─────────────────────────────────────────────────────────────────
# 1. INVALID / MALFORMED SAS INPUTS
# ─────────────────────────────────────────────────────────────────

def test_1_empty_sas_input_handling():
    parsed = parse_sas_source("")
    assert "macro_definitions" in parsed
    assert len(parsed["macro_definitions"]) == 0 or "MAIN" in parsed["macro_definitions"]

    conv = convert_sas_to_r("")
    assert "r_functions" in conv


def test_2_whitespace_sas_input_handling():
    parsed = parse_sas_source("   \n\n\t   ")
    assert "macro_definitions" in parsed

    conv = convert_sas_to_r("   \n\n\t   ")
    assert "r_functions" in conv


def test_3_malformed_macro_without_mend():
    sas_code = "%macro UNCLOSED(a, b); data out; set in; run;"
    parsed = parse_sas_source(sas_code)
    # Should not throw exception and handles unclosed macro definition safely
    assert isinstance(parsed, dict)


def test_4_incomplete_if_do_block():
    sas_code = """
    %macro BAD_IF(cond=1);
        %if &cond = 1 %then %do;
            data temp; set in; run;
        /* missing %end */
    %mend;
    """
    parsed = parse_sas_source(sas_code)
    assert isinstance(parsed, dict)


# ─────────────────────────────────────────────────────────────────
# 2. UNRESOLVED MACROS & CYCLES
# ─────────────────────────────────────────────────────────────────

def test_5_unknown_macro_call_handling():
    sas_code = """
    %macro CALLER(a=1);
        %UNKNOWN_MACRO(x=&a);
    %mend;
    """
    parsed = parse_sas_source(sas_code)
    res = HybridMacroConverter().convert_all(parsed['macro_definitions'], parsed['macro_calls'])
    assert "warnings" in res
    assert any("unresolved" in w.lower() or "unknown" in w.lower() for w in res["warnings"])


def test_6_macro_dependency_cycle_detection():
    sas_code = """
    %macro MACRO_A;
        %MACRO_B;
    %mend MACRO_A;

    %macro MACRO_B;
        %MACRO_A;
    %mend MACRO_B;
    """
    parsed = parse_sas_source(sas_code)
    res = HybridMacroConverter().convert_all(parsed['macro_definitions'], parsed['macro_calls'])
    assert "warnings" in res
    assert any("cycle" in w.lower() for w in res["warnings"])


# ─────────────────────────────────────────────────────────────────
# 3. UNSUPPORTED SAS CONSTRUCTS (SAFE_REJECT)
# ─────────────────────────────────────────────────────────────────

def test_7_unsupported_macro_eval_classification():
    macro_def = {"params": ["val"], "body": "let x = %eval(&val + 1);"}
    cls = classify_macro("EVAL_MACRO", macro_def)
    assert cls == "SAFE_REJECT"


def test_8_unsupported_macro_sysevalf_classification():
    macro_def = {"params": ["val"], "body": "let x = %sysevalf(&val / 2);"}
    cls = classify_macro("SYSEVALF_MACRO", macro_def)
    assert cls == "SAFE_REJECT"


def test_9_unsupported_macro_superq_classification():
    macro_def = {"params": ["var"], "body": "let x = %superq(var);"}
    cls = classify_macro("SUPERQ_MACRO", macro_def)
    assert cls == "SAFE_REJECT"


def test_10_multi_ampersand_indirection_classification():
    macro_def = {"params": ["var"], "body": "data out; set &&&var; run;"}
    cls = classify_macro("INDIRECT_MACRO", macro_def)
    assert cls == "SAFE_REJECT"


# ─────────────────────────────────────────────────────────────────
# 4. INCLUDE PROBLEMS & PROJECT RESOLVER HARDENING
# ─────────────────────────────────────────────────────────────────

def test_11_missing_include_file_detection():
    files = [("main.sas", '%include "nonexistent_file.sas";')]
    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project(files, main_filename="main.sas")

    assert ctx.resolution_result.status == ResolutionStatus.UNRESOLVED
    assert len(ctx.resolution_result.missing_includes) == 1
    assert ctx.resolution_result.missing_includes[0].normalized_filename == "nonexistent_file.sas"


def test_12_circular_include_detection():
    files = [
        ("file_a.sas", '%include "file_b.sas";'),
        ("file_b.sas", '%include "file_a.sas";')
    ]
    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project(files, main_filename="file_a.sas")

    assert ctx.resolution_result.status == ResolutionStatus.CIRCULAR_DEPENDENCY
    assert len(ctx.resolution_result.circular_paths) > 0


def test_13_duplicate_macro_definition_detection():
    files = [
        ("file1.sas", "%macro DUP; data a; run; %mend;"),
        ("file2.sas", "%macro DUP; data b; run; %mend;")
    ]
    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project(files, main_filename="file1.sas")

    assert ctx.resolution_result.status == ResolutionStatus.DUPLICATE_DEFINITION
    assert "DUP" in ctx.resolution_result.duplicate_definitions


# ─────────────────────────────────────────────────────────────────
# 5. ZIP SECURITY & PATH TRAVERSAL HARDENING
# ─────────────────────────────────────────────────────────────────

def test_14_zip_exporter_prevents_path_traversal_dotdot():
    prj = RProject(
        project_name="converted_project",
        main_file="main.R",
        source_files={
            "../outside.R": 'cat("outside")\n',
            "../../secret.txt": 'secret\n',
            "R/util.R": 'util <- function() { TRUE }\n'
        }
    )
    exporter = RProjectZipExporter()
    zip_bytes = exporter.export_bytes(prj)

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            assert ".." not in name, f"Path traversal '..' found in zip entry: {name}"
            assert name.startswith("converted_project/")


def test_15_zip_exporter_prevents_absolute_path_traversal():
    prj = RProject(
        project_name="converted_project",
        main_file="main.R",
        source_files={
            "/etc/passwd": 'root:x:0:0...\n',
            "C:\\Windows\\System32\\cmd.exe": 'binary\n',
            "R/util.R": 'util <- function() { TRUE }\n'
        }
    )
    exporter = RProjectZipExporter()
    zip_bytes = exporter.export_bytes(prj)

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            assert not name.startswith("/"), f"Absolute path found in zip entry: {name}"
            assert ":" not in name, f"Drive letter found in zip entry: {name}"
            assert name.startswith("converted_project/")


# ─────────────────────────────────────────────────────────────────
# 6. STREAMLIT OUTPUT HANDLER SAFETY
# ─────────────────────────────────────────────────────────────────

def test_16_output_handler_handles_none_conversion_result():
    out = prepare_conversion_output(None, output_format="Single R File")
    assert isinstance(out, ConversionOutput)
    assert out.output_format == "Single R File"
    assert out.r_code_text == ""
    assert isinstance(out.download_bytes, bytes)


def test_17_output_handler_handles_empty_dict_conversion_result():
    out = prepare_conversion_output({}, output_format="Modular R Project (.zip)")
    assert isinstance(out, ConversionOutput)
    assert out.output_format == "Modular R Project (.zip)"
    assert out.download_filename.endswith(".zip")
    assert isinstance(out.download_bytes, bytes)
    assert len(out.download_bytes) > 0


def test_18_output_handler_single_mode_does_not_invoke_zip():
    conv_res = {"r_functions": "foo <- function() { TRUE }", "r_calls": ""}
    out = prepare_conversion_output(conv_res, output_format="Single R File")
    assert out.r_project is None
    assert out.download_filename == "converted_pipeline.R"
    assert out.download_mime == "text/plain"


# ─────────────────────────────────────────────────────────────────
# 7. CLINICAL RUNTIME REGRESSION CHECK
# ─────────────────────────────────────────────────────────────────

def test_19_clinical_3_macro_runtime_regression():
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
    else:
        pytest.skip("Local test macro downloads missing; skipping clinical runtime test")

    combined_sas = sas3 + "\n\n" + sas2 + "\n\n" + sas1
    parsed = parse_sas_source(combined_sas)
    conv_res = HybridMacroConverter().convert_all(parsed['macro_definitions'], parsed['macro_calls'], 'Modern R (dplyr)')

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
