"""
test_sas_macro_if_else.py
─────────────────────────
Focused unit tests for Phase 8.9 Bounded SAS Macro %IF / %THEN / %ELSE Support.
"""

import pytest
from macro_processor import SASMacroProcessor
from sas_step_converter import SASStepConverter


def test_1_simple_true_condition():
    sas_code = """
    %macro flag();
        %if 65 >= 65 %then %do;
            data ADSL;
                set DM;
            run;
        %end;
    %mend;
    %flag();
    """
    processor = SASMacroProcessor()
    expanded, warnings, _ = processor.process(sas_code)
    assert "data ADSL;" in expanded
    assert "set DM;" in expanded
    
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "Rule_DataStepFilter"
    assert "ADSL <- DM" in step.optimized_r_code


def test_2_simple_false_condition():
    sas_code = """
    %macro flag();
        %if 18 >= 65 %then %do;
            data ADSL;
                set DM;
            run;
        %end;
    %mend;
    %flag();
    """
    processor = SASMacroProcessor()
    expanded, warnings, _ = processor.process(sas_code)
    assert "data ADSL;" not in expanded


def test_3_if_then_else():
    sas_code = """
    %macro flag();
        %if 18 >= 65 %then %do;
            data ADSL;
                set DM;
            run;
        %end;
        %else %do;
            data ADSL;
                set AE;
            run;
        %end;
    %mend;
    %flag();
    """
    processor = SASMacroProcessor()
    expanded, warnings, _ = processor.process(sas_code)
    assert "set AE;" in expanded
    assert "set DM;" not in expanded

    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "Rule_DataStepFilter"
    assert "ADSL <- AE" in step.optimized_r_code


def test_4_let_variable_in_condition():
    sas_code = """
    %let threshold = 65;
    %macro flag(ds=DM);
        %if &threshold >= 65 %then %do;
            data ADSL;
                set &ds;
            run;
        %end;
    %mend;
    %flag(ds=DM);
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "Rule_DataStepFilter"
    assert "ADSL <- DM" in step.optimized_r_code


def test_5_macro_parameter_in_condition():
    sas_code = """
    %macro flag(ds=DM, min_age=18);
        %if &min_age >= 18 %then %do;
            data ADSL;
                set &ds;
            run;
        %end;
    %mend;
    %flag(ds=AE, min_age=21);
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "Rule_DataStepFilter"
    assert "ADSL <- AE" in step.optimized_r_code


def test_6_default_parameter_in_condition():
    sas_code = """
    %macro flag(flag=Y);
        %if &flag = Y %then %do;
            data ADSL;
                set DM;
            run;
        %end;
    %mend;
    %flag();
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "Rule_DataStepFilter"
    assert "ADSL <- DM" in step.optimized_r_code


def test_7_numeric_comparison():
    sas_code = """
    %macro test(val=70);
        %if &val > 65 %then %do;
            data ADSL;
                set DM;
            run;
        %end;
    %mend;
    %test(val=70);
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "Rule_DataStepFilter"


def test_8_character_comparison():
    sas_code = """
    %macro test(pop=SAFFL);
        %if &pop = 'SAFFL' %then %do;
            data ADSL;
                set DM;
            run;
        %end;
    %mend;
    %test(pop=SAFFL);
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "Rule_DataStepFilter"


def test_9_unsupported_eval_safe_reject():
    sas_code = """
    %macro test(x=5);
        %if %eval(&x + 1) > 5 %then %do;
            data ADSL;
                set DM;
            run;
        %end;
    %mend;
    %test();
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_10_unsupported_sysfunc_safe_reject():
    sas_code = """
    %macro test();
        %if %sysfunc(today()) > 0 %then %do;
            data ADSL;
                set DM;
            run;
        %end;
    %mend;
    %test();
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_11_unknown_function_safe_reject():
    sas_code = """
    %macro test(flag=Y);
        %if %UNKNOWN_FUNCTION(&flag) = Y %then %do;
            data WRONG;
                set DM;
            run;
        %end;
    %mend;
    %test();
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    # Critical safety assertion: MUST NOT evaluate as True or output WRONG <- DM
    assert step.conversion_method == "ManualReviewRequired"
    assert "WRONG <- DM" not in step.optimized_r_code


def test_12_indirect_reference_safe_reject():
    sas_code = """
    %macro test();
        %if &&dynamic = Y %then %do;
            data ADSL;
                set DM;
            run;
        %end;
    %mend;
    %test();
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"


def test_13_invalid_expression_safe_reject():
    sas_code = """
    %macro test();
        %if &unresolved_var >= 10 %then %do;
            data ADSL;
                set DM;
            run;
        %end;
    %mend;
    %test();
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step = res.converted_steps[0]
    assert step.conversion_method == "ManualReviewRequired"
