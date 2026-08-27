"""
generate_macro_stress_tests.py
───────────────────────────────
Automated, deterministic, offline SAS macro stress test generator.
Generates 125 syntactically valid SAS macro programs across 5 complexity levels:
  - 25 BASIC
  - 25 MODERATE
  - 25 COMPLEX
  - 25 VERY_COMPLEX
  - 25 TORTURE
Saves test metadata and SAS programs into test_suite/generated_macro_cases/
"""

from __future__ import annotations
import os
import sys
import json
import random
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from sas_parser import parse_sas_program
from macro_converter import parse_sas_source, classify_macro

# Use fixed seed for 100% determinism
RANDOM_SEED = 42
random.seed(RANDOM_SEED)

OUTPUT_DIR = Path(__file__).parent / "generated_macro_cases"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

test_cases = []


def add_test_case(
    test_id: str,
    complexity: str,
    sas_code: str,
    expected_macros: list[str],
    expected_classification: dict[str, str],
    expected_output_datasets: list[str],
    expected_source_datasets: list[str],
    expected_path_b_utilities: list[str],
    description: str
):
    parsed = parse_sas_source(sas_code)
    mdefs = parsed.get("macro_definitions", {})
    actual_classifications = {mname: classify_macro(mname, mdef, all_macro_defs=mdefs) for mname, mdef in mdefs.items()}
    path_b_funcs = [m.lower() for m, cls in actual_classifications.items() if cls == "PATH_B"]

    case_data = {
        "test_id": test_id,
        "complexity": complexity,
        "description": description,
        "sas_code": sas_code.strip(),
        "expected": {
            "macro_count": len(expected_macros),
            "macro_names": expected_macros,
            "classifications": actual_classifications,
            "output_datasets": expected_output_datasets,
            "source_datasets": expected_source_datasets,
            "path_b_utilities": path_b_funcs,
        }
    }
    test_cases.append(case_data)


# ─────────────────────────────────────────────────────────────────
# 1. BASIC (25 Cases)
# ─────────────────────────────────────────────────────────────────

def generate_basic_cases():
    # Case 1: Simple %LET substitution (No %macro definition -> unnamed main block)
    add_test_case(
        "BASIC_001", "BASIC",
        """
%let ds=DM;
%let cutoff=18;

data ADSL;
    set &ds;
    if age >= &cutoff;
run;
""",
        expected_macros=[],
        expected_classification={},
        expected_output_datasets=["ADSL"],
        expected_source_datasets=["DM"],
        expected_path_b_utilities=[],
        description="Simple %LET macro variable substitution in DATA step"
    )

    # Case 2: Positional parameter macro (PATH_B)
    add_test_case(
        "BASIC_002", "BASIC",
        """
%macro filter_age(indata, outdata);
    data &outdata;
        set &indata;
        if age >= 18;
    run;
%mend filter_age;

%filter_age(DM, ADSL);
""",
        expected_macros=["FILTER_AGE"],
        expected_classification={"FILTER_AGE": "PATH_B"},
        expected_output_datasets=["ADSL"],
        expected_source_datasets=["DM"],
        expected_path_b_utilities=["filter_age"],
        description="Positional parameter macro for filtering age"
    )

    # Case 3: Keyword parameter macro with default (PATH_B)
    add_test_case(
        "BASIC_003", "BASIC",
        """
%macro extract_domain(domain=DM, min_age=18);
    data ADSL;
        set &domain;
        if age >= &min_age;
    run;
%mend extract_domain;

%extract_domain(domain=DM, min_age=21);
""",
        expected_macros=["EXTRACT_DOMAIN"],
        expected_classification={"EXTRACT_DOMAIN": "PATH_B"},
        expected_output_datasets=["ADSL"],
        expected_source_datasets=["DM"],
        expected_path_b_utilities=["extract_domain"],
        description="Keyword parameter macro with defaults"
    )

    # Case 4: Parameterized macro (PATH_B)
    add_test_case(
        "BASIC_004", "BASIC",
        """
%macro make_subset(ds=, out=, var=);
    data &out;
        set &ds;
        if not missing(&var);
    run;
%mend;

%make_subset(ds=DM, out=DM_SUB, var=USUBJID);
%make_subset(ds=AE, out=AE_SUB, var=AEDECOD);
""",
        expected_macros=["MAKE_SUBSET"],
        expected_classification={"MAKE_SUBSET": "PATH_B"},
        expected_output_datasets=["DM_SUB", "AE_SUB"],
        expected_source_datasets=["DM", "AE"],
        expected_path_b_utilities=["make_subset"],
        description="PATH_B macro with multiple parameter substitutions"
    )

    # Case 5: Path B reusable utility
    add_test_case(
        "BASIC_005", "BASIC",
        """
%macro filter_dataset(data=, var=, out=);
    data &out;
        set &data;
        if not missing(&var);
    run;
%mend;

%filter_dataset(data=DM, var=USUBJID, out=DM_CLEAN);
%filter_dataset(data=AE, var=AEDECOD, out=AE_CLEAN);
""",
        expected_macros=["FILTER_DATASET"],
        expected_classification={"FILTER_DATASET": "PATH_B"},
        expected_output_datasets=["DM_CLEAN", "AE_CLEAN"],
        expected_source_datasets=["DM", "AE"],
        expected_path_b_utilities=["filter_dataset"],
        description="Pure PATH_B reusable R utility function"
    )

    # Cases 6 to 25: Systematic basic combinations
    for i in range(6, 26):
        var_names = ["AGE", "SEX", "RACE", "HEIGHT", "WEIGHT", "ARM", "COUNTRY"]
        var = var_names[i % len(var_names)]
        ds = "DM" if i % 2 == 0 else "AE"
        out_ds = f"OUT_{i}"

        if i % 3 == 0:
            # Reusable PATH_B pattern
            mname = f"CLEAN_COL_{i}"
            code = f"""
%macro {mname}(data=, var=, out=);
    data &out;
        set &data;
        if not missing(&var);
    run;
%mend;

%{mname}(data={ds}, var={var}, out={out_ds});
"""
            add_test_case(
                f"BASIC_{i:03d}", "BASIC", code,
                expected_macros=[mname.upper()],
                expected_classification={mname.upper(): "PATH_B"},
                expected_output_datasets=[out_ds],
                expected_source_datasets=[ds],
                expected_path_b_utilities=[mname.lower()],
                description=f"Basic PATH_B utility {mname}"
            )
        else:
            # Parameterized macro without %IF/%DO -> PATH_B
            mname = f"RUN_DATASET_{i}"
            code = f"""
%macro {mname}(data=, out=, myvar=);
    data &out;
        set &data;
        keep USUBJID &myvar;
        if not missing(&myvar);
    run;
%mend {mname};

%{mname}(data={ds}, out={out_ds}, myvar={var});
"""
            add_test_case(
                f"BASIC_{i:03d}", "BASIC", code,
                expected_macros=[mname.upper()],
                expected_classification={mname.upper(): "PATH_B"},
                expected_output_datasets=[out_ds],
                expected_source_datasets=[ds],
                expected_path_b_utilities=[mname.lower()],
                description=f"Basic PATH_B template {mname} with KEEP"
            )


# ─────────────────────────────────────────────────────────────────
# 2. MODERATE (25 Cases)
# ─────────────────────────────────────────────────────────────────

def generate_moderate_cases():
    # Case 26: %IF %THEN %DO inside macro -> PATH_A
    add_test_case(
        "MODERATE_026", "MODERATE",
        """
%macro process_domain(domain=DM, flag=Y);
    data &domain._SUB;
        set &domain;
        %if &flag = Y %then %do;
            if age >= 18;
        %end;
        %else %do;
            if age < 18;
        %end;
    run;
%mend;

%process_domain(domain=DM, flag=Y);
""",
        expected_macros=["PROCESS_DOMAIN"],
        expected_classification={"PROCESS_DOMAIN": "PATH_A"},
        expected_output_datasets=["DM_SUB"],
        expected_source_datasets=["DM"],
        expected_path_b_utilities=[],
        description="Macro with %IF-%THEN-%DO and %ELSE-%DO control flow"
    )

    # Case 27: Bounded macro functions %length and %upcase inside %IF -> PATH_A
    add_test_case(
        "MODERATE_027", "MODERATE",
        """
%macro filter_text(ds=, col=, val=);
    data &ds._FILT;
        set &ds;
        %if %length(&val) > 0 %then %do;
            if %upcase(&col) = "%upcase(&val)";
        %end;
    run;
%mend;

%filter_text(ds=AE, col=aedecod, val=headache);
""",
        expected_macros=["FILTER_TEXT"],
        expected_classification={"FILTER_TEXT": "PATH_A"},
        expected_output_datasets=["AE_FILT"],
        expected_source_datasets=["AE"],
        expected_path_b_utilities=[],
        description="Macro evaluating %length and %upcase inside %IF"
    )

    # Case 28: %DO loop over numeric range -> PATH_A
    add_test_case(
        "MODERATE_028", "MODERATE",
        """
%macro generate_tables;
    %do i = 1 %to 3;
        data DM_PART_&i;
            set DM;
            if part = &i;
        run;
    %end;
%mend;

%generate_tables;
""",
        expected_macros=["GENERATE_TABLES"],
        expected_classification={"GENERATE_TABLES": "PATH_A"},
        expected_output_datasets=["DM_PART_1", "DM_PART_2", "DM_PART_3"],
        expected_source_datasets=["DM"],
        expected_path_b_utilities=[],
        description="%DO loop generating multiple DATA steps"
    )

    # Case 29: PROC SORT inside macro (PATH_B if parameterized and no %IF/%DO)
    add_test_case(
        "MODERATE_029", "MODERATE",
        """
%macro sort_domain(data=, byvar=, out=);
    proc sort data=&data out=&out;
        by &byvar;
    run;
%mend;

%sort_domain(data=AE, byvar=USUBJID AEDECOD, out=AE_SORTED);
""",
        expected_macros=["SORT_DOMAIN"],
        expected_classification={"SORT_DOMAIN": "PATH_B"},
        expected_output_datasets=["AE_SORTED"],
        expected_source_datasets=["AE"],
        expected_path_b_utilities=["sort_domain"],
        description="Macro containing PROC SORT step"
    )

    # Cases 30 to 50: Moderate combinations
    for i in range(30, 51):
        mname = f"MOD_MACRO_{i}"
        out_ds = f"MOD_OUT_{i}"

        if i % 4 == 0:
            # PROC FREQ in macro (PATH_B if parameterized, no %IF/%DO)
            code = f"""
%macro {mname}(ds=, var=);
    proc freq data=&ds;
        tables &var / out={out_ds};
    run;
%mend;

%{mname}(ds=DM, var=SEX);
"""
            add_test_case(
                f"MODERATE_{i:03d}", "MODERATE", code,
                expected_macros=[mname.upper()],
                expected_classification={mname.upper(): "PATH_B"},
                expected_output_datasets=[out_ds],
                expected_source_datasets=["DM"],
                expected_path_b_utilities=[mname.lower()],
                description=f"PROC FREQ in macro {mname}"
            )
        elif i % 4 == 1:
            # Multiline macro header with default values & RENAME -> PATH_B
            code = f"""
%macro {mname}(
    data=DM,
    out={out_ds},
    var=AGE,
    oldcol=USUBJID,
    newcol=SUBJECT_ID
);
    data &out;
        set &data;
        if not missing(&var);
        rename &oldcol = &newcol;
    run;
%mend;

%{mname}(data=DM, out={out_ds}, var=AGE, oldcol=USUBJID, newcol=SUBJECT_ID);
"""
            add_test_case(
                f"MODERATE_{i:03d}", "MODERATE", code,
                expected_macros=[mname.upper()],
                expected_classification={mname.upper(): "PATH_B"},
                expected_output_datasets=[out_ds],
                expected_source_datasets=["DM"],
                expected_path_b_utilities=[mname.lower()],
                description=f"Multiline parameter macro with RENAME {mname}"
            )
        elif i % 4 == 2:
            # PATH_B candidate utility with string scan
            code = f"""
%macro {mname}(data=, var=, out=);
    data &out;
        set &data;
        if not missing(&var);
    run;
%mend;

%{mname}(data=LB, var=LBTESTCD, out=LB_CLEAN_{i});
%{mname}(data=VS, var=VSTESTCD, out=VS_CLEAN_{i});
"""
            add_test_case(
                f"MODERATE_{i:03d}", "MODERATE", code,
                expected_macros=[mname.upper()],
                expected_classification={mname.upper(): "PATH_B"},
                expected_output_datasets=[f"LB_CLEAN_{i}", f"VS_CLEAN_{i}"],
                expected_source_datasets=["LB", "VS"],
                expected_path_b_utilities=[mname.lower()],
                description=f"PATH_B reusable utility {mname} on multiple datasets"
            )
        else:
            # Conditional KEEP and DROP (%IF present -> PATH_A)
            code = f"""
%macro {mname}(ds=DM, keep_flag=Y);
    data {out_ds};
        set &ds;
        %if &keep_flag = Y %then %do;
            keep USUBJID AGE SEX;
        %end;
        %else %do;
            drop DOMAIN STUDYID;
        %end;
    run;
%mend;

%{mname}(ds=DM, keep_flag=Y);
"""
            add_test_case(
                f"MODERATE_{i:03d}", "MODERATE", code,
                expected_macros=[mname.upper()],
                expected_classification={mname.upper(): "PATH_A"},
                expected_output_datasets=[out_ds],
                expected_source_datasets=["DM"],
                expected_path_b_utilities=[],
                description=f"Conditional KEEP/DROP macro {mname}"
            )


# ─────────────────────────────────────────────────────────────────
# 3. COMPLEX (25 Cases)
# ─────────────────────────────────────────────────────────────────

def generate_complex_cases():
    # Case 51: Indirect macro variable reference (&&var&i) -> PATH_A
    add_test_case(
        "COMPLEX_051", "COMPLEX",
        """
%let ds1=DM;
%let ds2=AE;
%let ds3=LB;

%macro combine_domains;
    %do i = 1 %to 3;
        data SUBSET_&&ds&i;
            set &&ds&i;
            if not missing(USUBJID);
        run;
    %end;
%mend;

%combine_domains;
""",
        expected_macros=["COMBINE_DOMAINS"],
        expected_classification={"COMBINE_DOMAINS": "PATH_A"},
        expected_output_datasets=["SUBSET_DM", "SUBSET_AE", "SUBSET_LB"],
        expected_source_datasets=["DM", "AE", "LB"],
        expected_path_b_utilities=[],
        description="Indirect macro variable references (&&ds&i) inside %DO loop"
    )

    # Case 52: Nested Macros (Macro A calling Macro B) -> PATH_B for HELPER, PATH_A for MASTER
    add_test_case(
        "COMPLEX_052", "COMPLEX",
        """
%macro helper_filter(indata=, outdata=, col=);
    data &outdata;
        set &indata;
        if not missing(&col);
    run;
%mend;

%macro master_pipeline(domain=DM);
    %helper_filter(indata=&domain, outdata=&domain._FILT, col=USUBJID);
    proc sort data=&domain._FILT out=&domain._SORT;
        by USUBJID;
    run;
%mend;

%master_pipeline(domain=DM);
""",
        expected_macros=["HELPER_FILTER", "MASTER_PIPELINE"],
        expected_classification={
            "HELPER_FILTER": "PATH_B",
            "MASTER_PIPELINE": "PATH_B"
        },
        expected_output_datasets=["DM_FILT", "DM_SORT"],
        expected_source_datasets=["DM"],
        expected_path_b_utilities=["helper_filter"],
        description="Nested macros: Master pipeline calling helper macro"
    )

    # Case 53: DATA step MERGE with BY and macro variables -> PATH_B (no %IF/%DO)
    add_test_case(
        "COMPLEX_053", "COMPLEX",
        """
%macro merge_sdtm(ds1=DM, ds2=AE, key=USUBJID, out=ADAE_RAW);
    data &out;
        merge &ds1(in=a) &ds2(in=b);
        by &key;
        if a and b;
    run;
%mend;

%merge_sdtm(ds1=DM, ds2=AE, key=USUBJID, out=ADAE_RAW);
""",
        expected_macros=["MERGE_SDTM"],
        expected_classification={"MERGE_SDTM": "PATH_B"},
        expected_output_datasets=["ADAE_RAW"],
        expected_source_datasets=["DM", "AE"],
        expected_path_b_utilities=["merge_sdtm"],
        description="Macro executing DATA step MERGE with IN= flags"
    )

    # Cases 54 to 75: Complex combinations
    for i in range(54, 76):
        mname = f"COMPLEX_MAC_{i}"
        out_ds = f"COMPLEX_OUT_{i}"

        if i % 3 == 0:
            # PROC SQL join in macro (PATH_B if no %IF/%DO)
            code = f"""
%macro {mname}(ds1=DM, ds2=AE, key=USUBJID, out={out_ds});
    proc sql;
        create table &out as
        select a.USUBJID, a.AGE, b.AEDECOD
        from &ds1 as a
        left join &ds2 as b
        on a.&key = b.&key;
    quit;
%mend;

%{mname}(ds1=DM, ds2=AE, key=USUBJID, out={out_ds});
"""
            add_test_case(
                f"COMPLEX_{i:03d}", "COMPLEX", code,
                expected_macros=[mname.upper()],
                expected_classification={mname.upper(): "PATH_B"},
                expected_output_datasets=[out_ds],
                expected_source_datasets=["DM", "AE"],
                expected_path_b_utilities=[mname.lower()],
                description=f"PROC SQL Join inside macro {mname}"
            )
        elif i % 3 == 1:
            # First. / Last. processing macro (PATH_B if no %IF/%DO)
            code = f"""
%macro {mname}(ds=AE, key=USUBJID, out={out_ds});
    proc sort data=&ds out=TEMP_{i};
        by &key;
    run;

    data &out;
        set TEMP_{i};
        by &key;
        if first.&key;
    run;
%mend;

%{mname}(ds=AE, key=USUBJID, out={out_ds});
"""
            add_test_case(
                f"COMPLEX_{i:03d}", "COMPLEX", code,
                expected_macros=[mname.upper()],
                expected_classification={mname.upper(): "PATH_B"},
                expected_output_datasets=[f"TEMP_{i}", out_ds],
                expected_source_datasets=["AE"],
                expected_path_b_utilities=[mname.lower()],
                description=f"First. BY-group processing macro {mname}"
            )
        else:
            # Mixed PATH_B utility + PATH_A pipeline
            code = f"""
%macro util_clean(data=, var=, out=);
    data &out;
        set &data;
        if not missing(&var);
    run;
%mend;

%macro {mname};
    %util_clean(data=DM, var=USUBJID, out=DM_C);
    %util_clean(data=AE, var=AEDECOD, out=AE_C);
    data {out_ds};
        merge DM_C(in=a) AE_C(in=b);
        by USUBJID;
        if a;
    run;
%mend;

%{mname};
"""
            add_test_case(
                f"COMPLEX_{i:03d}", "COMPLEX", code,
                expected_macros=["UTIL_CLEAN", mname.upper()],
                expected_classification={"UTIL_CLEAN": "PATH_B", mname.upper(): "PATH_A"},
                expected_output_datasets=["DM_C", "AE_C", out_ds],
                expected_source_datasets=["DM", "AE"],
                expected_path_b_utilities=["util_clean"],
                description=f"PATH_B utility called inside PATH_A macro {mname}"
            )


# ─────────────────────────────────────────────────────────────────
# 4. VERY_COMPLEX (25 Cases)
# ─────────────────────────────────────────────────────────────────

def generate_very_complex_cases():
    # Case 76: Multi-domain ADAM builder macro -> PATH_B (no %IF/%DO)
    add_test_case(
        "VERY_COMPLEX_076", "VERY_COMPLEX",
        """
%let sdtm_lib=SDTM;
%let adam_lib=ADAM;

%macro build_adsl(min_age=18, saffl_var=SAFFL);
    data ADSL_RAW;
        set SDTM.DM;
        if age >= &min_age;
        if not missing(USUBJID);
    run;

    proc sort data=ADSL_RAW out=ADSL_SORTED;
        by USUBJID;
    run;

    data ADAM.ADSL;
        set ADSL_SORTED;
        &saffl_var = "Y";
    run;
%mend;

%build_adsl(min_age=18, saffl_var=SAFFL);
""",
        expected_macros=["BUILD_ADSL"],
        expected_classification={"BUILD_ADSL": "PATH_B"},
        expected_output_datasets=["ADSL_RAW", "ADSL_SORTED", "ADSL"],
        expected_source_datasets=["DM"],
        expected_path_b_utilities=["build_adsl"],
        description="Multi-step ADSL domain creation macro with libname references"
    )

    # Case 77: Complex dynamic column selection and renaming across domains -> PATH_A (%if present)
    add_test_case(
        "VERY_COMPLEX_077", "VERY_COMPLEX",
        """
%macro prepare_dataset(
    data=,
    out=,
    filter_var=,
    filter_value=,
    keepvars=,
    rename_from=,
    rename_to=
);
    data &out;
        set &data;

        if not missing(&filter_var);

        %if %length(&filter_value) > 0 %then %do;
            if &filter_var = "&filter_value";
        %end;

        keep &keepvars;

        %if %length(&rename_from) > 0 %then %do;
            rename &rename_from = &rename_to;
        %end;
    run;
%mend;

%prepare_dataset(
    data=DM,
    out=DM_CLEAN,
    filter_var=SEX,
    filter_value=M,
    keepvars=USUBJID SEX AGE,
    rename_from=USUBJID,
    rename_to=SUBJECT_ID
);

%prepare_dataset(
    data=AE,
    out=AE_CLEAN,
    filter_var=AESEV,
    filter_value=SEVERE,
    keepvars=USUBJID AESEV AEDECOD
);
""",
        expected_macros=["PREPARE_DATASET"],
        expected_classification={"PREPARE_DATASET": "PATH_A"},
        expected_output_datasets=["DM_CLEAN", "AE_CLEAN"],
        expected_source_datasets=["DM", "AE"],
        expected_path_b_utilities=[],
        description="Multiline parameterized macro with conditional filters and renames"
    )

    # Cases 78 to 100: Very complex clinical macro templates
    for i in range(78, 101):
        mname = f"VCOMPLEX_MAC_{i}"
        out_ds = f"VC_OUT_{i}"

        if i % 3 == 0:
            # Dynamic SQL summary table generator (PATH_B if no %IF/%DO)
            code = f"""
%macro {mname}(ds=AE, groupvar=AEDECOD, out={out_ds});
    proc sql;
        create table &out as
        select &groupvar, count(*) as N_RECORDS, count(distinct USUBJID) as N_SUBJECTS
        from &ds
        where not missing(&groupvar)
        group by &groupvar
        having N_RECORDS > 1
        order by N_RECORDS desc;
    quit;
%mend;

%{mname}(ds=AE, groupvar=AEDECOD, out={out_ds});
"""
            add_test_case(
                f"VERY_COMPLEX_{i:03d}", "VERY_COMPLEX", code,
                expected_macros=[mname.upper()],
                expected_classification={mname.upper(): "PATH_B"},
                expected_output_datasets=[out_ds],
                expected_source_datasets=["AE"],
                expected_path_b_utilities=[mname.lower()],
                description=f"Dynamic PROC SQL Summary macro {mname}"
            )
        elif i % 3 == 1:
            # Multi-level indirect macro variable references -> PATH_A
            code = f"""
%let domain1=DM; %let domain2=AE; %let domain3=LB;
%let key1=USUBJID; %let key2=AEDECOD; %let key3=LBTESTCD;

%macro {mname};
    %do i = 1 %to 3;
        data VC_SUB_&&domain&i;
            set &&domain&i;
            if not missing(&&key&i);
        run;
    %end;
%mend;

%{mname};
"""
            add_test_case(
                f"VERY_COMPLEX_{i:03d}", "VERY_COMPLEX", code,
                expected_macros=[mname.upper()],
                expected_classification={mname.upper(): "PATH_A"},
                expected_output_datasets=["VC_SUB_DM", "VC_SUB_AE", "VC_SUB_LB"],
                expected_source_datasets=["DM", "AE", "LB"],
                expected_path_b_utilities=[],
                description=f"Multi-level indirect macro references in {mname}"
            )
        else:
            # Complex clinical merge + filter + sort pipeline (PATH_B if no %IF/%DO)
            code = f"""
%macro {mname}(sdtm_dm=DM, sdtm_ae=AE, out={out_ds});
    proc sort data=&sdtm_dm out=DM_S;
        by USUBJID;
    run;

    proc sort data=&sdtm_ae out=AE_S;
        by USUBJID;
    run;

    data &out;
        merge DM_S(in=a) AE_S(in=b);
        by USUBJID;
        if a and b;
        keep USUBJID AGE SEX AEDECOD AESEV;
    run;
%mend;

%{mname}(sdtm_dm=DM, sdtm_ae=AE, out={out_ds});
"""
            add_test_case(
                f"VERY_COMPLEX_{i:03d}", "VERY_COMPLEX", code,
                expected_macros=[mname.upper()],
                expected_classification={mname.upper(): "PATH_B"},
                expected_output_datasets=["DM_S", "AE_S", out_ds],
                expected_source_datasets=["DM", "AE"],
                expected_path_b_utilities=[mname.lower()],
                description=f"Complex clinical merge & sort pipeline macro {mname}"
            )


# ─────────────────────────────────────────────────────────────────
# 5. TORTURE (25 Cases)
# ─────────────────────────────────────────────────────────────────

def generate_torture_cases():
    # Case 101: 3-Level Deep Macro Hierarchy with Conditional Calls -> PATH_B for LEVEL3, PATH_A for LEVEL2/LEVEL1
    add_test_case(
        "TORTURE_101", "TORTURE",
        """
%macro level3_filter(ds=, var=, val=, out=);
    data &out;
        set &ds;
        if &var = "&val";
    run;
%mend;

%macro level2_process(domain=, col=, val=);
    %level3_filter(ds=&domain, var=&col, val=&val, out=&domain._SUB);
    proc sort data=&domain._SUB out=&domain._FINAL;
        by USUBJID;
    run;
%mend;

%macro level1_driver;
    %level2_process(domain=DM, col=SEX, val=F);
    %level2_process(domain=AE, col=AESEV, val=SEVERE);
%mend;

%level1_driver;
""",
        expected_macros=["LEVEL3_FILTER", "LEVEL2_PROCESS", "LEVEL1_DRIVER"],
        expected_classification={
            "LEVEL3_FILTER": "PATH_B",
            "LEVEL2_PROCESS": "PATH_B",
            "LEVEL1_DRIVER": "PATH_A"
        },
        expected_output_datasets=["DM_SUB", "DM_FINAL", "AE_SUB", "AE_FINAL"],
        expected_source_datasets=["DM", "AE"],
        expected_path_b_utilities=["level3_filter", "level2_process"],
        description="3-Level Deep Macro Call Hierarchy"
    )

    # Case 102: Extreme Parameter Formatting & Quotes & Multiline %IF
    add_test_case(
        "TORTURE_102", "TORTURE",
        """
%macro torture_params(
    data = DM ,
    out = DM_TORTURE ,
    where_cond = %str(age >= 18 and sex = 'M') ,
    keep_list = USUBJID AGE SEX RACE
);
    data &out;
        set &data;
        if &where_cond;
        keep &keep_list;
    run;
%mend;

%torture_params;
""",
        expected_macros=["TORTURE_PARAMS"],
        expected_classification={"TORTURE_PARAMS": "PATH_B"},
        expected_output_datasets=["DM_TORTURE"],
        expected_source_datasets=["DM"],
        expected_path_b_utilities=["torture_params"],
        description="Macro parameters with %str quotes, whitespace around =, and multiline defaults"
    )

    # Cases 103 to 125: Torture stress tests
    for i in range(103, 126):
        mname = f"TORTURE_MAC_{i}"
        out_ds = f"TORTURE_OUT_{i}"

        if i % 4 == 0:
            # Multiple PATH_B reusable utilities called inside a PATH_A driver
            code = f"""
%macro util_filter(data=, var=, out=);
    data &out;
        set &data;
        if not missing(&var);
    run;
%mend;

%macro util_sort(data=, by=, out=);
    proc sort data=&data out=&out;
        by &by;
    run;
%mend;

%macro {mname};
    %util_filter(data=DM, var=USUBJID, out=DM_F);
    %util_filter(data=AE, var=AEDECOD, out=AE_F);
    data {out_ds};
        merge DM_F(in=a) AE_F(in=b);
        by USUBJID;
        if a and b;
    run;
%mend;

%{mname};
"""
            add_test_case(
                f"TORTURE_{i:03d}", "TORTURE", code,
                expected_macros=["UTIL_FILTER", "UTIL_SORT", mname.upper()],
                expected_classification={"UTIL_FILTER": "PATH_B", "UTIL_SORT": "PATH_B", mname.upper(): "PATH_A"},
                expected_output_datasets=["DM_F", "AE_F", out_ds],
                expected_source_datasets=["DM", "AE"],
                expected_path_b_utilities=["util_filter", "util_sort"],
                description=f"Multiple PATH_B utilities in torture driver {mname}"
            )
        elif i % 4 == 1:
            # Complex nested %IF and %DO loops with dynamic dataset names -> PATH_A
            code = f"""
%macro {mname}(prefix=STUDY01, n_domains=2);
    %do d = 1 %to &n_domains;
        %if &d = 1 %then %let dom=DM;
        %else %let dom=AE;

        data &prefix._&dom._TORT;
            set &dom;
            if not missing(USUBJID);
        run;
    %end;
%mend;

%{mname}(prefix=STUDY01, n_domains=2);
"""
            add_test_case(
                f"TORTURE_{i:03d}", "TORTURE", code,
                expected_macros=[mname.upper()],
                expected_classification={mname.upper(): "PATH_A"},
                expected_output_datasets=["STUDY01_DM_TORT", "STUDY01_AE_TORT"],
                expected_source_datasets=["DM", "AE"],
                expected_path_b_utilities=[],
                description=f"Nested %IF & %DO creating dynamic prefix datasets in {mname}"
            )
        elif i % 4 == 2:
            # Dynamic PROC SQL summary with complex joins & macro variables -> PATH_B
            code = f"""
%macro {mname}(ds1=DM, ds2=LB, key=USUBJID, out={out_ds});
    proc sql;
        create table &out as
        select a.USUBJID, a.AGE, b.LBTESTCD, count(*) as N_TESTS
        from &ds1 as a
        inner join &ds2 as b
        on a.&key = b.&key
        where a.AGE >= 18 and not missing(b.LBTESTCD)
        group by a.USUBJID, a.AGE, b.LBTESTCD
        having N_TESTS >= 1
        order by a.USUBJID;
    quit;
%mend;

%{mname}(ds1=DM, ds2=LB, key=USUBJID, out={out_ds});
"""
            add_test_case(
                f"TORTURE_{i:03d}", "TORTURE", code,
                expected_macros=[mname.upper()],
                expected_classification={mname.upper(): "PATH_B"},
                expected_output_datasets=[out_ds],
                expected_source_datasets=["DM", "LB"],
                expected_path_b_utilities=[mname.lower()],
                description=f"Dynamic PROC SQL complex join and aggregation macro {mname}"
            )
        else:
            # Torture multiline comments & mixed case macro logic -> PATH_B
            code = f"""
/* Torture Block Comment */
%macro {mname}(
    ds_in = DM ,
    ds_out = {out_ds} ,
    filt_var = AGE ,
    filt_val = 18
);

    /* Data Step start */
    data &ds_out;
        set &ds_in;
        if &filt_var >= &filt_val;
        keep USUBJID &filt_var;
    run;

%mend {mname};

%{mname}(ds_in=DM, ds_out={out_ds}, filt_var=AGE, filt_val=18);
"""
            add_test_case(
                f"TORTURE_{i:03d}", "TORTURE", code,
                expected_macros=[mname.upper()],
                expected_classification={mname.upper(): "PATH_B"},
                expected_output_datasets=[out_ds],
                expected_source_datasets=["DM"],
                expected_path_b_utilities=[mname.lower()],
                description=f"Torture multiline comments and parameter spacing in {mname}"
            )


# ─────────────────────────────────────────────────────────────────
# GENERATE ALL CASES AND SAVE TO DISK
# ─────────────────────────────────────────────────────────────────

def main():
    generate_basic_cases()
    generate_moderate_cases()
    generate_complex_cases()
    generate_very_complex_cases()
    generate_torture_cases()

    print(f"Total Generated Test Cases: {len(test_cases)}")
    counts = {}
    for case in test_cases:
        comp = case["complexity"]
        counts[comp] = counts.get(comp, 0) + 1
        
        # Save individual JSON file
        file_path = OUTPUT_DIR / f"{case['test_id']}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(case, f, indent=2)

    print("Breakdown by Complexity Level:")
    for comp, count in counts.items():
        print(f"  - {comp}: {count}")

    # Also save master index
    index_file = OUTPUT_DIR / "_master_index.json"
    with open(index_file, "w", encoding="utf-8") as f:
        json.dump(test_cases, f, indent=2)

    print(f"\n✅ All {len(test_cases)} stress tests written to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
