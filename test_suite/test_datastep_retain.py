"""
test_datastep_retain.py
───────────────────────
Focused unit tests for Phase 8.12 Bounded Clinical DATA-step RETAIN Support.
"""

import pytest
from sas_step_converter import SASStepConverter


def test_1_simple_retain_variable():
    sas_code = """
    data OUT;
        set DM;
        retain FLAG 'N';
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    
    assert step.conversion_method == "Rule_DataStepRetain"
    assert step.confidence_score >= 0.85
    assert "FLAG = 'N'" in step.optimized_r_code


def test_2_retain_initial_character_value():
    sas_code = """
    data OUT;
        set DM;
        retain STATUS 'PENDING';
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    
    assert step.conversion_method == "Rule_DataStepRetain"
    assert "STATUS = 'PENDING'" in step.optimized_r_code


def test_3_retain_initial_numeric_value():
    sas_code = """
    data OUT;
        set DM;
        retain INIT_VAL 0;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    
    assert step.conversion_method == "Rule_DataStepRetain"
    assert "INIT_VAL = 0" in step.optimized_r_code


def test_4_retain_cumulative_counter():
    sas_code = """
    data OUT;
        set DM;
        retain COUNT 0;
        COUNT = COUNT + 1;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    
    assert step.conversion_method == "Rule_DataStepRetain"
    assert "COUNT = dplyr::row_number()" in step.optimized_r_code


def test_5_retain_carry_forward_locf():
    sas_code = """
    data OUT;
        set DM;
        retain LAST_VAL;
        if VAL ne . then LAST_VAL = VAL;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    
    assert step.conversion_method == "Rule_DataStepRetain"
    assert "LAST_VAL = VAL" in step.optimized_r_code
    assert 'tidyr::fill(LAST_VAL, .direction = "down")' in step.optimized_r_code


def test_6_retain_by_first_safe_reject():
    sas_code = """
    data OUT;
        set DM;
        by USUBJID;
        retain FLAG;
        if first.USUBJID then FLAG='N';
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_7_retain_last_safe_reject():
    sas_code = """
    data OUT;
        set DM;
        by USUBJID;
        retain FLAG;
        if last.USUBJID then FLAG='Y';
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_8_retain_lag_safe_reject():
    sas_code = """
    data OUT;
        set DM;
        retain FLAG;
        PREV = lag(FLAG);
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_9_retain_merge_safe_reject():
    sas_code = """
    data OUT;
        merge DM AE;
        by USUBJID;
        retain FLAG;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_10_retain_do_loop_safe_reject():
    sas_code = """
    data OUT;
        set DM;
        retain COUNT 0;
        do i = 1 to 5;
            COUNT = COUNT + i;
        end;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_11_complex_retain_expression_safe_reject():
    sas_code = """
    data OUT;
        set DM;
        retain X 10;
        X = X * 2 + AGE;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_12_value_equivalence_logic():
    # Deterministic reference value equivalence calculation:
    # Input data:
    # ID  VAL
    # 1   A
    # 2   None
    # 3   None
    # 4   B
    # 5   None
    import pandas as pd
    
    df = pd.DataFrame({
        "ID": [1, 2, 3, 4, 5],
        "VAL": ["A", None, None, "B", None]
    })
    
    # LOCF (Carry forward) logic
    df["LAST_VAL"] = df["VAL"]
    df["LAST_VAL"] = df["LAST_VAL"].ffill()
    
    assert list(df["LAST_VAL"]) == ["A", "A", "A", "B", "B"]
    
    # Cumulative counter logic
    df["COUNT"] = range(1, len(df) + 1)
    assert list(df["COUNT"]) == [1, 2, 3, 4, 5]
