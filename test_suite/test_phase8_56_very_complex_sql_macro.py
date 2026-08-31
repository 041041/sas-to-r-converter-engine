import unittest
from macro_converter import parse_sas_source, classify_macro, convert_macros_to_r
from macro_processor import SASMacroProcessor
from sas_step_converter import SASStepConverter


class TestPhase856VeryComplexSQLMacro(unittest.TestCase):
    def test_very_complex_sql_macro_pipeline(self):
        sas_input = """
%let SRC_LIB = WORK;
%let OUT_LIB = WORK;
%let MIN_AGE = 18;
%let SEX_FILTER = M;

%macro apply_domain_filter(
    source=,
    target=,
    domain=,
    filter_var=,
    filter_value=,
    keepvars=
);

    data &target;
        set &source;

        %if %length(&filter_var) > 0 %then %do;
            if not missing(&filter_var);
        %end;

        %if %length(&filter_value) > 0 %then %do;

            %if %upcase(&domain) = DM %then %do;
                if &filter_var = "&filter_value";
            %end;

            %else %if %upcase(&domain) = AE %then %do;
                if upcase(&filter_var) = "%upcase(&filter_value)";
            %end;

            %else %if %upcase(&domain) = LB %then %do;
                if upcase(&filter_var) = "%upcase(&filter_value)";
            %end;

        %end;

        %if %length(&keepvars) > 0 %then %do;
            keep &keepvars;
        %end;

    run;

%mend apply_domain_filter;


%macro conditional_rename(
    data=,
    from=,
    to=
);

    %if %length(&from) > 0 and %length(&to) > 0 %then %do;

        data &data;
            set &data;
            rename &from = &to;
        run;

    %end;

%mend conditional_rename;


%macro sort_domain(
    data=,
    by=
);

    proc sort data=&data;
        by &by;
    run;

%mend sort_domain;


%macro build_domain(
    domain=,
    source=,
    output=,
    filter_var=,
    filter_value=,
    keepvars=,
    rename_from=,
    rename_to=,
    sortby=
);

    %apply_domain_filter(
        source=&source,
        target=&output._FILT,
        domain=&domain,
        filter_var=&filter_var,
        filter_value=&filter_value,
        keepvars=&keepvars
    );

    %conditional_rename(
        data=&output._FILT,
        from=&rename_from,
        to=&rename_to
    );

    %if %length(&sortby) > 0 %then %do;

        %sort_domain(
            data=&output._FILT,
            by=&sortby
        );

    %end;

    data &output;
        set &output._FILT;
    run;

%mend build_domain;


%build_domain(
    domain=DM,
    source=&SRC_LIB..DM,
    output=&OUT_LIB..DM_CLEAN,
    filter_var=SEX,
    filter_value=&SEX_FILTER,
    keepvars=USUBJID SEX AGE,
    rename_from=USUBJID,
    rename_to=SUBJECT_ID,
    sortby=SUBJECT_ID
);

%build_domain(
    domain=AE,
    source=&SRC_LIB..AE,
    output=&OUT_LIB..AE_CLEAN,
    filter_var=AESEV,
    filter_value=severe,
    keepvars=USUBJID AESEV AEDECOD,
    rename_from=,
    rename_to=,
    sortby=USUBJID
);

%build_domain(
    domain=LB,
    source=&SRC_LIB..LB,
    output=&OUT_LIB..LB_CLEAN,
    filter_var=LBTESTCD,
    filter_value=,
    keepvars=USUBJID LBTESTCD LBSTRESN,
    rename_from=,
    rename_to=,
    sortby=USUBJID
);

proc sql;

    create table &OUT_LIB..DM_AE_SUMMARY as

    select
        d.SUBJECT_ID,
        d.SEX,
        d.AGE,
        count(a.AEDECOD) as AE_COUNT

    from &OUT_LIB..DM_CLEAN as d

    left join &OUT_LIB..AE_CLEAN as a
        on d.SUBJECT_ID = a.USUBJID

    where d.AGE >= &MIN_AGE

    group by
        d.SUBJECT_ID,
        d.SEX,
        d.AGE

    having calculated AE_COUNT >= 0

    order by
        d.SUBJECT_ID;

quit;


proc sort
    data=&OUT_LIB..DM_AE_SUMMARY
    out=&OUT_LIB..FINAL_ANALYSIS;

    by descending AGE SUBJECT_ID;

run;
"""

        parsed = parse_sas_source(sas_input)
        mdefs = parsed["macro_definitions"]
        has_path_b = any(classify_macro(m, mdef, all_macro_defs=mdefs) == "PATH_B" for m, mdef in mdefs.items())

        proc = SASMacroProcessor()
        unexp, _, _ = proc.process(sas_input, expand_path_b=not has_path_b)

        converter = SASStepConverter(dialect="Modern R (dplyr)")
        res = converter.convert_program(unexp, raw_sas_code=sas_input)
        r_out = res.full_optimized_r

        # Issue 1: PATH_B sort_domain R function semantics
        mres = convert_macros_to_r(mdefs, parsed.get("macro_calls", []), dialect="Modern R (dplyr)")
        r_func = mres.get("r_functions", "")
        self.assertIn(".data[[by]]", r_func)
        self.assertIn("return(data)", r_func)

        # Issue 2: COUNT(a.AEDECOD) in summarise
        self.assertIn('AE_COUNT = sum(!is.na(AEDECOD))', r_out)

        # Issue 3: Join key semantics for unequal names
        self.assertIn('by = c("SUBJECT_ID" = "USUBJID")', r_out)

        # Extract DM_AE_SUMMARY block specifically
        summary_start = r_out.find('DM_AE_SUMMARY <-')
        summary_end = r_out.find('FINAL_ANALYSIS <-')
        summary_block = r_out[summary_start:summary_end]

        # Issue 4: HAVING CALCULATED AE_COUNT >= 0 after group_by + summarise inside DM_AE_SUMMARY block
        group_idx = summary_block.find('group_by')
        summ_idx = summary_block.find('summarise')
        filt_idx = summary_block.find('filter(AE_COUNT >= 0)')
        arr_idx = summary_block.find('arrange(SUBJECT_ID)')
        self.assertTrue(group_idx < summ_idx < filt_idx < arr_idx)

        # Issue 6: No bogus step fallbacks
        self.assertNotIn('Step', r_out)
        self.assertIn('DM_AE_SUMMARY <-', r_out)
        self.assertIn('FINAL_ANALYSIS <-', r_out)


if __name__ == "__main__":
    unittest.main()
