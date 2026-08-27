import pytest
import re
from macro_converter import parse_sas_source, classify_macro
from semantic_conversion_engine import SemanticConversionEngine

def test_1_nested_path_a_child_propagates_to_parent():
    sas = """
    %macro parent();
        %macro child();
            %do i=1 %to 2;
                data OUT&i; set DM; run;
            %end;
        %mend;
        %child;
    %mend;
    """
    parsed = parse_sas_source(sas)
    defs = parsed['macro_definitions']
    assert classify_macro('CHILD', defs['CHILD'], all_macro_defs=defs) == 'PATH_A'
    assert classify_macro('PARENT', defs['PARENT'], all_macro_defs=defs) == 'PATH_A'

def test_2_nested_path_a_with_do_and_amp():
    sas = """
    %let ds1=DM; %let ds2=AE;
    %macro outer();
        %macro inner();
            %do i=1 %to 2;
                data OUT&i; set &&ds&i; run;
            %end;
        %mend;
        %inner;
    %mend;
    """
    parsed = parse_sas_source(sas)
    defs = parsed['macro_definitions']
    assert classify_macro('INNER', defs['INNER'], all_macro_defs=defs) == 'PATH_A'
    assert classify_macro('OUTER', defs['OUTER'], all_macro_defs=defs) == 'PATH_A'

def test_3_nested_path_a_with_dynamic_data_names():
    sas = """
    %macro main(prefix=STUDY);
        %macro make_ds(name=DM);
            data &prefix._&name; set &name; run;
        %mend;
        %make_ds(name=DM);
    %mend;
    """
    parsed = parse_sas_source(sas)
    defs = parsed['macro_definitions']
    assert classify_macro('MAIN', defs['MAIN'], all_macro_defs=defs) == 'PATH_A'

def test_4_nested_path_b_utility_remains_path_b():
    sas = """
    %macro outer_util(data=DM, var=AGE);
        %macro helper_util(data=, var=);
            data OUT; set &data; if not missing(&var); run;
        %mend;
        %helper_util(data=&data, var=&var);
    %mend;
    """
    parsed = parse_sas_source(sas)
    defs = parsed['macro_definitions']
    assert classify_macro('HELPER_UTIL', defs['HELPER_UTIL'], all_macro_defs=defs) == 'PATH_B'
    assert classify_macro('OUTER_UTIL', defs['OUTER_UTIL'], all_macro_defs=defs) == 'PATH_B'

def test_5_parent_path_a_and_child_path_a():
    sas = """
    %macro p_a();
        %do j=1 %to 2;
            %macro c_a();
                %do i=1 %to 2;
                    data OUT&i; set DM; run;
                %end;
            %mend;
            %c_a;
        %end;
    %mend;
    """
    parsed = parse_sas_source(sas)
    defs = parsed['macro_definitions']
    assert classify_macro('C_A', defs['C_A'], all_macro_defs=defs) == 'PATH_A'
    assert classify_macro('P_A', defs['P_A'], all_macro_defs=defs) == 'PATH_A'

def test_6_parent_path_b_and_child_path_b():
    sas = """
    %macro p_b(data=DM);
        %macro c_b(data=);
            data OUT; set &data; run;
        %mend;
        %c_b(data=&data);
    %mend;
    """
    parsed = parse_sas_source(sas)
    defs = parsed['macro_definitions']
    assert classify_macro('C_B', defs['C_B'], all_macro_defs=defs) == 'PATH_B'
    assert classify_macro('P_B', defs['P_B'], all_macro_defs=defs) == 'PATH_B'

def test_7_mixed_ambiguous_nested_macro_safe_reject():
    sas = """
    %macro p_unsafe(x=1);
        %macro c_unsafe(x=);
            %let val = %eval(&x + 1);
        %mend;
        %c_unsafe(x=&x);
    %mend;
    """
    parsed = parse_sas_source(sas)
    defs = parsed['macro_definitions']
    assert classify_macro('C_UNSAFE', defs['C_UNSAFE'], all_macro_defs=defs) == 'SAFE_REJECT'
    assert classify_macro('P_UNSAFE', defs['P_UNSAFE'], all_macro_defs=defs) == 'SAFE_REJECT'

def test_8_reproduction_no_unresolved_macro_artifacts():
    sas_code = """
    %let study=STUDY01;
    %let ds1=DM;
    %let ds2=AE;

    %macro prepare_domain(domain=DM, suffix=FINAL);

        %if &domain=DM %then %do;
            %let keepvars=USUBJID AGE SEX;
        %end;
        %else %do;
            %let keepvars=USUBJID AEDECOD AESTDTC;
        %end;

        %macro build_output(prefix=STUDY);

            %do i=1 %to 2;

                data &prefix._&domain._&i._&suffix;
                    set &&ds&i;
                    keep &keepvars;
                    if not missing(USUBJID);
                run;

            %end;

        %mend build_output;

        %build_output(prefix=&study);

    %mend prepare_domain;

    %prepare_domain(domain=DM, suffix=FINAL);
    """
    engine = SemanticConversionEngine()
    res = engine.convert_program(sas_code)
    r_code = res.optimized_r_code
    
    assert re.search(r'%(?:macro|mend|let|do|if|then|else|sysfunc)', r_code, re.I) is None
    assert "&&" not in r_code
    assert re.search(r'&\w+', r_code) is None

def test_9_reproduction_no_todo_comments():
    sas_code = """
    %let study=STUDY01;
    %let ds1=DM;
    %let ds2=AE;

    %macro prepare_domain(domain=DM, suffix=FINAL);

        %if &domain=DM %then %do;
            %let keepvars=USUBJID AGE SEX;
        %end;

        %macro build_output(prefix=STUDY);

            %do i=1 %to 2;

                data &prefix._&domain._&i._&suffix;
                    set &&ds&i;
                    if not missing(USUBJID);
                run;

            %end;

        %mend build_output;

        %build_output(prefix=&study);

    %mend prepare_domain;

    %prepare_domain(domain=DM, suffix=FINAL);
    """
    engine = SemanticConversionEngine()
    res = engine.convert_program(sas_code)
    r_code = res.optimized_r_code
    assert "TODO" not in r_code

def test_10_reproduction_data_steps_reach_rule_engine():
    sas_code = """
    %let study=STUDY01;
    %let ds1=DM;
    %let ds2=AE;

    %macro prepare_domain(domain=DM, suffix=FINAL);

        %if &domain=DM %then %do;
            %let keepvars=USUBJID AGE SEX;
        %end;

        %macro build_output(prefix=STUDY);

            %do i=1 %to 2;

                data &prefix._&domain._&i._&suffix;
                    set &&ds&i;
                    if not missing(USUBJID);
                run;

            %end;

        %mend build_output;

        %build_output(prefix=&study);

    %mend prepare_domain;

    %prepare_domain(domain=DM, suffix=FINAL);
    """
    engine = SemanticConversionEngine()
    res = engine.convert_program(sas_code)
    r_code = res.optimized_r_code
    
    assert "STUDY01_DM_1_FINAL <- DM" in r_code
    assert "STUDY01_DM_2_FINAL <- AE" in r_code
