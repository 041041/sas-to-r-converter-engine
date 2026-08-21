import unittest
import os
import sys

sys.path.insert(0, os.path.abspath("."))

from sas_ast import ProgramStep
from rule_engine import RuleEngine


class TestProcSqlNestedCaseWhen(unittest.TestCase):

    def setUp(self):
        self.r_engine = RuleEngine(dialect="Modern R (tidyverse)")

    def test_1_exact_case_25(self):
        sas = """proc sql;
    create table ADSL as
    select
        USUBJID,
        case
            when AGE >= 65 then
                case
                    when SEX = 'F' then 'ELDERLY_FEMALE'
                    else 'ELDERLY_MALE'
                end
            else 'NON_ELDERLY'
        end as CATEGORY
    from SDTM.DM;
quit;"""
        p_step = ProgramStep(step_index=25, step_type="PROC_STEP", name="ADSL", source_code=sas, input_datasets=["SDTM.DM"], output_datasets=["ADSL"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNotNone(code)
        self.assertEqual(conf, 0.95)
        self.assertIn("select(USUBJID, CATEGORY)", code)
        self.assertIn("CATEGORY = dplyr::case_when(", code)
        self.assertIn("AGE >= 65 & SEX == 'F' ~ 'ELDERLY_FEMALE'", code)
        self.assertIn("AGE >= 65 ~ 'ELDERLY_MALE'", code)
        self.assertIn("TRUE ~ 'NON_ELDERLY'", code)

    def test_2_multiline_formatting(self):
        sas = """proc sql;
    create table ADSL as select USUBJID, case when AGE >= 65 then case when SEX = 'F' then 'ELDERLY_FEMALE' else 'ELDERLY_MALE' end else 'NON_ELDERLY' end as CATEGORY from SDTM.DM;
quit;"""
        p_step = ProgramStep(step_index=25, step_type="PROC_STEP", name="ADSL", source_code=sas, input_datasets=["SDTM.DM"], output_datasets=["ADSL"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNotNone(code)
        self.assertIn("CATEGORY = dplyr::case_when(", code)

    def test_3_string_values(self):
        sas = 'proc sql; create table RESULT as select case when A = 1 then case when B = 2 then "VAL_AB" else "VAL_A" end else "VAL_NONE" end as LAB_CAT from DM; quit;'
        p_step = ProgramStep(step_index=1, step_type="PROC_STEP", name="RESULT", source_code=sas, input_datasets=["DM"], output_datasets=["RESULT"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNotNone(code)
        self.assertIn('LAB_CAT = dplyr::case_when(', code)
        self.assertIn('A == 1 & B == 2 ~ "VAL_AB"', code)

    def test_4_correct_flattening(self):
        sas = 'proc sql; create table ADSL as select case when AGE >= 65 then case when SEX = "F" then "EF" else "EM" end else "NE" end as CAT from DM; quit;'
        p_step = ProgramStep(step_index=1, step_type="PROC_STEP", name="ADSL", source_code=sas, input_datasets=["DM"], output_datasets=["ADSL"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNotNone(code)
        self.assertIn("AGE >= 65 & SEX == \"F\" ~ \"EF\"", code)
        self.assertIn("AGE >= 65 ~ \"EM\"", code)
        self.assertIn("TRUE ~ \"NE\"", code)

    def test_5_negative_three_level_nested_case(self):
        sas = """proc sql;
    create table ADSL as
    select USUBJID,
           case when C1 then
                case when C2 then
                     case when C3 then 'V1' else 'V2' end
                else 'V3' end
           else 'V4' end as X
    from DM;
quit;"""
        p_step = ProgramStep(step_index=1, step_type="PROC_STEP", name="ADSL", source_code=sas, input_datasets=["DM"], output_datasets=["ADSL"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNone(code)
        self.assertEqual(conf, 0.0)

    def test_6_negative_nested_case_in_else(self):
        sas = """proc sql;
    create table ADSL as
    select USUBJID,
           case when AGE >= 65 then "OLD"
                else case when SEX = "F" then "F" else "M" end
           end as X
    from DM;
quit;"""
        p_step = ProgramStep(step_index=1, step_type="PROC_STEP", name="ADSL", source_code=sas, input_datasets=["DM"], output_datasets=["ADSL"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNone(code)
        self.assertEqual(conf, 0.0)

    def test_7_negative_multiple_inner_when(self):
        sas = """proc sql;
    create table ADSL as
    select USUBJID,
           case when AGE >= 65 then
                case when SEX = 'F' then 'F' when SEX = 'M' then 'M' else 'OTHER' end
           else 'N' end as X
    from DM;
quit;"""
        p_step = ProgramStep(step_index=1, step_type="PROC_STEP", name="ADSL", source_code=sas, input_datasets=["DM"], output_datasets=["ADSL"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNone(code)
        self.assertEqual(conf, 0.0)

    def test_8_negative_missing_else(self):
        sas = """proc sql;
    create table ADSL as
    select USUBJID,
           case when AGE >= 65 then
                case when SEX = 'F' then 'F' else 'M' end
           end as X
    from DM;
quit;"""
        p_step = ProgramStep(step_index=1, step_type="PROC_STEP", name="ADSL", source_code=sas, input_datasets=["DM"], output_datasets=["ADSL"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNone(code)
        self.assertEqual(conf, 0.0)

    def test_9_negative_malformed_case(self):
        sas = """proc sql;
    create table ADSL as
    select USUBJID,
           case when AGE >= 65 then
                case when SEX = 'F' then 'F' end else 'M'
           end as X
    from DM;
quit;"""
        p_step = ProgramStep(step_index=1, step_type="PROC_STEP", name="ADSL", source_code=sas, input_datasets=["DM"], output_datasets=["ADSL"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNone(code)
        self.assertEqual(conf, 0.0)

    def test_10_regression_case_23(self):
        sas = """proc sql; create table ADSL as select USUBJID, case when AGE >= 65 then 'ELDERLY' else 'YOUNG' end as AGEGR1 from SDTM.DM; quit;"""
        p_step = ProgramStep(step_index=23, step_type="PROC_STEP", name="ADSL", source_code=sas, input_datasets=["SDTM.DM"], output_datasets=["ADSL"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNotNone(code)
        self.assertEqual(conf, 0.95)
        self.assertIn("AGEGR1 = dplyr::case_when(", code)

    def test_11_regression_case_24(self):
        sas = """proc sql; create table ADSL as select USUBJID, case when AGE >= 65 then 'ELDERLY' else 'YOUNG' end as AGEGR1, case when SEX = 'M' then 'MALE' else 'FEMALE' end as SEX_LABEL from SDTM.DM; quit;"""
        p_step = ProgramStep(step_index=24, step_type="PROC_STEP", name="ADSL", source_code=sas, input_datasets=["SDTM.DM"], output_datasets=["ADSL"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNotNone(code)
        self.assertEqual(conf, 0.95)
        self.assertIn("AGEGR1 = dplyr::case_when(", code)
        self.assertIn("SEX_LABEL = dplyr::case_when(", code)

    def test_12_regression_aggregate_case(self):
        sas = 'proc sql; create table RESULT as select ARM, sum(case when AGE >= 65 then 1 else 0 end) as N_ELDERLY from ADSL group by ARM; quit;'
        p_step = ProgramStep(step_index=26, step_type="PROC_STEP", name="RESULT", source_code=sas, input_datasets=["ADSL"], output_datasets=["RESULT"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNotNone(code)
        self.assertEqual(conf, 0.95)
        self.assertIn('N_ELDERLY = sum(if_else(AGE >= 65, 1, 0), na.rm = TRUE)', code)


if __name__ == "__main__":
    unittest.main()
