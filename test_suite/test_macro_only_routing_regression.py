"""
test_suite/test_macro_only_routing_regression.py
─────────────────────────────────────────────────
Regression tests for Phase 9.21: Macro-only and Large Macro pipeline routing.
Ensures valid SAS macro sources pass preflight classification without throwing
'No valid SAS steps found'.
"""

import pytest
from app import is_meaningful_sas_source
from macro_converter import parse_sas_source, convert_macros_to_r
from sas_step_converter import SASStepConverter

def test_macro_only_source_classification():
    sas_code = """
    %macro calc_summary(data=, out=);
        proc summary data=&data;
            var age;
            output out=&out sum=;
        run;
    %mend calc_summary;
    """
    parsed = parse_sas_source(sas_code)
    assert len(parsed["macro_definitions"]) == 1
    assert "CALC_SUMMARY" in parsed["macro_definitions"]
    assert is_meaningful_sas_source(sas_code, parsed) is True

def test_large_macro_only_source():
    sas_code = """
    /* Complex Clinical Enterprise Macro Library */
    %macro process_sdtm(in_ds=, out_ds=, filter_var=, filter_val=);
        %local i num_vars;
        %let num_vars = %sysfunc(countw(&filter_var));

        %if %sysfunc(exist(&in_ds)) %then %do;
            proc sort data=&in_ds out=WORK.tmp_sorted;
                by USUBJID;
            run;

            proc sql;
                create table &out_ds as
                select a.*, b.AGE, b.SEX
                from WORK.tmp_sorted a
                left join WORK.DM b
                on a.USUBJID = b.USUBJID
                where a.&filter_var = "&filter_val";
            quit;
        %end;
    %mend process_sdtm;

    %macro generate_qc_report(ds=, qc_out=);
        proc freq data=&ds;
            tables SEX * AGE / out=&qc_out;
        run;
    %mend generate_qc_report;
    """
    parsed = parse_sas_source(sas_code)
    assert len(parsed["macro_definitions"]) == 2
    assert "PROCESS_SDTM" in parsed["macro_definitions"]
    assert "GENERATE_QC_REPORT" in parsed["macro_definitions"]
    assert is_meaningful_sas_source(sas_code, parsed) is True

    mres = convert_macros_to_r(parsed["macro_definitions"], parsed.get("macro_calls", []), "Modern R (tidyverse)")
    assert "r_functions" in mres
    assert len(mres["r_functions"]) > 0

def test_macro_with_data_step_inside():
    sas_code = """
    %macro transform_data(indata=, outdata=);
        data &outdata;
            set &indata;
            if age >= 18 then adult = 1;
            else adult = 0;
        run;
    %mend transform_data;
    """
    parsed = parse_sas_source(sas_code)
    assert "TRANSFORM_DATA" in parsed["macro_definitions"]
    assert is_meaningful_sas_source(sas_code, parsed) is True

def test_macro_with_proc_sql_inside():
    sas_code = """
    %macro run_sql_query(table=);
        proc sql;
            create table WORK.summary as
            select count(*) as N, avg(VAL) as MEAN
            from &table;
        quit;
    %mend run_sql_query;
    """
    parsed = parse_sas_source(sas_code)
    assert "RUN_SQL_QUERY" in parsed["macro_definitions"]
    assert is_meaningful_sas_source(sas_code, parsed) is True

def test_nested_macros():
    sas_code = """
    %macro inner_tool(val=);
        %let double_val = %eval(&val * 2);
    %mend inner_tool;

    %macro outer_wrapper(in=, out=);
        %inner_tool(val=10);
        data &out;
            set &in;
        run;
    %mend outer_wrapper;
    """
    parsed = parse_sas_source(sas_code)
    assert "INNER_TOOL" in parsed["macro_definitions"]
    assert "OUTER_WRAPPER" in parsed["macro_definitions"]
    assert is_meaningful_sas_source(sas_code, parsed) is True

def test_macro_library_without_invocation():
    sas_code = """
    %macro lib_func_1();
        %put Lib 1 executed;
    %mend lib_func_1;

    %macro lib_func_2();
        %put Lib 2 executed;
    %mend lib_func_2;
    """
    parsed = parse_sas_source(sas_code)
    assert len(parsed["macro_definitions"]) == 2
    assert len(parsed["macro_calls"]) == 0
    assert is_meaningful_sas_source(sas_code, parsed) is True

def test_mixed_macro_and_executable_program():
    sas_code = """
    %macro calc(x=);
        data WORK.TMP;
            val = &x;
        run;
    %mend calc;

    data WORK.FINAL;
        set SDTM.DM;
    run;
    """
    parsed = parse_sas_source(sas_code)
    assert "CALC" in parsed["macro_definitions"]
    assert is_meaningful_sas_source(sas_code, parsed) is True

def test_invalid_empty_source():
    assert is_meaningful_sas_source("", None) is False
    assert is_meaningful_sas_source("   \n\t ", None) is False
    assert is_meaningful_sas_source("/* Just a comment block */", None) is False
    assert is_meaningful_sas_source("random non sas text without keywords", None) is False

def test_no_valid_sas_steps_found_error_not_thrown_for_macro_only():
    sas_code = """
    %macro office_macro_library();
        proc print data=WORK.TEST;
        run;
    %mend office_macro_library;
    """
    parsed = parse_sas_source(sas_code)
    assert is_meaningful_sas_source(sas_code, parsed) is True
    converter = SASStepConverter(dialect="Modern R (tidyverse)")
    conv_result = converter.convert_program(sas_code)
    assert conv_result is not None
    assert conv_result.full_optimized_r is not None
