"""
Phase 8.47 Macros Detected Metric Regression Test
"""

import pytest
from sas_step_converter import SASStepConverter
from macro_processor import SASMacroProcessor
from macro_converter import parse_sas_source, classify_macro


def test_phase8_47_single_path_b_macro_detected_metric():
    sas_b = """
%macro filter_dataset(data=, var=, out=);
    data &out;
        set &data;
        if not missing(&var);
    run;
%mend;

%filter_dataset(data=DM, var=USUBJID, out=DM_CLEAN);
%filter_dataset(data=AE, var=AEDECOD, out=AE_CLEAN);
"""
    parsed = parse_sas_source(sas_b)
    m_defs = parsed["macro_definitions"]

    proc = SASMacroProcessor()
    unexp_sas, _, _ = proc.process(sas_b, expand_path_b=False)

    converter = SASStepConverter(dialect="Modern R (dplyr)")
    res_b = converter.convert_program(unexp_sas, raw_sas_code=sas_b)

    # Metric assertion: 1 macro detected
    assert len(res_b.ast.macros) == 1
    assert "FILTER_DATASET" in res_b.ast.macros

    # Step conversion & program call assertions
    assert len(res_b.converted_steps) == 2
    assert "DM_CLEAN <- filter_dataset(DM, \"USUBJID\")" in res_b.converted_steps[0].optimized_r_code
    assert "AE_CLEAN <- filter_dataset(AE, \"AEDECOD\")" in res_b.converted_steps[1].optimized_r_code


def test_phase8_47_two_nested_path_a_macros_detected_metric():
    sas_a = """
%let study=STUDY01;
%let ds1=DM; %let ds2=AE; %let ds3=LB;

%macro prepare_domain(domain=DM, suffix=FINAL);
    %if &domain=DM %then %do;
        %let keepvars=USUBJID AGE SEX;
    %end;
    %macro build_output(prefix=STUDY01);
        %do i=1 %to 3;
            data &prefix._&domain._&i._&suffix;
                set &&ds&i;
                keep &keepvars;
                if not missing(USUBJID);
            run;
        %end;
    %mend;
    %build_output(prefix=&study);
%mend;

%prepare_domain(domain=DM, suffix=FINAL);
"""
    converter = SASStepConverter(dialect="Modern R (dplyr)")
    res_a = converter.convert_program(sas_a)

    # Metric assertion: 2 nested macros detected
    assert len(res_a.ast.macros) == 2
    macro_names = list(res_a.ast.macros.keys())
    assert "PREPARE_DOMAIN" in macro_names
    assert "BUILD_OUTPUT" in macro_names
    assert len(res_a.converted_steps) == 3
