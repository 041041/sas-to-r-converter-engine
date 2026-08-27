"""
test_phase8_51_upcase_macro_condition.py
──────────────────────────────────────────
Regression test for Phase 8.51:
Validates that residual %upcase() / %lowcase() in SAS DATA step condition expressions
are translated to valid R toupper() / tolower() without leaving invalid residual '%' signs.
"""

import pytest
import re
import subprocess
import shutil
from macro_converter import parse_sas_source, classify_macro, convert_macros_to_r
from macro_processor import SASMacroProcessor
from sas_step_converter import SASStepConverter


def test_phase8_51_upcase_macro_condition():
    sas_code = """
%macro filter_text(ds=, col=, val=);
    data &ds._FILT;
        set &ds;
        %if %length(&val) > 0 %then %do;
            if %upcase(&col) = "%upcase(&val)";
        %end;
    run;
%mend;

%filter_text(ds=AE, col=aedecod, val=headache);
"""

    # 1. Macro Detection & Classification
    parsed = parse_sas_source(sas_code)
    macro_defs = parsed["macro_definitions"]
    assert "FILTER_TEXT" in macro_defs, "FILTER_TEXT macro definition not detected"

    cls = classify_macro("FILTER_TEXT", macro_defs["FILTER_TEXT"], all_macro_defs=macro_defs)
    assert cls == "PATH_A", f"Expected PATH_A for %if control flow, got {cls}"

    # 2. SAS Macro Processor Expansion
    proc = SASMacroProcessor()
    unexp_sas, warnings, _ = proc.process(sas_code, expand_path_b=True)
    assert "AE_FILT" in unexp_sas, "Expanded SAS does not contain output dataset AE_FILT"

    # 3. Conversion to R
    converter = SASStepConverter(dialect="Modern R (dplyr)")
    res = converter.convert_program(unexp_sas, raw_sas_code=sas_code)

    r_code = res.full_optimized_r

    # 4. Assertions on Generated R
    assert "%upcase" not in r_code, f"Residual %upcase macro symbol found in generated R:\n{r_code}"
    assert "%lowcase" not in r_code, f"Residual %lowcase macro symbol found in generated R:\n{r_code}"
    assert "toupper(aedecod)" in r_code or "toupper(.data$aedecod)" in r_code or "toupper(" in r_code, (
        f"Expected toupper() in generated R, got:\n{r_code}"
    )

    # 5. Executable R Syntax Validation via Rscript if installed
    if shutil.which("Rscript"):
        proc_r = subprocess.run(
            ["Rscript", "-e", f"parse(text={repr(r_code)})"],
            capture_output=True,
            text=True
        )
        assert proc_r.returncode == 0, f"Generated R has syntax error:\n{proc_r.stderr}\n\nCode:\n{r_code}"


def test_phase8_51_lowcase_macro_condition():
    sas_code = """
%macro filter_low(ds=, col=, val=);
    data &ds._FILT;
        set &ds;
        if %lowcase(&col) = "%lowcase(&val)";
    run;
%mend;

%filter_low(ds=DM, col=SEX, val=m);
"""

    converter = SASStepConverter(dialect="Modern R (dplyr)")
    proc = SASMacroProcessor()
    unexp_sas, _, _ = proc.process(sas_code, expand_path_b=True)
    res = converter.convert_program(unexp_sas, raw_sas_code=sas_code)

    r_code = res.full_optimized_r
    assert "%lowcase" not in r_code
    assert "tolower(" in r_code
