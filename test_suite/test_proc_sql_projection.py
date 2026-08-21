import unittest
import os
import sys

sys.path.insert(0, os.path.abspath("."))

from sas_ast import ProgramStep
from rule_engine import RuleEngine


class TestProcSqlProjection(unittest.TestCase):

    def setUp(self):
        self.r_engine = RuleEngine(dialect="Modern R (tidyverse)")

    def test_a_select_projection(self):
        sas = "proc sql; create table RESULT as select USUBJID, AGE, SEX from DM; quit;"
        p_step = ProgramStep(step_index=1, step_type="PROC_STEP", name="RESULT", source_code=sas, input_datasets=["DM"], output_datasets=["RESULT"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNotNone(code)
        self.assertIn("select(USUBJID, AGE, SEX)", code)

    def test_b_select_projection_where(self):
        sas = "proc sql; create table RESULT as select USUBJID, AGE from DM where AGE >= 50; quit;"
        p_step = ProgramStep(step_index=1, step_type="PROC_STEP", name="RESULT", source_code=sas, input_datasets=["DM"], output_datasets=["RESULT"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNotNone(code)
        self.assertIn("filter(AGE >= 50)", code)
        self.assertIn("select(USUBJID, AGE)", code)

    def test_c_select_projection_order_by(self):
        sas = "proc sql; create table RESULT as select USUBJID, AGE from DM order by AGE desc; quit;"
        p_step = ProgramStep(step_index=1, step_type="PROC_STEP", name="RESULT", source_code=sas, input_datasets=["DM"], output_datasets=["RESULT"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNotNone(code)
        self.assertIn("select(USUBJID, AGE)", code)
        self.assertIn("arrange(desc(AGE))", code)

    def test_d_select_projection_inner_join(self):
        sas = "proc sql; create table ADAE as select a.USUBJID, a.ARM, b.AEDECOD from ADSL as a inner join AE as b on a.USUBJID = b.USUBJID; quit;"
        p_step = ProgramStep(step_index=1, step_type="PROC_STEP", name="ADAE", source_code=sas, input_datasets=["ADSL", "AE"], output_datasets=["ADAE"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNotNone(code)
        self.assertIn("inner_join(AE, by = \"USUBJID\")", code)
        self.assertIn("select(USUBJID, ARM, AEDECOD)", code)

    def test_e_select_projection_left_join(self):
        sas = "proc sql; create table ADAE as select a.USUBJID, a.ARM, b.AEDECOD from ADSL as a left join AE as b on a.USUBJID = b.USUBJID; quit;"
        p_step = ProgramStep(step_index=1, step_type="PROC_STEP", name="ADAE", source_code=sas, input_datasets=["ADSL", "AE"], output_datasets=["ADAE"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNotNone(code)
        self.assertIn("left_join(AE, by = \"USUBJID\")", code)
        self.assertIn("select(USUBJID, ARM, AEDECOD)", code)

    def test_f_qualified_columns(self):
        sas = "proc sql; create table RESULT as select a.USUBJID, a.AGE from DM as a; quit;"
        p_step = ProgramStep(step_index=1, step_type="PROC_STEP", name="RESULT", source_code=sas, input_datasets=["DM"], output_datasets=["RESULT"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNotNone(code)
        self.assertIn("select(USUBJID, AGE)", code)

    def test_g_regression_aggregate_select(self):
        sas = "proc sql; create table N_SUBJ as select count(*) as TOTAL_PATIENTS from ADSL; quit;"
        p_step = ProgramStep(step_index=1, step_type="PROC_STEP", name="N_SUBJ", source_code=sas, input_datasets=["ADSL"], output_datasets=["N_SUBJ"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNotNone(code)
        self.assertIn("summarise(\n    TOTAL_PATIENTS = n()", code)
        self.assertNotIn("select(TOTAL_PATIENTS)", code)

    def test_h_regression_group_by(self):
        sas = "proc sql; create table AE_SUM as select ARM, count(*) as N from ADSL group by ARM; quit;"
        p_step = ProgramStep(step_index=1, step_type="PROC_STEP", name="AE_SUM", source_code=sas, input_datasets=["ADSL"], output_datasets=["AE_SUM"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNotNone(code)
        self.assertIn("group_by(ARM)", code)
        self.assertIn("summarise(\n    N = n()", code)

    def test_i_regression_having(self):
        sas = "proc sql; create table AE_SUM as select ARM, count(*) as N from ADSL group by ARM having count(*) > 5; quit;"
        p_step = ProgramStep(step_index=1, step_type="PROC_STEP", name="AE_SUM", source_code=sas, input_datasets=["ADSL"], output_datasets=["AE_SUM"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNotNone(code)
        self.assertIn("filter(N > 5)", code)

    def test_j_regression_join_null_behavior(self):
        sas = "proc sql; create table NO_AE as select a.USUBJID from ADSL as a left join AE as b on a.USUBJID = b.USUBJID where b.USUBJID is null; quit;"
        p_step = ProgramStep(step_index=1, step_type="PROC_STEP", name="NO_AE", source_code=sas, input_datasets=["ADSL", "AE"], output_datasets=["NO_AE"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNotNone(code)
        self.assertIn("anti_join(AE, by = \"USUBJID\")", code)
        self.assertIn("select(USUBJID)", code)


if __name__ == "__main__":
    unittest.main()
