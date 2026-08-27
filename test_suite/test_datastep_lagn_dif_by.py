"""
test_datastep_lagn_dif_by.py
─────────────────────────────
Focused unit tests for Phase 8.18 Bounded LAGn, DIF, and Multi-Variable BY support.
"""

import pytest
from sas_step_converter import SASStepConverter


# ── PART A: BOUNDED LAGn ──

def test_1_lag2_numeric():
    sas_code = """
    data OUT;
        set DM;
        PREV2 = lag2(AGE);
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    
    assert step.conversion_method == "Rule_DataStepLag"
    assert step.confidence_score >= 0.85
    assert "PREV2 = dplyr::lag(AGE, 2)" in step.optimized_r_code


def test_2_lag3_numeric():
    sas_code = """
    data OUT;
        set DM;
        PREV3 = lag3(AGE);
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    
    assert step.conversion_method == "Rule_DataStepLag"
    assert "PREV3 = dplyr::lag(AGE, 3)" in step.optimized_r_code


def test_3_lag2_character():
    sas_code = """
    data OUT;
        set DM;
        PREV2 = lag2(STATUS);
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    
    assert step.conversion_method == "Rule_DataStepLag"
    assert "PREV2 = dplyr::lag(STATUS, 2)" in step.optimized_r_code


def test_4_multiple_independent_lagn():
    sas_code = """
    data OUT;
        set DM;
        P2 = lag2(A);
        P3 = lag3(B);
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    
    assert step.conversion_method == "Rule_DataStepLag"
    assert "P2 = dplyr::lag(A, 2)" in step.optimized_r_code
    assert "P3 = dplyr::lag(B, 3)" in step.optimized_r_code


def test_5_arithmetic_with_one_lagn():
    sas_code = """
    data OUT;
        set DM;
        DIFF = AGE - lag2(AGE);
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    
    assert step.conversion_method == "Rule_DataStepLag"
    assert "DIFF = AGE - dplyr::lag(AGE, 2)" in step.optimized_r_code


# ── PART B: DIF() ──

def test_6_simple_dif():
    sas_code = """
    data OUT;
        set DM;
        D = dif(AGE);
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    
    assert step.conversion_method == "Rule_DataStepLag"
    assert "D = AGE - dplyr::lag(AGE)" in step.optimized_r_code


def test_7_dif_missing_first_obs_semantics():
    import pandas as pd
    import numpy as np

    df = pd.DataFrame({"AGE": [20, 25, 30, 40, 50]})
    df["DIF_AGE"] = df["AGE"] - df["AGE"].shift(1)
    
    assert np.isnan(df["DIF_AGE"].iloc[0])
    assert list(df["DIF_AGE"].iloc[1:]) == [5.0, 5.0, 10.0, 10.0]


def test_8_conditional_dif_safe_reject():
    sas_code = """
    data OUT;
        set DM;
        if FLAG='Y' then D = dif(AGE);
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_9_dif_retain_safe_reject():
    sas_code = """
    data OUT;
        set DM;
        retain X;
        D = dif(AGE);
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_10_dif_by_safe_reject():
    sas_code = """
    data OUT;
        set DM;
        by USUBJID;
        D = dif(AGE);
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


# ── SAFETY & REJECTIONS ──

def test_11_nested_lagn_safe_reject():
    sas_code = """
    data OUT;
        set DM;
        P = lag2(lag(X));
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_12_multiple_lag_calls_in_expr_safe_reject():
    sas_code = """
    data OUT;
        set DM;
        P = lag2(X) + lag3(Y);
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_13_dynamic_lag_distance_safe_reject():
    sas_code = """
    data OUT;
        set DM;
        P = lag&n(X);
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_14_lagn_merge_safe_reject():
    sas_code = """
    data OUT;
        merge DM AE;
        by USUBJID;
        P = lag2(AGE);
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_15_lagn_do_loop_safe_reject():
    sas_code = """
    data OUT;
        set DM;
        do i = 1 to 5;
            P = lag2(X);
        end;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


# ── PART C: MULTI-VARIABLE BY ──

def test_16_two_variable_by_first():
    sas_code = """
    data OUT;
        set ADSL;
        by USUBJID PARAMCD;
        if first.PARAMCD;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    
    assert step.conversion_method == "Rule_DataStepByGroup"
    assert "dplyr::arrange(USUBJID, PARAMCD)" in step.optimized_r_code
    assert "dplyr::group_by(USUBJID, PARAMCD)" in step.optimized_r_code
    assert "dplyr::slice_head(n = 1)" in step.optimized_r_code


def test_17_two_variable_by_last():
    sas_code = """
    data OUT;
        set ADSL;
        by USUBJID PARAMCD;
        if last.PARAMCD then LASTFL='Y';
        else LASTFL='N';
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    
    assert step.conversion_method == "Rule_DataStepByGroup"
    assert "dplyr::arrange(USUBJID, PARAMCD)" in step.optimized_r_code
    assert "dplyr::group_by(USUBJID, PARAMCD)" in step.optimized_r_code
    assert "LASTFL = ifelse(row_number() == n(), 'Y', 'N')" in step.optimized_r_code


def test_18_three_variable_by():
    sas_code = """
    data OUT;
        set DM;
        by STUDYID USUBJID PARAMCD;
        if last.PARAMCD then LASTFL='Y';
        else LASTFL='N';
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    
    assert step.conversion_method == "Rule_DataStepByGroup"
    assert "dplyr::arrange(STUDYID, USUBJID, PARAMCD)" in step.optimized_r_code
    assert "dplyr::group_by(STUDYID, USUBJID, PARAMCD)" in step.optimized_r_code


def test_19_by_notsorted_safe_reject():
    sas_code = """
    data OUT;
        set DM;
        by USUBJID notsorted;
        if first.USUBJID;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_20_by_descending_safe_reject():
    sas_code = """
    data OUT;
        set DM;
        by descending AGE;
        if first.AGE;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_21_by_retain_safe_reject():
    sas_code = """
    data OUT;
        set DM;
        by USUBJID PARAMCD;
        retain CNT 0;
        CNT = CNT + 1;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_22_by_lag_safe_reject():
    sas_code = """
    data OUT;
        set DM;
        by USUBJID PARAMCD;
        P = lag2(AGE);
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_23_by_merge_safe_reject():
    sas_code = """
    data OUT;
        merge DM AE;
        by USUBJID PARAMCD;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_24_reference_values_lagn_dif():
    import pandas as pd
    import numpy as np

    # Reference dataset:
    # AGE: [20, 25, 30, 40, 50]
    df = pd.DataFrame({"AGE": [20, 25, 30, 40, 50]})
    df["LAG2_AGE"] = df["AGE"].shift(2)
    df["LAG3_AGE"] = df["AGE"].shift(3)
    df["DIF_AGE"] = df["AGE"] - df["AGE"].shift(1)

    # lag2(AGE) -> [NaN, NaN, 20.0, 25.0, 30.0]
    assert np.isnan(df["LAG2_AGE"].iloc[0]) and np.isnan(df["LAG2_AGE"].iloc[1])
    assert list(df["LAG2_AGE"].iloc[2:]) == [20.0, 25.0, 30.0]

    # lag3(AGE) -> [NaN, NaN, NaN, 20.0, 25.0]
    assert np.isnan(df["LAG3_AGE"].iloc[0]) and np.isnan(df["LAG3_AGE"].iloc[1]) and np.isnan(df["LAG3_AGE"].iloc[2])
    assert list(df["LAG3_AGE"].iloc[3:]) == [20.0, 25.0]

    # dif(AGE) -> [NaN, 5.0, 5.0, 10.0, 10.0]
    assert np.isnan(df["DIF_AGE"].iloc[0])
    assert list(df["DIF_AGE"].iloc[1:]) == [5.0, 5.0, 10.0, 10.0]
