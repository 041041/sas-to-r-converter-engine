import pytest
import re
from macro_converter import parse_sas_source, classify_macro, convert_macros_to_r
from semantic_conversion_engine import SemanticConversionEngine
from sas_step_converter import SASStepConverter

def test_1_path_a_never_enters_r_functions():
    sas_code = """
    %macro prepare_domain(domain=, source=, out=, minage=18, suffix=FINAL);
        %if &domain=DM %then %do;
            data &out; set &source; run;
        %end;
    %mend;
    %prepare_domain(domain=DM, source=DM, out=ADSL, minage=18, suffix=FINAL);
    """
    parsed = parse_sas_source(sas_code)
    defs = parsed["macro_definitions"]

    assert classify_macro("PREPARE_DOMAIN", defs["PREPARE_DOMAIN"], all_macro_defs=defs) == "PATH_A"

    res = convert_macros_to_r(defs, [], "Modern R (dplyr)")
    assert res["r_functions"] == ""
    assert "prepare_domain" not in res["r_functions"]

def test_2_path_b_reaches_r_functions():
    sas_code = """
    %macro filter_dataset(data=, var=, out=);
        data &out;
            set &data;
            if not missing(&var);
        run;
    %mend;
    """
    parsed = parse_sas_source(sas_code)
    defs = parsed["macro_definitions"]

    assert classify_macro("FILTER_DATASET", defs["FILTER_DATASET"], all_macro_defs=defs) == "PATH_B"

    res = convert_macros_to_r(defs, [], "Modern R (dplyr)")
    assert "filter_dataset <- function" in res["r_functions"]
    assert "data, var, out" in res["r_functions"]

def test_3_mixed_path_a_and_path_b_routing():
    sas_code = """
    %macro filter_dataset(data=, var=, out=);
        data &out;
            set &data;
            if not missing(&var);
        run;
    %mend;

    %macro prepare_domain(domain=, source=, out=);
        %if &domain=DM %then %do;
            data &out; set &source; run;
        %end;
    %mend;
    %prepare_domain(domain=DM, source=DM, out=ADSL);
    """
    parsed = parse_sas_source(sas_code)
    defs = parsed["macro_definitions"]

    assert classify_macro("PREPARE_DOMAIN", defs["PREPARE_DOMAIN"], all_macro_defs=defs) == "PATH_A"
    assert classify_macro("FILTER_DATASET", defs["FILTER_DATASET"], all_macro_defs=defs) == "PATH_B"

    res = convert_macros_to_r(defs, [], "Modern R (dplyr)")
    assert "filter_dataset <- function" in res["r_functions"]
    assert "prepare_domain" not in res["r_functions"]

def test_4_three_repeated_invocations_isolated_frames():
    sas_code = """
    %macro prepare_domain(domain=, source=, out=, minage=18, suffix=FINAL);

        %if &domain=DM %then %do;
            data &out;
                set &source;
                if not missing(USUBJID);
                AGEGRP = '';
                if AGE < 18 then AGEGRP='PEDIATRIC';
                else if AGE < 65 then AGEGRP='ADULT';
                else AGEGRP='OLDER';
                if SEX='' then SEX='U';
                STUDYID = "STUDY01";
            run;
        %end;
        %else %if &domain=AE %then %do;
            data &out;
                set &source;
                if not missing(USUBJID);
                if not missing(AEDECOD);
                if AESEV='MILD' then SEVGRP='LOW';
                else if AESEV='MODERATE' then SEVGRP='MEDIUM';
                else if AESEV='SEVERE' then SEVGRP='HIGH';
                else SEVGRP='UNKNOWN';
                STUDYID = "STUDY01";
            run;
        %end;
        %else %if &domain=LB %then %do;
            data &out;
                set &source;
                if not missing(USUBJID);
                if not missing(LBTESTCD);
                BASELINE = 0;
                if VISITNUM=1 then BASELINE=1;
                STUDYID = "STUDY01";
            run;
        %end;

    %mend;

    %prepare_domain(
        domain=DM,
        source=DM,
        out=ADSL_STUDY01,
        minage=18,
        suffix=FINAL
    );

    %prepare_domain(
        domain=AE,
        source=AE,
        out=ADAE_STUDY01,
        minage=18,
        suffix=FINAL
    );

    %prepare_domain(
        domain=LB,
        source=LB,
        out=ADLB_STUDY01,
        minage=18,
        suffix=FINAL
    );
    """
    engine = SemanticConversionEngine()
    conv = engine.convert_program(sas_code)
    r_code = conv.optimized_r_code

    # Verify isolated parameters per invocation
    assert "ADSL_STUDY01 <- DM" in r_code
    assert "ADAE_STUDY01 <- AE" in r_code
    assert "ADLB_STUDY01 <- LB" in r_code

    # Verify no cross-invocation leakage
    assert "ADSL_STUDY01 <- LB" not in r_code
    assert "ADAE_STUDY01 <- LB" not in r_code
    assert "ADSL_STUDY01 <- AE" not in r_code

    # Verify no residual macro artifacts or TODO comments
    assert "TODO" not in r_code
    prohibited = ["%macro", "%mend", "%let", "%do", "%if", "%then", "%else"]
    for p in prohibited:
        assert p not in r_code

    assert "&&" not in r_code
    assert re.search(r'&\w+', r_code) is None

def test_5_ui_rendering_path_a_only_no_fake_function():
    sas_code = """
    %macro prepare_domain(domain=, source=, out=);
        %if &domain=DM %then %do;
            data &out; set &source; run;
        %end;
    %mend;
    %prepare_domain(domain=DM, source=DM, out=ADSL);
    """
    parsed = parse_sas_source(sas_code)
    defs = parsed["macro_definitions"]
    res = convert_macros_to_r(defs, [], "Modern R (dplyr)")

    assert res["r_functions"] == ""
    assert res["classifications"]["PREPARE_DOMAIN"] == "PATH_A"

def test_live_macro_path_a_ui_integration():
    sas_code = """
    %let study=STUDY01;

    %let ds1=DM;
    %let ds2=AE;
    %let ds3=LB;

    %macro prepare_domain(domain=DM, suffix=FINAL);

        %if &domain=DM %then %do;
            %let source=DM;
            %let keepvars=USUBJID AGE SEX;
        %end;
        %else %if &domain=AE %then %do;
            %let source=AE;
            %let keepvars=USUBJID AEDECOD AESTDTC;
        %end;
        %else %do;
            %let source=LB;
            %let keepvars=USUBJID LBTESTCD VISITNUM;
        %end;

        data &domain._&suffix;
            set &source;
            keep &keepvars;
        run;

    %mend;

    %prepare_domain(domain=DM, suffix=FINAL);
    """
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)

    # A. Macro count >= 1
    assert len(res.ast.macros) >= 1
    assert "PREPARE_DOMAIN" in res.ast.macros

    # B. PREPARE_DOMAIN = PATH_A
    parsed = parse_sas_source(sas_code)
    defs = parsed["macro_definitions"]
    assert classify_macro("PREPARE_DOMAIN", defs["PREPARE_DOMAIN"], all_macro_defs=defs) == "PATH_A"

    # C. Generated reusable R functions = 0
    mac_res = convert_macros_to_r(defs, [], "Modern R (dplyr)")
    assert mac_res["r_functions"] == ""

    # D & E. TODO comments = 0 and residual macro artifacts = 0
    step = res.converted_steps[0]
    r_code = step.optimized_r_code
    assert "TODO" not in r_code
    prohibited = ["%macro", "%mend", "%let", "%do", "%if", "%then", "%else"]
    for p in prohibited:
        assert p not in r_code

    # F & G. DM remains DM, no silent dataset substitution to LB
    assert "DM_FINAL <- DM" in r_code
    assert "DM_FINAL <- LB" not in r_code
    assert "dplyr::select(USUBJID, AGE, SEX)" in r_code

def test_live_nested_macro_execution():
    sas_code = """
    %let study=STUDY01;

    %let ds1=DM;
    %let ds2=AE;
    %let ds3=LB;

    %macro prepare_domain(domain=DM, suffix=FINAL);

        %if &domain=DM %then %do;
            %let source=DM;
            %let keepvars=USUBJID AGE SEX;
        %end;

        %else %if &domain=AE %then %do;
            %let source=AE;
            %let keepvars=USUBJID AEDECOD AESTDTC;
        %end;

        %else %do;
            %let source=LB;
            %let keepvars=USUBJID LBTESTCD VISITNUM;
        %end;

        %macro build_output(prefix=STUDY);

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
    converter = SASStepConverter()
    res = converter.convert_program(sas_code)

    # 1. Macro count from AST >= 2 (PREPARE_DOMAIN and BUILD_OUTPUT)
    assert len(res.ast.macros) >= 2
    assert "PREPARE_DOMAIN" in res.ast.macros
    assert "BUILD_OUTPUT" in res.ast.macros

    # 2. Both macros classified as PATH_A
    parsed = parse_sas_source(sas_code)
    defs = parsed["macro_definitions"]
    assert classify_macro("PREPARE_DOMAIN", defs["PREPARE_DOMAIN"], all_macro_defs=defs) == "PATH_A"
    assert classify_macro("BUILD_OUTPUT", defs["BUILD_OUTPUT"], all_macro_defs=defs) == "PATH_A"

    # 3. 0 reusable R functions generated
    mac_res = convert_macros_to_r(defs, parsed["macro_calls"], dialect="Modern R (dplyr)")
    assert mac_res["r_functions"] == ""

    # 4. 3 converted steps with exact dataset inputs
    assert len(res.converted_steps) == 3
    s1 = res.converted_steps[0].optimized_r_code
    s2 = res.converted_steps[1].optimized_r_code
    s3 = res.converted_steps[2].optimized_r_code

    assert "STUDY01_DM_1_FINAL <- DM" in s1
    assert "STUDY01_DM_2_FINAL <- AE" in s2
    assert "STUDY01_DM_3_FINAL <- LB" in s3

    # 5. No TODOs, no residual macro tokens, no incorrect LB substitution
    prohibited = ["%macro", "%mend", "%let", "%do", "%if", "%then", "%else"]
    for s in (s1, s2, s3):
        assert "TODO" not in s
        for p in prohibited:
            assert p not in s
        assert "&&" not in s
        assert "select(USUBJID, AGE, SEX)" in s
