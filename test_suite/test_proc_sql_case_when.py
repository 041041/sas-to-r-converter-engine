import unittest
import os
import sys

sys.path.insert(0, os.path.abspath("."))

from sas_ast import ProgramStep
from rule_engine import RuleEngine


class TestProcSqlCaseWhen(unittest.TestCase):

    def setUp(self):
        self.r_engine = RuleEngine(dialect="Modern R (tidyverse)")

    def test_a_simple_scalar_case(self):
        sas = 'proc sql; create table RESULT as select case when AGE >= 65 then "ELDERLY" else "YOUNG" end as AGE_GROUP from DM; quit;'
        p_step = ProgramStep(step_index=1, step_type="PROC_STEP", name="RESULT", source_code=sas, input_datasets=["DM"], output_datasets=["RESULT"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNotNone(code)
        self.assertEqual(conf, 0.95)
        self.assertIn('AGE_GROUP = dplyr::case_when(', code)
        self.assertIn('AGE >= 65 ~ "ELDERLY"', code)
        self.assertIn('TRUE ~ "YOUNG"', code)

    def test_b_select_plus_case(self):
        sas = """proc sql;
    create table ADSL as
    select
        USUBJID,
        case
            when AGE >= 65 then "ELDERLY"
            else "YOUNG"
        end as AGE_GROUP
    from DM;
quit;"""
        p_step = ProgramStep(step_index=23, step_type="PROC_STEP", name="ADSL", source_code=sas, input_datasets=["DM"], output_datasets=["ADSL"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNotNone(code)
        self.assertEqual(conf, 0.95)
        self.assertIn("select(USUBJID, AGE_GROUP)", code)
        self.assertIn("AGE_GROUP = dplyr::case_when(", code)

    def test_c_multiline_case(self):
        sas = """proc sql;
    create table ADSL as
    select
        USUBJID,
        case
            when AGE >= 65
            then "ELDERLY"
            else "YOUNG"
        end as AGE_GROUP
    from DM;
quit;"""
        p_step = ProgramStep(step_index=1, step_type="PROC_STEP", name="ADSL", source_code=sas, input_datasets=["DM"], output_datasets=["ADSL"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNotNone(code)
        self.assertIn("AGE_GROUP = dplyr::case_when(", code)

    def test_d_string_values(self):
        sas = 'proc sql; create table RESULT as select case when SEX = "F" then "FEMALE" else "MALE" end as SEX_DESC from DM; quit;'
        p_step = ProgramStep(step_index=1, step_type="PROC_STEP", name="RESULT", source_code=sas, input_datasets=["DM"], output_datasets=["RESULT"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNotNone(code)
        self.assertIn('SEX_DESC = dplyr::case_when(', code)
        self.assertIn('SEX == "F" ~ "FEMALE"', code)
        self.assertIn('TRUE ~ "MALE"', code)

    def test_e_numeric_values(self):
        sas = 'proc sql; create table RESULT as select case when AGE >= 65 then 1 else 0 end as ELDERLY_FLAG from DM; quit;'
        p_step = ProgramStep(step_index=1, step_type="PROC_STEP", name="RESULT", source_code=sas, input_datasets=["DM"], output_datasets=["RESULT"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNotNone(code)
        self.assertIn('ELDERLY_FLAG = dplyr::case_when(', code)
        self.assertIn('AGE >= 65 ~ 1', code)
        self.assertIn('TRUE ~ 0', code)

    def test_f_negative_case_without_else(self):
        sas = 'proc sql; create table RESULT as select case when AGE >= 65 then "ELDERLY" end as AGE_GROUP from DM; quit;'
        p_step = ProgramStep(step_index=1, step_type="PROC_STEP", name="RESULT", source_code=sas, input_datasets=["DM"], output_datasets=["RESULT"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNone(code)
        self.assertEqual(conf, 0.0)

    def test_g_negative_nested_case(self):
        # 3-level nested case must remain unsupported/rejected
        sas = """proc sql;
    create table ADSL as
    select USUBJID,
           case when AGE >= 65 then
                case when SEX = 'F' then
                     case when ARM = 'Placebo' then 'P' else 'A' end
                else 'ELDERLY_MALE' end
           else 'NON_ELDERLY' end as CATEGORY
    from DM;
quit;"""
        p_step = ProgramStep(step_index=25, step_type="PROC_STEP", name="ADSL", source_code=sas, input_datasets=["DM"], output_datasets=["ADSL"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNone(code)
        self.assertEqual(conf, 0.0)

    def test_h_negative_multiple_when(self):
        sas = """proc sql;
    create table ADSL as
    select USUBJID,
           case when AGE >= 65 then 'OLD' when AGE >= 50 then 'MID' else 'YOUNG' end as AGEGR
    from DM;
quit;"""
        p_step = ProgramStep(step_index=1, step_type="PROC_STEP", name="ADSL", source_code=sas, input_datasets=["DM"], output_datasets=["ADSL"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNone(code)
        self.assertEqual(conf, 0.0)

    def test_i_negative_malformed_case(self):
        sas = 'proc sql; create table RESULT as select case when AGE >= 65 then "ELDERLY" else "YOUNG" end from DM; quit;'
        p_step = ProgramStep(step_index=1, step_type="PROC_STEP", name="RESULT", source_code=sas, input_datasets=["DM"], output_datasets=["RESULT"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNone(code)
        self.assertEqual(conf, 0.0)

    def test_j_regression_aggregate_case(self):
        sas = 'proc sql; create table RESULT as select ARM, sum(case when AGE >= 65 then 1 else 0 end) as N_ELDERLY from ADSL group by ARM; quit;'
        p_step = ProgramStep(step_index=26, step_type="PROC_STEP", name="RESULT", source_code=sas, input_datasets=["ADSL"], output_datasets=["RESULT"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNotNone(code)
        self.assertEqual(conf, 0.95)
        self.assertIn('N_ELDERLY = sum(if_else(AGE >= 65, 1, 0), na.rm = TRUE)', code)


if __name__ == "__main__":
    unittest.main()
