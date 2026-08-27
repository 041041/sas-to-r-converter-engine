"""
test_sas_macro_parameters.py
─────────────────────────────
Phase 8.6 Focused Test Suite for SAS Macro %LET and Parameter Support.
"""

import pytest
from macro_processor import SASMacroProcessor
from sas_step_converter import SASStepConverter


def test_1_global_let_variable():
    sas_code = """
    %let threshold=65;
    data ADSL;
        set DM;
        if AGE >= &threshold then FLAG='Y';
    run;
    """
    processor = SASMacroProcessor()
    expanded, warnings, _ = processor.process(sas_code)
    assert "65" in expanded
    assert "&threshold" not in expanded

    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    assert len(res.converted_steps) == 1
    step_res = res.converted_steps[0]
    assert step_res.conversion_method.startswith("Rule_")
    assert "65" in step_res.optimized_r_code


def test_2_keyword_parameters():
    sas_code = """
    %macro flag(ds=DM, out=ADSL);
        data &out;
            set &ds;
        run;
    %mend;

    %flag(ds=AE, out=ADAE);
    """
    processor = SASMacroProcessor()
    expanded, warnings, _ = processor.process(sas_code)
    assert "data ADAE;" in expanded
    assert "set AE;" in expanded

    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    assert len(res.converted_steps) == 1
    step_res = res.converted_steps[0]
    assert step_res.conversion_method.startswith("Rule_")
    assert "ADAE <- AE" in step_res.optimized_r_code


def test_3_default_parameters():
    sas_code = """
    %macro flag(ds=DM, out=ADSL);
        data &out;
            set &ds;
        run;
    %mend;

    %flag();
    """
    processor = SASMacroProcessor()
    expanded, warnings, _ = processor.process(sas_code)
    assert "data ADSL;" in expanded
    assert "set DM;" in expanded

    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    assert len(res.converted_steps) == 1
    step_res = res.converted_steps[0]
    assert step_res.conversion_method.startswith("Rule_")
    assert "ADSL <- DM" in step_res.optimized_r_code


def test_4_positional_parameters():
    sas_code = """
    %macro flag(ds, out);
        data &out;
            set &ds;
        run;
    %mend;

    %flag(DM, ADSL);
    """
    processor = SASMacroProcessor()
    expanded, warnings, _ = processor.process(sas_code)
    assert "data ADSL;" in expanded
    assert "set DM;" in expanded

    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    assert len(res.converted_steps) == 1
    step_res = res.converted_steps[0]
    assert step_res.conversion_method.startswith("Rule_")
    assert "ADSL <- DM" in step_res.optimized_r_code


def test_5_multiple_let_variables():
    sas_code = """
    %let source=DM;
    %let target=ADSL;

    data &target;
        set &source;
    run;
    """
    processor = SASMacroProcessor()
    expanded, warnings, _ = processor.process(sas_code)
    assert "data ADSL;" in expanded
    assert "set DM;" in expanded

    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    assert len(res.converted_steps) == 1
    step_res = res.converted_steps[0]
    assert step_res.conversion_method.startswith("Rule_")
    assert "ADSL <- DM" in step_res.optimized_r_code


def test_6_missing_required_parameter_safe_reject():
    sas_code = """
    %macro flag(ds, out);
        data &out;
            set &ds;
        run;
    %mend;

    %flag(DM);
    """
    processor = SASMacroProcessor()
    expanded, warnings, _ = processor.process(sas_code)
    assert any("Missing required parameter" in w for w in warnings)
    assert "%flag(DM);" in expanded

    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step_res = res.converted_steps[0]
    assert step_res.conversion_method == "ManualReviewRequired"


def test_7_unknown_macro_variable_safe_reject():
    sas_code = """
    data ADSL;
        set DM;
        if AGE >= &unknown_var then FLAG='Y';
    run;
    """
    processor = SASMacroProcessor()
    expanded, warnings, _ = processor.process(sas_code)
    assert any("Unresolved macro variable" in w for w in warnings)
    assert "&unknown_var" in expanded or "&UNKNOWN_VAR" in expanded

    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step_res = res.converted_steps[0]
    assert step_res.conversion_method == "ManualReviewRequired"


def test_8_indirect_reference_safe_reject():
    sas_code = """
    %let prefix=DM;
    data ADSL;
        set &&prefix;
    run;
    """
    processor = SASMacroProcessor()
    expanded, warnings, _ = processor.process(sas_code)
    assert any("Indirect macro variable reference" in w for w in warnings)

    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    step_res = res.converted_steps[0]
    assert step_res.conversion_method == "ManualReviewRequired"


def test_9_recursive_macro_safe_reject():
    sas_code = """
    %macro rec(n);
        %rec(&n);
    %mend;

    %rec(5);
    """
    processor = SASMacroProcessor()
    expanded, warnings, _ = processor.process(sas_code)
    assert any("Recursive call to macro" in w for w in warnings)

    converter = SASStepConverter()
    res = converter.convert_program(sas_code)
    assert len(res.converted_steps) == 0 or res.converted_steps[0].conversion_method == "ManualReviewRequired"
