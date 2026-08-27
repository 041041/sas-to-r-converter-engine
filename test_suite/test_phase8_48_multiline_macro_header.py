"""
Phase 8.48 Multiline Macro Header & Bounded Function Evaluation Regression Test
"""

import pytest
from sas_step_converter import SASStepConverter
from macro_processor import SASMacroProcessor
from macro_converter import parse_sas_source, classify_macro


def test_phase8_48_multiline_macro_header_and_length_expansion():
    sas_code = """
%macro prepare_dataset(
    data=,
    out=,
    filter_var=,
    filter_value=,
    keepvars=,
    rename_from=,
    rename_to=
);

    data &out;
        set &data;

        if not missing(&filter_var);

        %if %length(&filter_value) > 0 %then %do;
            if &filter_var = "&filter_value";
        %end;

        keep &keepvars;

        %if %length(&rename_from) > 0 %then %do;
            rename &rename_from = &rename_to;
        %end;
    run;

%mend;

%prepare_dataset(
    data=DM,
    out=DM_CLEAN,
    filter_var=SEX,
    filter_value=M,
    keepvars=USUBJID SEX AGE,
    rename_from=USUBJID,
    rename_to=SUBJECT_ID
);

%prepare_dataset(
    data=AE,
    out=AE_CLEAN,
    filter_var=AESEV,
    filter_value=SEVERE,
    keepvars=USUBJID AESEV AEDECOD
);

%prepare_dataset(
    data=LB,
    out=LB_CLEAN,
    filter_var=LBTESTCD,
    filter_value=,
    keepvars=USUBJID LBTESTCD VISITNUM
);
"""

    # 1. Verify parse_sas_source() detects PREPARE_DATASET
    parsed = parse_sas_source(sas_code)
    assert "PREPARE_DATASET" in parsed["macro_definitions"]

    # 2. Verify classification is PATH_A
    mdef = parsed["macro_definitions"]["PREPARE_DATASET"]
    cls = classify_macro("PREPARE_DATASET", mdef, all_macro_defs=parsed["macro_definitions"])
    assert cls == "PATH_A"

    # 3. Verify SASMacroProcessor expands macro with 0 warnings
    proc = SASMacroProcessor()
    exp_code, warnings, _ = proc.process(sas_code)
    assert len(warnings) == 0

    # 4. Verify end-to-end conversion generates valid R code for all 3 steps
    converter = SASStepConverter(dialect="Modern R (dplyr)")
    res = converter.convert_program(sas_code)

    assert len(res.ast.macros) == 1
    assert "PREPARE_DATASET" in res.ast.macros
    assert len(res.converted_steps) == 3

    # Check Step 1 (DM_CLEAN)
    step1_code = res.converted_steps[0].optimized_r_code
    assert "DM_CLEAN <- DM" in step1_code
    assert "dplyr::filter(!is.na(SEX))" in step1_code
    assert "dplyr::filter(SEX == \"M\")" in step1_code
    assert "dplyr::select(USUBJID, SEX, AGE)" in step1_code
    assert "dplyr::rename(SUBJECT_ID = USUBJID)" in step1_code

    # Check Step 2 (AE_CLEAN)
    step2_code = res.converted_steps[1].optimized_r_code
    assert "AE_CLEAN <- AE" in step2_code
    assert "dplyr::filter(!is.na(AESEV))" in step2_code
    assert "dplyr::filter(AESEV == \"SEVERE\")" in step2_code
    assert "dplyr::select(USUBJID, AESEV, AEDECOD)" in step2_code

    # Check Step 3 (LB_CLEAN)
    step3_code = res.converted_steps[2].optimized_r_code
    assert "LB_CLEAN <- LB" in step3_code
    assert "dplyr::filter(!is.na(LBTESTCD))" in step3_code
    assert "dplyr::select(USUBJID, LBTESTCD, VISITNUM)" in step3_code
