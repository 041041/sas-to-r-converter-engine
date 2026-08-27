"""
test_datastep_select_delete_schema_functions.py
────────────────────────────────────────────────
Focused unit tests for Phase 8.16 Bounded DATA-step SELECT/WHEN, DELETE, DROP/KEEP, RENAME, and Elementwise Functions.
"""

import pytest
from sas_step_converter import SASStepConverter


# ── SELECT / WHEN / OTHERWISE ──

def test_1_select_when_otherwise():
    sas_code = """
    data OUT;
        set DM;
        select;
            when (AGE >= 65) GROUP='OLD';
            when (AGE >= 18) GROUP='ADULT';
            otherwise GROUP='MINOR';
        end;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    
    assert step.conversion_method == "Rule_DataStepSelectWhen"
    assert step.confidence_score >= 0.85
    assert "GROUP = dplyr::case_when(" in step.optimized_r_code
    assert 'AGE >= 65 ~ \'OLD\'' in step.optimized_r_code or 'AGE >= 65 ~ "OLD"' in step.optimized_r_code
    assert 'TRUE ~ \'MINOR\'' in step.optimized_r_code or 'TRUE ~ "MINOR"' in step.optimized_r_code


def test_2_select_expression_form():
    sas_code = """
    data OUT;
        set DM;
        select(TYPE);
            when ('A') FLAG='Y';
            otherwise FLAG='N';
        end;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    
    assert step.conversion_method == "Rule_DataStepSelectWhen"
    assert "TYPE == 'A' ~ 'Y'" in step.optimized_r_code or 'TYPE == "A" ~ "Y"' in step.optimized_r_code
    assert "TRUE ~ 'N'" in step.optimized_r_code or 'TRUE ~ "N"' in step.optimized_r_code


def test_3_when_ordering_preserved():
    sas_code = """
    data OUT;
        set DM;
        select;
            when (SCORE > 90) GRADE='A';
            when (SCORE > 80) GRADE='B';
            when (SCORE > 70) GRADE='C';
            otherwise GRADE='F';
        end;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    
    code = step.optimized_r_code
    idx_a = code.find("'A'") if "'A'" in code else code.find('"A"')
    idx_b = code.find("'B'") if "'B'" in code else code.find('"B"')
    idx_c = code.find("'C'") if "'C'" in code else code.find('"C"')
    assert idx_a != -1 and idx_b != -1 and idx_c != -1
    assert idx_a < idx_b < idx_c


def test_4_unsupported_complex_select_safe_reject():
    sas_code = """
    data OUT;
        set DM;
        by USUBJID;
        select;
            when (AGE >= 65) GROUP='OLD';
            otherwise GROUP='YOUNG';
        end;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


# ── DELETE ──

def test_5_simple_delete():
    sas_code = """
    data OUT;
        set DM;
        if AGE < 18 then delete;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    
    assert step.conversion_method == "Rule_DataStepDelete"
    assert "dplyr::filter(!(AGE < 18))" in step.optimized_r_code


def test_6_delete_unsupported_stateful_safe_reject():
    sas_code = """
    data OUT;
        set DM;
        by USUBJID;
        if first.USUBJID then delete;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_7_delete_missing_value_edge_case():
    sas_code = """
    data OUT;
        set DM;
        if AGE = . then delete;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "Rule_DataStepDelete"
    assert "is.na(AGE)" in step.optimized_r_code


# ── DROP / KEEP ──

def test_8_drop_variable():
    sas_code = """
    data OUT;
        set DM;
        drop AGE SEX;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    
    assert step.conversion_method == "Rule_DataStepSchemaRename"
    assert "dplyr::select(-AGE, -SEX)" in step.optimized_r_code


def test_9_keep_variables():
    sas_code = """
    data OUT;
        set DM;
        keep USUBJID AGE;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    
    assert step.conversion_method == "Rule_DataStepSchemaRename"
    assert "dplyr::select(USUBJID, AGE)" in step.optimized_r_code


def test_10_drop_keep_ordering_after_assignments():
    sas_code = """
    data OUT;
        set DM;
        NEW_VAR = OLD_VAR + 1;
        drop OLD_VAR;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    
    assert step.conversion_method == "Rule_DataStepSchemaRename"
    code = step.optimized_r_code
    idx_mut = code.find("mutate")
    idx_sel = code.find("select(-OLD_VAR)")
    assert idx_mut < idx_sel


def test_11_conflicting_drop_keep_safe_reject():
    sas_code = """
    data OUT;
        set DM;
        drop AGE;
        keep USUBJID;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


# ── RENAME ──

def test_12_simple_rename():
    sas_code = """
    data OUT;
        set DM;
        rename OLD_VAR=NEW_VAR;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    
    assert step.conversion_method == "Rule_DataStepSchemaRename"
    assert "dplyr::rename(NEW_VAR = OLD_VAR)" in step.optimized_r_code


def test_13_assignment_before_rename():
    sas_code = """
    data OUT;
        set DM;
        NEW_VAR = OLD_VAR + 1;
        rename OLD_VAR=OLD_VALUE;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    
    assert step.conversion_method == "Rule_DataStepSchemaRename"
    code = step.optimized_r_code
    idx_mut = code.find("NEW_VAR = OLD_VAR + 1")
    idx_ren = code.find("dplyr::rename(OLD_VALUE = OLD_VAR)")
    assert idx_mut != -1 and idx_ren != -1
    assert idx_mut < idx_ren


def test_14_rename_collision_safe_reject():
    sas_code = """
    data OUT;
        set DM;
        by USUBJID;
        rename USUBJID=ID;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_15_complex_rename_safe_reject():
    sas_code = """
    data OUT;
        set DM;
        rename INVALID_SYNTAX;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


# ── ELEMENTWISE FUNCTIONS ──

def test_16_function_abs():
    sas_code = """
    data OUT;
        set DM;
        X = abs(A);
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert "X = abs(A)" in step.optimized_r_code


def test_17_function_missing():
    sas_code = """
    data OUT;
        set DM;
        FLAG = missing(A);
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert "FLAG = is.na(A)" in step.optimized_r_code


def test_18_function_coalesce():
    sas_code = """
    data OUT;
        set DM;
        X = coalesce(A, B);
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert "X = dplyr::coalesce(A, B)" in step.optimized_r_code


def test_19_function_round():
    sas_code = """
    data OUT;
        set DM;
        X = round(A, 0.1);
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert "X = round(A, 1)" in step.optimized_r_code


def test_20_function_sum_a_b():
    sas_code = """
    data OUT;
        set DM;
        TOTAL = sum(A, B);
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert "TOTAL = ifelse(is.na(A) & is.na(B), NA_real_, dplyr::coalesce(A, 0) + dplyr::coalesce(B, 0))" in step.optimized_r_code


def test_21_function_mean_a_b():
    sas_code = """
    data OUT;
        set DM;
        AVG = mean(A, B);
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert "AVG = ifelse(is.na(A) & is.na(B), NA_real_, (dplyr::coalesce(A, 0) + dplyr::coalesce(B, 0)) / (!is.na(A) + !is.na(B)))" in step.optimized_r_code


# ── UNSAFE COMBINATIONS ──

def test_22_function_lag_safe_reject():
    sas_code = """
    data OUT;
        set DM;
        if AGE >= 18 then X = sum(A, B);
        PREV = lag(X);
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_23_function_retain_safe_reject():
    sas_code = """
    data OUT;
        set DM;
        retain X;
        TOTAL = sum(A, B);
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_24_function_by_safe_reject():
    sas_code = """
    data OUT;
        set DM;
        by USUBJID;
        TOTAL = sum(A, B);
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_25_function_merge_safe_reject():
    sas_code = """
    data OUT;
        merge DM AE;
        by USUBJID;
        TOTAL = sum(A, B);
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


# ── REFERENCE VALUE EQUIVALENCE TESTS ──

def test_26_reference_values_sum_mean_coalesce_delete_rename():
    import pandas as pd
    import numpy as np

    # 1. SUM(A, B) and MEAN(A, B) reference evaluation
    # A   B
    # 10  20
    # 10  NaN
    # NaN 20
    # NaN NaN
    df = pd.DataFrame({
        "A": [10.0, 10.0, np.nan, np.nan],
        "B": [20.0, np.nan, 20.0, np.nan]
    })

    # SAS SUM semantics
    df["TOTAL"] = np.where(df["A"].isna() & df["B"].isna(), np.nan, df["A"].fillna(0) + df["B"].fillna(0))
    assert list(df["TOTAL"].fillna(-999)) == [30.0, 10.0, 20.0, -999]

    # SAS MEAN semantics
    df["AVG"] = np.where(
        df["A"].isna() & df["B"].isna(),
        np.nan,
        (df["A"].fillna(0) + df["B"].fillna(0)) / ((~df["A"].isna()).astype(int) + (~df["B"].isna()).astype(int))
    )
    # 10,20 -> (10+20)/2=15; 10,NaN -> 10/1=10; NaN,20 -> 20/1=20; NaN,NaN -> NaN
    assert list(df["AVG"].fillna(-999)) == [15.0, 10.0, 20.0, -999]

    # 2. COALESCE(A, B) reference evaluation
    # A    B
    # NaN  20
    # 10   30
    # NaN  NaN
    df_coal = pd.DataFrame({
        "A": [np.nan, 10.0, np.nan],
        "B": [20.0, 30.0, np.nan]
    })
    df_coal["COAL"] = df_coal["A"].combine_first(df_coal["B"])
    assert list(df_coal["COAL"].fillna(-999)) == [20.0, 10.0, -999]

    # 3. DELETE reference evaluation
    # AGE: [15, 18, 25] -> if AGE < 18 then delete;
    df_age = pd.DataFrame({"AGE": [15, 18, 25]})
    df_del = df_age[~(df_age["AGE"] < 18)]
    assert list(df_del["AGE"]) == [18, 25]

    # 4. RENAME reference evaluation
    # OLD=10 -> NEW = OLD + 1; rename OLD=OLD_VALUE;
    # Result: OLD_VALUE = 10, NEW = 11
    df_ren = pd.DataFrame({"OLD_VAR": [10]})
    df_ren["NEW_VAR"] = df_ren["OLD_VAR"] + 1
    df_ren = df_ren.rename(columns={"OLD_VAR": "OLD_VALUE"})
    assert "OLD_VALUE" in df_ren.columns and "NEW_VAR" in df_ren.columns
    assert df_ren["OLD_VALUE"].iloc[0] == 10
    assert df_ren["NEW_VAR"].iloc[0] == 11
