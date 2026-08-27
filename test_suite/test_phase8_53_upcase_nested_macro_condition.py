"""
test_phase8_53_upcase_nested_macro_condition.py
─────────────────────────────────────────────────
Regression test for Phase 8.53:
Validates that %upcase(&val) / %lowcase(&val) inside quotes during macro expansion evaluate to
upper/lower case string literals, and SAS DATA step upcase(column) / lowcase(column) translate to
R toupper(column) / tolower(column).
"""

import pytest
import re
import subprocess
import shutil
from macro_converter import parse_sas_source, classify_macro
from macro_processor import SASMacroProcessor
from sas_step_converter import SASStepConverter


def test_phase8_53_case_1_macro_value_upcase():
    sas_code = """
%macro test(value=);
    data OUT;
        set AE;
        if upcase(AESEV) = "%upcase(&value)";
    run;
%mend;

%test(value=SEVERE);
"""
    converter = SASStepConverter(dialect="Modern R (dplyr)")
    proc = SASMacroProcessor()
    unexp_sas, _, _ = proc.process(sas_code, expand_path_b=True)
    res = converter.convert_program(unexp_sas, raw_sas_code=sas_code)

    r_code = res.full_optimized_r
    assert "%upcase" not in r_code
    assert 'toupper(AESEV) == "SEVERE"' in r_code or 'toupper(.data$AESEV) == "SEVERE"' in r_code


def test_phase8_53_case_2_direct_upcase_literal():
    sas_code = """
data OUT;
    set AE;
    if upcase(AESEV) = "%upcase(SEVERE)";
run;
"""
    converter = SASStepConverter(dialect="Modern R (dplyr)")
    proc = SASMacroProcessor()
    unexp_sas, _, _ = proc.process(sas_code, expand_path_b=True)
    res = converter.convert_program(unexp_sas, raw_sas_code=sas_code)

    r_code = res.full_optimized_r
    assert "%upcase" not in r_code
    assert 'toupper(AESEV) == "SEVERE"' in r_code or 'toupper(.data$AESEV) == "SEVERE"' in r_code


def test_phase8_53_case_3_direct_lowcase_literal():
    sas_code = """
data OUT;
    set AE;
    if lowcase(AESEV) = "%lowcase(SEVERE)";
run;
"""
    converter = SASStepConverter(dialect="Modern R (dplyr)")
    proc = SASMacroProcessor()
    unexp_sas, _, _ = proc.process(sas_code, expand_path_b=True)
    res = converter.convert_program(unexp_sas, raw_sas_code=sas_code)

    r_code = res.full_optimized_r
    assert "%lowcase" not in r_code
    assert 'tolower(AESEV) == "severe"' in r_code or 'tolower(.data$AESEV) == "severe"' in r_code


def test_phase8_53_case_4_mixed_case_macro_args():
    sas_code = """
%macro test_mixed(variable=, value=);
    data OUT;
        set AE;
        if upcase(&variable) = "%upcase(&value)";
    run;
%mend;

%test_mixed(variable=AESEV, value=SeVeRe);
"""
    converter = SASStepConverter(dialect="Modern R (dplyr)")
    proc = SASMacroProcessor()
    unexp_sas, _, _ = proc.process(sas_code, expand_path_b=True)
    res = converter.convert_program(unexp_sas, raw_sas_code=sas_code)

    r_code = res.full_optimized_r
    assert "%upcase" not in r_code
    assert 'toupper(AESEV) == "SEVERE"' in r_code or 'toupper(.data$AESEV) == "SEVERE"' in r_code


def test_phase8_53_full_very_hard_pipeline():
    sas_input = """
%macro apply_filter(ds=, var=, val=, out=, keepvars=, rename_from=, rename_to=);
    data &out;
        set &ds;

        if not missing(&var);

        %if %length(&val) > 0 %then %do;
            if upcase(&var) = "%upcase(&val)";
        %end;

        keep &keepvars;

        %if %length(&rename_from) > 0 %then %do;
            rename &rename_from = &rename_to;
        %end;
    run;
%mend;

%macro transform_domain(domain=, keyvar=, filter_val=, keepvars=, rename_from=, rename_to=, out=);
    %apply_filter(
        ds=&domain,
        var=&keyvar,
        val=&filter_val,
        out=&out._FILT,
        keepvars=&keepvars,
        rename_from=&rename_from,
        rename_to=&rename_to
    );

    proc sort data=&out._FILT out=&out;
        by USUBJID;
    run;
%mend;

%transform_domain(domain=DM, keyvar=SEX, filter_val=M, keepvars=USUBJID SEX AGE, rename_from=USUBJID, rename_to=SUBJECT_ID, out=DM_CLEAN);
%transform_domain(domain=AE, keyvar=AESEV, filter_val=SEVERE, keepvars=USUBJID AESEV AEDECOD, out=AE_CLEAN);
%transform_domain(domain=LB, keyvar=LBTESTCD, filter_val=ALT, keepvars=USUBJID LBTESTCD LBSTRESN, out=LB_CLEAN);
"""

    parsed = parse_sas_source(sas_input)
    macro_defs = parsed["macro_definitions"]
    assert "APPLY_FILTER" in macro_defs
    assert "TRANSFORM_DOMAIN" in macro_defs
    assert classify_macro("APPLY_FILTER", macro_defs["APPLY_FILTER"], all_macro_defs=macro_defs) == "PATH_A"
    assert classify_macro("TRANSFORM_DOMAIN", macro_defs["TRANSFORM_DOMAIN"], all_macro_defs=macro_defs) == "PATH_A"

    proc = SASMacroProcessor()
    unexp_sas, warnings, _ = proc.process(sas_input, expand_path_b=True)
    assert "%upcase" not in unexp_sas
    assert "%length" not in unexp_sas

    converter = SASStepConverter(dialect="Modern R (dplyr)")
    res = converter.convert_program(unexp_sas, raw_sas_code=sas_input)
    r_code = res.full_optimized_r

    # Zero residual SAS syntax
    assert "%upcase" not in r_code
    assert "%lowcase" not in r_code
    assert "%length" not in r_code
    assert "upcase(" not in r_code
    assert "lowcase(" not in r_code
    assert "&variable" not in r_code
    assert "&value" not in r_code

    # DM assertions
    assert "!is.na(SEX)" in r_code
    assert 'toupper(SEX) == "M"' in r_code
    assert "SUBJECT_ID = USUBJID" in r_code or "SUBJECT_ID = .data$USUBJID" in r_code

    # AE assertions
    assert "!is.na(AESEV)" in r_code
    assert 'toupper(AESEV) == "SEVERE"' in r_code

    # LB assertions
    assert "!is.na(LBTESTCD)" in r_code
    assert 'toupper(LBTESTCD) == "ALT"' in r_code

    # Executable syntax validation via Rscript
    if shutil.which("Rscript"):
        proc_r = subprocess.run(
            ["Rscript", "-e", f"parse(text={repr(r_code)})"],
            capture_output=True,
            text=True
        )
        assert proc_r.returncode == 0, f"Generated R has syntax error:\n{proc_r.stderr}\n\nCode:\n{r_code}"
