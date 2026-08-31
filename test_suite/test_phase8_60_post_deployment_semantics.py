import unittest
import re
from sas_step_converter import SASStepConverter
from macro_processor import SASMacroProcessor
from macro_converter import parse_sas_source, classify_macro, convert_macros_to_r
from rule_engine import RuleEngine
from sas_ast import ProgramStep


class TestPhase860PostDeploymentSemantics(unittest.TestCase):
    def test_proc_sql_and_proc_sort_out_dataset_names_and_no_bogus_fallback(self):
        sas_input = """
%macro sort_domain(data=, by=);
    proc sort data=&data;
        by &by;
    run;
%mend;

%sort_domain(data=AE, by=USUBJID);

proc sql;
    create table DM_AE_SUMMARY as
    select
        d.SUBJECT_ID,
        d.SEX,
        d.AGE,
        count(a.AEDECOD) as AE_COUNT
    from DM_CLEAN as d
    left join AE_CLEAN as a
        on d.SUBJECT_ID = a.USUBJID
    where d.AGE >= 18
    group by
        d.SUBJECT_ID,
        d.SEX,
        d.AGE
    having calculated AE_COUNT >= 0
    order by d.SUBJECT_ID;
quit;

proc sort
    data=DM_AE_SUMMARY
    out=FINAL_ANALYSIS;

    by descending AGE SUBJECT_ID;

run;
"""
        proc = SASMacroProcessor()
        unexp, _, _ = proc.process(sas_input, expand_path_b=False)

        converter = SASStepConverter(dialect="Modern R (dplyr)")
        res = converter.convert_program(unexp, raw_sas_code=sas_input)
        r_out = res.full_optimized_r

        # 1. No bogus Step11 / Step12 fallbacks
        self.assertNotIn("Step11 <- df", r_out)
        self.assertNotIn("Step12 <- df", r_out)
        self.assertNotIn("<- df", r_out)

        # 2. No self-referencing dataset before assignment
        self.assertNotIn("FINAL_ANALYSIS$AGE", r_out)
        self.assertNotIn("FINAL_ANALYSIS$SUBJECT_ID", r_out)

        # 3. Correct pipeline outputs
        self.assertIn("DM_AE_SUMMARY <-", r_out)
        self.assertIn("FINAL_ANALYSIS <- DM_AE_SUMMARY", r_out)
        self.assertIn("arrange(desc(AGE), SUBJECT_ID)", r_out)

    def test_rule_engine_proc_sort_base_r_input_dataset_reference(self):
        rule_engine = RuleEngine(dialect="Base R")
        step = ProgramStep(
            step_index=1,
            step_type="PROC_STEP",
            name="FINAL_ANALYSIS",
            source_code="proc sort data=DM_AE_SUMMARY out=FINAL_ANALYSIS; by descending AGE SUBJECT_ID; run;",
            input_datasets=["DM_AE_SUMMARY"],
            output_datasets=["FINAL_ANALYSIS"]
        )
        r_code, _, _ = rule_engine.translate_step(step)
        # Should reference input dataset DM_AE_SUMMARY inside order(), NOT output dataset FINAL_ANALYSIS
        self.assertIn("order(-DM_AE_SUMMARY$AGE, DM_AE_SUMMARY$SUBJECT_ID)", r_code)
        self.assertNotIn("order(-FINAL_ANALYSIS$AGE", r_code)

    def test_app_step_name_extraction(self):
        steps = [
            "proc sql; create table WORK.DM_AE_SUMMARY as select * from DM_CLEAN; quit;",
            "proc sort data=WORK.DM_AE_SUMMARY out=WORK.FINAL_ANALYSIS; by descending AGE; run;"
        ]
        snames = []
        for i, step in enumerate(steps, 11):
            out_name_match = re.search(r"(?:^\s*data\s+|out\s*=\s*|create\s+table\s+)([\w.]+)", step, re.I | re.M)
            sort_inplace_match = re.search(r"proc\s+sort\s+data\s*=\s*([\w.]+)", step, re.I)

            if out_name_match:
                sname = out_name_match.group(1).split('.')[-1].upper().strip()
            elif sort_inplace_match:
                sname = sort_inplace_match.group(1).split('.')[-1].upper().strip()
            else:
                sname = f"Step{i}"
            snames.append(sname)

        self.assertEqual(snames, ["DM_AE_SUMMARY", "FINAL_ANALYSIS"])


if __name__ == "__main__":
    unittest.main()
