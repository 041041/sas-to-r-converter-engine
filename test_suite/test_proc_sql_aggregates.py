import unittest
import os
import sys

sys.path.insert(0, os.path.abspath("."))

from sas_ast import ProgramStep
from rule_engine import RuleEngine


class TestProcSqlAggregates(unittest.TestCase):

    def setUp(self):
        self.r_engine = RuleEngine(dialect="Modern R (tidyverse)")

    def test_a_count_distinct(self):
        sas = "proc sql; create table RESULT as select count(distinct USUBJID) as PATIENTS from ADSL; quit;"
        p_step = ProgramStep(step_index=1, step_type="PROC_STEP", name="RESULT", source_code=sas, input_datasets=["ADSL"], output_datasets=["RESULT"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNotNone(code)
        self.assertIn("PATIENTS = dplyr::n_distinct(USUBJID)", code)

    def test_b_sum_case_when_inequality(self):
        sas = "proc sql; create table RESULT as select sum(case when AGE >= 65 then 1 else 0 end) as ELDERLY_PATIENTS from ADSL; quit;"
        p_step = ProgramStep(step_index=1, step_type="PROC_STEP", name="RESULT", source_code=sas, input_datasets=["ADSL"], output_datasets=["RESULT"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNotNone(code)
        self.assertIn("ELDERLY_PATIENTS = sum(if_else(AGE >= 65, 1, 0), na.rm = TRUE)", code)

    def test_c_sum_case_when_compound_and(self):
        sas = 'proc sql; create table RESULT as select sum(case when AGE >= 65 and SEX = "F" then 1 else 0 end) as ELDERLY_FEMALES from ADSL; quit;'
        p_step = ProgramStep(step_index=1, step_type="PROC_STEP", name="RESULT", source_code=sas, input_datasets=["ADSL"], output_datasets=["RESULT"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNotNone(code)
        self.assertIn('ELDERLY_FEMALES = sum(if_else(AGE >= 65 & SEX == "F", 1, 0), na.rm = TRUE)', code)

    def test_d_combined_trt_summary(self):
        sas = """proc sql;
    create table TRT_SUMMARY as
    select
        TRT01A,
        count(distinct USUBJID) as PATIENTS,
        sum(case when AGE >= 65 then 1 else 0 end) as ELDERLY_PATIENTS,
        sum(case when AGE >= 65 and SEX = "F" then 1 else 0 end) as ELDERLY_FEMALES,
        avg(AGE) as MEAN_AGE
    from ADSL
    group by TRT01A
    order by TRT01A;
quit;"""
        p_step = ProgramStep(step_index=1, step_type="PROC_STEP", name="TRT_SUMMARY", source_code=sas, input_datasets=["ADSL"], output_datasets=["TRT_SUMMARY"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNotNone(code)
        self.assertIn("PATIENTS = dplyr::n_distinct(USUBJID)", code)
        self.assertIn("ELDERLY_PATIENTS = sum(if_else(AGE >= 65, 1, 0), na.rm = TRUE)", code)
        self.assertIn('ELDERLY_FEMALES = sum(if_else(AGE >= 65 & SEX == "F", 1, 0), na.rm = TRUE)', code)
        self.assertIn("MEAN_AGE = mean(AGE, na.rm = TRUE)", code)
        self.assertIn("group_by(TRT01A)", code)
        self.assertIn("arrange(TRT01A)", code)

    def test_e_regression_existing_aggregates(self):
        sas = "proc sql; create table RESULT as select ARM, count(*) as N, avg(AGE) as MEAN_AGE from ADSL group by ARM; quit;"
        p_step = ProgramStep(step_index=1, step_type="PROC_STEP", name="RESULT", source_code=sas, input_datasets=["ADSL"], output_datasets=["RESULT"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNotNone(code)
        self.assertIn("N = n()", code)
        self.assertIn("MEAN_AGE = mean(AGE, na.rm = TRUE)", code)

    def test_f_regression_group_by(self):
        sas = "proc sql; create table RESULT as select ARM, count(*) as N from ADSL group by ARM; quit;"
        p_step = ProgramStep(step_index=1, step_type="PROC_STEP", name="RESULT", source_code=sas, input_datasets=["ADSL"], output_datasets=["RESULT"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNotNone(code)
        self.assertIn("group_by(ARM)", code)

    def test_g_regression_join(self):
        sas = "proc sql; create table ADAE as select a.USUBJID, a.ARM, b.AEDECOD from ADSL as a left join AE as b on a.USUBJID = b.USUBJID; quit;"
        p_step = ProgramStep(step_index=1, step_type="PROC_STEP", name="ADAE", source_code=sas, input_datasets=["ADSL", "AE"], output_datasets=["ADAE"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNotNone(code)
        self.assertIn("left_join(AE, by = \"USUBJID\")", code)

    def test_h_regression_select_projection(self):
        sas = "proc sql; create table RESULT as select USUBJID, AGE, SEX from DM; quit;"
        p_step = ProgramStep(step_index=1, step_type="PROC_STEP", name="RESULT", source_code=sas, input_datasets=["DM"], output_datasets=["RESULT"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNotNone(code)
        self.assertIn("select(USUBJID, AGE, SEX)", code)


if __name__ == "__main__":
    unittest.main()
