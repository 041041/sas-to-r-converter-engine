"""
test_sas_macro_indirect_references.py
──────────────────────────────────────
Unit test suite for Phase 8.22 — Bounded Indirect SAS Macro References (&&var&i).
"""

import pytest
from macro_processor import SASMacroProcessor
from sas_step_converter import SASStepConverter


def test_1_simple_indirect_reference():
    sas_code = """
    %let ds1=DM;
    %let ds2=AE;
    %do i=1 %to 2;
        data OUT&i;
            set &&ds&i;
        run;
    %end;
    """
    proc = SASMacroProcessor()
    code, warnings, _ = proc.process(sas_code)
    assert "data OUT1;" in code
    assert "set DM;" in code
    assert "data OUT2;" in code
    assert "set AE;" in code


def test_2_two_iterations():
    sas_code = """
    %let ds1=DM;
    %let ds2=AE;
    %do i=1 %to 2;
        data OUT&i;
            set &&ds&i;
        run;
    %end;
    """
    proc = SASMacroProcessor()
    code, warnings, _ = proc.process(sas_code)
    assert "data OUT1;" in code
    assert "set DM;" in code
    assert "data OUT2;" in code
    assert "set AE;" in code


def test_3_three_iterations_reference_1():
    sas_code = """
    %let ds1=DM;
    %let ds2=AE;
    %let ds3=LB;

    %do i=1 %to 3;

        data OUT&i;
            set &&ds&i;
        run;

    %end;
    """
    proc = SASMacroProcessor()
    code, warnings, _ = proc.process(sas_code)
    assert "data OUT1;" in code
    assert "set DM;" in code
    assert "data OUT2;" in code
    assert "set AE;" in code
    assert "data OUT3;" in code
    assert "set LB;" in code


def test_4_datastep_set_usage():
    sas_code = """
    %let ds1=DM;
    %do i=1 %to 1;
        data OUT;
            set &&ds&i;
        run;
    %end;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method != "ManualReviewRequired"
    assert "OUT <- DM" in step.optimized_r_code


def test_5_multiple_indirect_references_reference_2():
    sas_code = """
    %let in1=DM;
    %let out1=DM2;

    %let in2=AE;
    %let out2=AE2;

    %do i=1 %to 2;

        data &&out&i;
            set &&in&i;
        run;

    %end;
    """
    proc = SASMacroProcessor()
    code, warnings, _ = proc.process(sas_code)
    assert "data DM2;" in code
    assert "set DM;" in code
    assert "data AE2;" in code
    assert "set AE;" in code


def test_6_indirect_plus_normal_macro_variable():
    sas_code = """
    %let prefix=STUDY;
    %let ds1=DM;
    %let ds2=AE;

    %do i=1 %to 2;

        data &prefix._&i;
            set &&ds&i;
        run;

    %end;
    """
    proc = SASMacroProcessor()
    code, warnings, _ = proc.process(sas_code)
    assert "data STUDY_1;" in code
    assert "set DM;" in code
    assert "data STUDY_2;" in code
    assert "set AE;" in code


def test_7_deterministic_if():
    sas_code = """
    %let ds1=DM;
    %let ds2=AE;

    %do i=1 %to 2;

        %if &i = 1 %then %do;
            data OUT;
                set &&ds&i;
            run;
        %end;

    %end;
    """
    proc = SASMacroProcessor()
    code, warnings, _ = proc.process(sas_code)
    assert "data OUT;" in code
    assert "set DM;" in code
    assert "AE" not in code


def test_8_indirect_outside_do_safe_reject():
    sas_code = """
    %let ds1=DM;
    %let i=1;
    data OUT;
        set &&ds&i;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_9_unknown_iterator_safe_reject():
    sas_code = """
    %let ds1=DM;
    %do i=1 %to 2;
        data OUT;
            set &&ds&j;
        run;
    %end;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_10_missing_target_variable_safe_reject():
    sas_code = """
    %let ds1=DM;
    %do i=1 %to 2;
        data OUT&i;
            set &&ds&i;
        run;
    %end;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    # Step 2 (OUT2) should fail closed because ds2 is missing
    step2 = res.converted_steps[1]
    assert step2.conversion_method == "ManualReviewRequired"


def test_11_nested_quad_ampersand_safe_reject():
    sas_code = """
    %let ds1=DM;
    %do i=1 %to 1;
        data OUT;
            set &&&&ds&i;
        run;
    %end;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_12_unresolved_dynamic_reference_safe_reject():
    sas_code = """
    %do i=1 %to 1;
        data OUT;
            set &&&dynamic&i;
        run;
    %end;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_13_unsupported_sysfunc_combination_safe_reject():
    sas_code = """
    %let ds1=DM;
    %do i=1 %to 1;
        %let handle=%sysfunc(open(&&ds&i));
    %end;
    """
    proc = SASMacroProcessor()
    code, warnings, _ = proc.process(sas_code)
    assert any("unsupported" in w.lower() for w in warnings)


def test_14_path_b_unresolved_indirect_reference():
    sas_code = """
    %macro dynamic_proc(num=);
        data OUT;
            set &&ds&num;
        run;
    %mend dynamic_proc;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    assert res.converted_steps[0].conversion_method in ("ManualReviewRequired", "NoRuleMatched")


def test_15_normal_macro_var_regression():
    sas_code = """
    %let ds=DM;
    data OUT;
        set &ds;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    assert res.converted_steps[0].conversion_method != "ManualReviewRequired"


def test_16_phase_8_21_function_regression():
    sas_code = """
    %let ds=STUDY_ADSL_FINAL;
    %let prefix=%substr(&ds, 7, 4);
    %let part=%scan(&ds, 2, %str(_));
    %let pos=%index(&ds, ADSL);
    %let len=%length(&ds);
    """
    proc = SASMacroProcessor()
    proc.process(sas_code)
    assert proc.let_vars.get("PREFIX") == "ADSL"
    assert proc.let_vars.get("PART") == "ADSL"
    assert proc.let_vars.get("POS") == "7"
    assert proc.let_vars.get("LEN") == "16"


def test_17_phase_8_9_if_regression():
    sas_code = """
    %let flag=Y;
    %if &flag = Y %then %do;
        data OUT;
            set DM;
        run;
    %end;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    assert res.converted_steps[0].conversion_method != "ManualReviewRequired"


def test_18_phase_8_8_dependency_regression():
    from dependency_graph import topological_sort_macros, MacroCallNode
    graph = {
        "MACRO_B": MacroCallNode("MACRO_B", calls=["MACRO_A"]),
        "MACRO_A": MacroCallNode("MACRO_A", calls=[]),
        "UTILITY": MacroCallNode("UTILITY", calls=["MACRO_B"])
    }
    ordered, has_cycle, err = topological_sort_macros(graph)
    assert not has_cycle
    assert ordered == ["MACRO_A", "MACRO_B", "UTILITY"]


def test_19_bounded_do_regression():
    sas_code = """
    %do i=1 %to 3;
        data OUT&i;
            set DM;
        run;
    %end;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    assert len(res.converted_steps) == 3
    assert res.converted_steps[0].conversion_method != "ManualReviewRequired"


def test_20_trailing_digit_ds1_ds2_ds3():
    sas_code = """
    %let ds1=DM;
    %let ds2=AE;
    %let ds3=LB;

    %do i=1 %to 3;
        data OUT&i;
            set &&ds&i;
        run;
    %end;
    """
    proc = SASMacroProcessor()
    code, warnings, _ = proc.process(sas_code)
    assert "data OUT1;" in code
    assert "set DM;" in code
    assert "data OUT2;" in code
    assert "set AE;" in code
    assert "data OUT3;" in code
    assert "set LB;" in code


def test_21_in1_out1_pattern():
    sas_code = """
    %let in1=DM;
    %let out1=DM2;
    %let in2=AE;
    %let out2=AE2;

    %do i=1 %to 2;
        data &&out&i;
            set &&in&i;
        run;
    %end;
    """
    proc = SASMacroProcessor()
    code, warnings, _ = proc.process(sas_code)
    assert "data DM2;" in code
    assert "set DM;" in code
    assert "data AE2;" in code
    assert "set AE;" in code


def test_22_multi_digit_trailing_names():
    sas_code = """
    %let ds10=DM;
    %let ds20=AE;

    %do i=10 %to 20 %by 10;
        data OUT&i;
            set &&ds&i;
        run;
    %end;
    """
    proc = SASMacroProcessor()
    code, warnings, _ = proc.process(sas_code)
    assert "data OUT10;" in code
    assert "set DM;" in code
    assert "data OUT20;" in code
    assert "set AE;" in code


def test_23_base_name_with_embedded_digits():
    sas_code = """
    %let set1_1=DM;
    %let set1_2=AE;

    %do i=1 %to 2;
        data OUT&i;
            set &&set1_&i;
        run;
    %end;
    """
    proc = SASMacroProcessor()
    code, warnings, _ = proc.process(sas_code)
    assert "data OUT1;" in code
    assert "set DM;" in code
    assert "data OUT2;" in code
    assert "set AE;" in code


def test_24_trailing_digit_missing_target_safe_reject():
    sas_code = """
    %let ds10=DM;

    %do i=10 %to 20 %by 10;
        data OUT&i;
            set &&ds&i;
        run;
    %end;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step2 = res.converted_steps[1]
    assert step2.conversion_method == "ManualReviewRequired"


def test_25_trailing_digit_unknown_iterator_safe_reject():
    sas_code = """
    %let ds1=DM;

    %do i=1 %to 2;
        data OUT;
            set &&ds&j;
        run;
    %end;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_26_trailing_digit_outside_do_safe_reject():
    sas_code = """
    %let ds1=DM;
    %let i=1;

    data OUT;
        set &&ds&i;
    run;
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"
