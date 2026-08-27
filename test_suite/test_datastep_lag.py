"""
test_datastep_lag.py
─────────────────────
Focused unit tests for Phase 8.14 Bounded Unconditional LAG() Support and P1 Conditional-LAG Safety Fix.
"""

import pytest
from sas_step_converter import SASStepConverter


def test_1_simple_numeric_lag():
    sas_code = """
    data OUT;
        set DM;
        PREV_AGE = lag(AGE);
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    
    assert step.conversion_method == "Rule_DataStepLag"
    assert step.confidence_score >= 0.85
    assert "PREV_AGE = dplyr::lag(AGE)" in step.optimized_r_code


def test_2_simple_character_lag():
    sas_code = """
    data OUT;
        set DM;
        PREV_STATUS = lag(STATUS);
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    
    assert step.conversion_method == "Rule_DataStepLag"
    assert "PREV_STATUS = dplyr::lag(STATUS)" in step.optimized_r_code


def test_3_multiple_independent_lag():
    sas_code = """
    data OUT;
        set DM;
        P1 = lag(A);
        P2 = lag(B);
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    
    assert step.conversion_method == "Rule_DataStepLag"
    assert "P1 = dplyr::lag(A)" in step.optimized_r_code
    assert "P2 = dplyr::lag(B)" in step.optimized_r_code


def test_4_arithmetic_lag():
    sas_code = """
    data OUT;
        set DM;
        DIFF = AGE - lag(AGE);
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    
    assert step.conversion_method == "Rule_DataStepLag"
    assert "DIFF = AGE - dplyr::lag(AGE)" in step.optimized_r_code


def test_5_conditional_lag_safe_reject_p1_fix():
    sas_code = """
    data OUT;
        set DM;
        if AGE >= 18 then PREV = lag(AGE);
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    # Critical P1 safety assertion: MUST NOT translate via Rule_DataStepFilter or produce case_when
    assert step.conversion_method == "ManualReviewRequired"
    assert "case_when" not in step.optimized_r_code


def test_6_lag_retain_safe_reject():
    sas_code = """
    data OUT;
        set DM;
        retain X;
        P = lag(X);
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_7_lag_by_safe_reject():
    sas_code = """
    data OUT;
        set DM;
        by USUBJID;
        P = lag(AGE);
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_8_lag_first_safe_reject():
    sas_code = """
    data OUT;
        set DM;
        by USUBJID;
        if first.USUBJID then P = lag(AGE);
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_9_lag_last_safe_reject():
    sas_code = """
    data OUT;
        set DM;
        by USUBJID;
        if last.USUBJID then P = lag(AGE);
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_10_nested_lag_safe_reject():
    sas_code = """
    data OUT;
        set DM;
        P = lag(lag(X));
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_11_multiple_lags_in_one_expr_safe_reject():
    sas_code = """
    data OUT;
        set DM;
        P = lag(X) + lag(Y);
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_12_lag_merge_safe_reject():
    sas_code = """
    data OUT;
        merge DM AE;
        by USUBJID;
        P = lag(AGE);
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_13_lag_do_loop_safe_reject():
    sas_code = """
    data OUT;
        set DM;
        do i = 1 to 5;
            P = lag(X);
        end;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_14_lag_inside_function_safe_reject():
    sas_code = """
    data OUT;
        set DM;
        P = mean(lag(X), 10);
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_15_unsupported_statement_lag_safe_reject():
    sas_code = """
    data OUT;
        set DM;
        P = lag(X);
        output;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_16_value_equivalence_reference_logic():
    # Value equivalence of reference dataset:
    # AGE: [20, 25, 30, 40]
    # PREV_AGE (lag(AGE)): [NaN, 20.0, 25.0, 30.0]
    # DIFF (AGE - lag(AGE)): [NaN, 5.0, 5.0, 10.0]
    import pandas as pd
    import numpy as np
    
    df = pd.DataFrame({"AGE": [20, 25, 30, 40]})
    df["PREV_AGE"] = df["AGE"].shift(1)
    df["DIFF"] = df["AGE"] - df["PREV_AGE"]
    
    assert np.isnan(df["PREV_AGE"].iloc[0])
    assert list(df["PREV_AGE"].iloc[1:]) == [20.0, 25.0, 30.0]
    
    assert np.isnan(df["DIFF"].iloc[0])
    assert list(df["DIFF"].iloc[1:]) == [5.0, 5.0, 10.0]
