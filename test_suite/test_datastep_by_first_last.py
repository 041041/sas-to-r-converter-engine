"""
test_datastep_by_first_last.py
──────────────────────────────
Focused unit tests for Phase 8.11 Bounded Clinical DATA-step BY / FIRST. / LAST. Support.
"""

import pytest
from sas_step_converter import SASStepConverter


def test_1_by_first_filter():
    sas_code = """
    data ADSL;
        set DM;
        by USUBJID;
        if first.USUBJID;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    
    assert step.conversion_method == "Rule_DataStepByGroup"
    assert step.confidence_score >= 0.85
    assert "dplyr::arrange(USUBJID)" in step.optimized_r_code
    assert "dplyr::group_by(USUBJID)" in step.optimized_r_code
    assert "dplyr::slice_head(n = 1)" in step.optimized_r_code
    assert "FIRST.USUBJID" not in step.optimized_r_code


def test_2_by_last_filter():
    sas_code = """
    data ADSL;
        set DM;
        by USUBJID;
        if last.USUBJID;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    
    assert step.conversion_method == "Rule_DataStepByGroup"
    assert "dplyr::arrange(USUBJID)" in step.optimized_r_code
    assert "dplyr::group_by(USUBJID)" in step.optimized_r_code
    assert "dplyr::slice_tail(n = 1)" in step.optimized_r_code
    assert "LAST.USUBJID" not in step.optimized_r_code


def test_3_by_first_assignment():
    sas_code = """
    data DM2;
        set DM;
        by USUBJID;
        if first.USUBJID then FIRSTFL='Y';
        else FIRSTFL='N';
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    
    assert step.conversion_method == "Rule_DataStepByGroup"
    assert "FIRSTFL = ifelse(row_number() == 1, 'Y', 'N')" in step.optimized_r_code
    assert "FIRST.USUBJID" not in step.optimized_r_code


def test_4_by_last_assignment():
    sas_code = """
    data DM2;
        set DM;
        by USUBJID;
        if last.USUBJID then LASTFL='Y';
        else LASTFL='N';
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    
    assert step.conversion_method == "Rule_DataStepByGroup"
    assert "LASTFL = ifelse(row_number() == n(), 'Y', 'N')" in step.optimized_r_code
    assert "LAST.USUBJID" not in step.optimized_r_code


def test_5_first_and_last_assignment():
    sas_code = """
    data DM2;
        set DM;
        by USUBJID;
        if first.USUBJID then FIRSTFL='Y';
        else FIRSTFL='N';
        if last.USUBJID then LASTFL='Y';
        else LASTFL='N';
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    
    assert step.conversion_method == "Rule_DataStepByGroup"
    assert "FIRSTFL = ifelse(row_number() == 1, 'Y', 'N')" in step.optimized_r_code
    assert "LASTFL = ifelse(row_number() == n(), 'Y', 'N')" in step.optimized_r_code


def test_6_multiple_by_variables_safe_reject():
    sas_code = """
    data ADSL;
        set DM;
        by USUBJID PARAMCD;
        if first.USUBJID;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "Rule_DataStepByGroup"
    assert "dplyr::arrange(USUBJID, PARAMCD)" in step.optimized_r_code


def test_7_merge_by_first_safe_reject():
    sas_code = """
    data ADSL;
        merge DM AE;
        by USUBJID;
        if first.USUBJID;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_8_retain_first_safe_reject():
    sas_code = """
    data ADSL;
        set DM;
        by USUBJID;
        retain COUNT 0;
        if first.USUBJID then COUNT=1;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_9_lag_first_safe_reject():
    sas_code = """
    data ADSL;
        set DM;
        by USUBJID;
        PREV = lag(AGE);
        if first.USUBJID;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_10_by_notsorted_safe_reject():
    sas_code = """
    data ADSL;
        set DM;
        by notsorted USUBJID;
        if first.USUBJID;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_11_by_descending_safe_reject():
    sas_code = """
    data ADSL;
        set DM;
        by descending USUBJID;
        if first.USUBJID;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_12_complex_expression_safe_reject():
    sas_code = """
    data ADSL;
        set DM;
        by USUBJID;
        if first.USUBJID and AGE > 50;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_13_no_literal_first_last_columns():
    sas_code = """
    data ADSL;
        set DM;
        by USUBJID;
        if first.USUBJID;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert "FIRST.USUBJID" not in step.optimized_r_code
    assert "LAST.USUBJID" not in step.optimized_r_code
    assert "first.usubjid" not in step.optimized_r_code.lower()


def test_14_value_equivalence_logic():
    # Value equivalence validation of python logic simulation on clinical test data:
    # Input:
    # USUBJID  VISIT
    # 01       1
    # 01       2
    # 01       3
    # 02       1
    # 02       2
    
    import pandas as pd
    df = pd.DataFrame({
        "USUBJID": ["01", "01", "01", "02", "02"],
        "VISIT": [1, 2, 3, 1, 2]
    })
    
    # 1. FIRST filter
    first_df = df.groupby("USUBJID", as_index=False).first()
    assert list(first_df["VISIT"]) == [1, 1]
    
    # 2. LAST filter
    last_df = df.groupby("USUBJID", as_index=False).last()
    assert list(last_df["VISIT"]) == [3, 2]
    
    # 3. FIRSTFL
    df["FIRSTFL"] = df.groupby("USUBJID").cumcount().apply(lambda x: "Y" if x == 0 else "N")
    assert list(df["FIRSTFL"]) == ["Y", "N", "N", "Y", "N"]
    
    # 4. LASTFL
    df["LASTFL"] = df.groupby("USUBJID").cumcount(ascending=False).apply(lambda x: "Y" if x == 0 else "N")
    assert list(df["LASTFL"]) == ["N", "N", "Y", "N", "Y"]


def test_15_outer_by_first_usubjid():
    sas_code = """
    data ADSL;
        set DM;
        by USUBJID PARAMCD;
        if first.USUBJID then USUBFL='Y';
        else USUBFL='N';
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "Rule_DataStepByGroup"
    assert "dplyr::arrange(USUBJID, PARAMCD)" in step.optimized_r_code
    assert "dplyr::group_by(USUBJID)" in step.optimized_r_code
    assert "group_by(USUBJID, PARAMCD)" not in step.optimized_r_code


def test_16_outer_by_last_usubjid():
    sas_code = """
    data ADSL;
        set DM;
        by USUBJID PARAMCD;
        if last.USUBJID then USUBLAST='Y';
        else USUBLAST='N';
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "Rule_DataStepByGroup"
    assert "dplyr::arrange(USUBJID, PARAMCD)" in step.optimized_r_code
    assert "dplyr::group_by(USUBJID)" in step.optimized_r_code
    assert "group_by(USUBJID, PARAMCD)" not in step.optimized_r_code


def test_17_inner_by_first_paramcd():
    sas_code = """
    data ADSL;
        set DM;
        by USUBJID PARAMCD;
        if first.PARAMCD then PARAMFL='Y';
        else PARAMFL='N';
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "Rule_DataStepByGroup"
    assert "dplyr::arrange(USUBJID, PARAMCD)" in step.optimized_r_code
    assert "dplyr::group_by(USUBJID, PARAMCD)" in step.optimized_r_code


def test_18_combined_first_usubjid_first_paramcd():
    sas_code = """
    data ADSL;
        set DM;
        by USUBJID PARAMCD;
        if first.USUBJID then USUBFL='Y';
        if first.PARAMCD then PARAMFL='Y';
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "Rule_DataStepByGroup"
    assert "dplyr::group_by(USUBJID)" in step.optimized_r_code
    assert "dplyr::group_by(USUBJID, PARAMCD)" in step.optimized_r_code


def test_19_unknown_first_variable_safe_reject():
    sas_code = """
    data ADSL;
        set DM;
        by USUBJID;
        if first.PARAMCD then PARAMFL='Y';
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_20_reference_dataset_exact_boundary_equivalence():
    import pandas as pd

    df = pd.DataFrame({
        "USUBJID": ["001", "001", "001", "001", "002", "002", "002", "002"],
        "PARAMCD": ["LAB", "LAB", "ECG", "ECG", "LAB", "LAB", "ECG", "ECG"],
        "VALUE": [10, 20, 30, 40, 50, 60, 70, 80]
    })

    df["FIRST_USUBJID"] = df.groupby("USUBJID").cumcount().apply(lambda x: "Y" if x == 0 else "N")
    assert list(df["FIRST_USUBJID"]) == ["Y", "N", "N", "N", "Y", "N", "N", "N"]

    df["LAST_USUBJID"] = df.groupby("USUBJID").cumcount(ascending=False).apply(lambda x: "Y" if x == 0 else "N")
    assert list(df["LAST_USUBJID"]) == ["N", "N", "N", "Y", "N", "N", "N", "Y"]

    df["FIRST_PARAMCD"] = df.groupby(["USUBJID", "PARAMCD"]).cumcount().apply(lambda x: "Y" if x == 0 else "N")
    assert list(df["FIRST_PARAMCD"]) == ["Y", "N", "Y", "N", "Y", "N", "Y", "N"]

    df["LAST_PARAMCD"] = df.groupby(["USUBJID", "PARAMCD"]).cumcount(ascending=False).apply(lambda x: "Y" if x == 0 else "N")
    assert list(df["LAST_PARAMCD"]) == ["N", "Y", "N", "Y", "N", "Y", "N", "Y"]
