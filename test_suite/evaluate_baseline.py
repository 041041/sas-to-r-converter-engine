"""
evaluate_baseline.py
────────────────────
Evaluates simple SAS conversion and complex SAS macro conversion against the rolled-back baseline commit ffc5268.
Records exact initial & optimized R output produced.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from semantic_conversion_engine import SemanticConversionEngine

SIMPLE_SAS = """
data adsl;
    set sdtm.dm;
    if age >= 18;
run;
"""

COMPLEX_SAS_MACRO = """
libname SDTM "/clinical/data/sdtm";
libname ADAM "/clinical/data/adam";
filename setup "/clinical/config/setup.sas";
%include setup;

%let study = CLINICAL_ABC;
%let today = %sysfunc(today(), yymmddn8.);
%let ds1 = DM;
%let ds2 = AE;
%let ds3 = EX;

%macro build_clinical_pipeline(sdtm_lib=SDTM, adam_lib=ADAM, min_age=18);
    %local i current_ds;
    
    /* 1. ADSL Base Step */
    data &adam_lib..adsl;
        set &sdtm_lib..&ds1;
        if age >= &min_age;
    run;

    /* 2. EX_SUM Exposure Aggregation Step */
    proc sql;
        create table &adam_lib..ex_sum as
        select usubjid,
               count(*) as exposure_records,
               sum(dose) as total_dose,
               mean(dose) as avg_dose
        from &sdtm_lib..&ds3
        group by usubjid;
    quit;

    /* 3. ADAE_SUM Adverse Event Aggregation Step */
    proc sql;
        create table &adam_lib..adae_sum as
        select usubjid,
               count(*) as ae_count
        from &sdtm_lib..&ds2
        group by usubjid;
    quit;

    /* 4. ADSL_FINAL Multi-Join Step */
    proc sql;
        create table &adam_lib..adsl_final as
        select a.*, b.ae_count, c.total_dose
        from &adam_lib..adsl a
        left join &adam_lib..adae_sum b on a.usubjid = b.usubjid
        left join &adam_lib..ex_sum c on a.usubjid = c.usubjid;
    quit;

    /* 5. ADSL_SORTED Sort Step */
    proc sort data=&adam_lib..adsl_final out=&adam_lib..adsl_sorted;
        by usubjid;
    run;
%mend build_clinical_pipeline;

/* Invoke Clinical Macro */
%build_clinical_pipeline(sdtm_lib=SDTM, adam_lib=ADAM, min_age=18);
"""


def evaluate():
    engine = SemanticConversionEngine(dialect="Modern R (tidyverse)")

    print("==================================================")
    print("1. SIMPLE SAS CONVERSION RESULT")
    print("==================================================")
    simple_res = engine.convert_program(SIMPLE_SAS, program_name="Simple_Data_Step")
    print("--- Initial R ---")
    print(simple_res.initial_r_code)
    print("\n--- Optimized R ---")
    print(simple_res.optimized_r_code)
    print(f"\nConversion Confidence: {simple_res.confidence_report.conversion_confidence}%")

    print("\n==================================================")
    print("2. COMPLEX MACRO BENCHMARK RESULT")
    print("==================================================")
    complex_res = engine.convert_program(COMPLEX_SAS_MACRO, program_name="Gold_Clinical_Benchmark")
    print("--- Initial R ---")
    print(complex_res.initial_r_code)
    print("\n--- Optimized R ---")
    print(complex_res.optimized_r_code)
    print(f"\nConversion Confidence: {complex_res.confidence_report.conversion_confidence}%")


if __name__ == "__main__":
    evaluate()
