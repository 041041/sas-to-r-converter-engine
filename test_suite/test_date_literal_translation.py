import unittest
import os
import sys

sys.path.insert(0, os.path.abspath("."))

from sas_ast import ProgramStep
from rule_engine import RuleEngine
from app import is_valid_r_code, validate_r_syntax, run_r_subprocess
import pandas as pd


class TestDateLiteralTranslation(unittest.TestCase):

    def setUp(self):
        self.r_engine = RuleEngine(dialect="Modern R (tidyverse)")

    def test_a_basic_date_assignment(self):
        sas = "data ADSL; set DM; CUTOFF = '01JAN2024'd; run;"
        step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas)
        r_code, conf, method = self.r_engine.translate_step(step)
        self.assertIsNotNone(r_code)
        self.assertIn('as.Date("2024-01-01")', r_code)
        self.assertTrue(is_valid_r_code(r_code))
        self.assertTrue(validate_r_syntax(r_code))

    def test_b_multiple_date_literals(self):
        sas = "data ADSL; set DM; D1 = '01JAN2024'd; D2 = '31DEC2023'd; run;"
        step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas)
        r_code, conf, method = self.r_engine.translate_step(step)
        self.assertIsNotNone(r_code)
        self.assertIn('as.Date("2024-01-01")', r_code)
        self.assertIn('as.Date("2023-12-31")', r_code)
        self.assertTrue(is_valid_r_code(r_code))
        self.assertTrue(validate_r_syntax(r_code))

    def test_c_date_comparison(self):
        sas = "data ADSL; set DM; if STARTDT >= '01JAN2024'd; run;"
        step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas)
        r_code, conf, method = self.r_engine.translate_step(step)
        self.assertIsNotNone(r_code)
        self.assertIn('as.Date("2024-01-01")', r_code)
        self.assertTrue(is_valid_r_code(r_code))
        self.assertTrue(validate_r_syntax(r_code))

    def test_d_proc_sql_date_where(self):
        sas = "proc sql; create table ADSL as select USUBJID, STARTDT from DM where STARTDT >= '01JAN2024'd; quit;"
        step = ProgramStep(step_index=1, step_type="PROC_STEP", name="ADSL", source_code=sas)
        r_code, conf, method = self.r_engine.translate_step(step)
        self.assertIsNotNone(r_code)
        self.assertIn('as.Date("2024-01-01")', r_code)
        self.assertTrue(is_valid_r_code(r_code))
        self.assertTrue(validate_r_syntax(r_code))

    def test_e_valid_leap_year(self):
        sas = "data ADSL; set DM; CUTOFF = '29FEB2024'd; run;"
        step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas)
        r_code, conf, method = self.r_engine.translate_step(step)
        self.assertIsNotNone(r_code)
        self.assertIn('as.Date("2024-02-29")', r_code)
        self.assertTrue(is_valid_r_code(r_code))
        self.assertTrue(validate_r_syntax(r_code))

    def test_f_malformed_date_rejection(self):
        # Invalid day 99 -> should not convert to as.Date
        r_99 = RuleEngine._normalize_sas_date_literals("'99JAN2024'd")
        self.assertEqual(r_99, "'99JAN2024'd")

        # Invalid month XYZ -> should not convert to as.Date
        r_xyz = RuleEngine._normalize_sas_date_literals("'01XYZ2024'd")
        self.assertEqual(r_xyz, "'01XYZ2024'd")

        # Invalid non-leap year Feb 29 2023 -> should not convert to as.Date
        r_feb29 = RuleEngine._normalize_sas_date_literals("'29FEB2023'd")
        self.assertEqual(r_feb29, "'29FEB2023'd")

    def test_g_execution_and_value_equivalence(self):
        input_df = pd.DataFrame({
            "USUBJID": ["P1", "P2"],
            "STARTDT": ["2024-01-15", "2023-05-10"]
        })
        sas = "proc sql; create table ADSL as select USUBJID, STARTDT from DM where STARTDT >= '01JAN2024'd; quit;"
        step = ProgramStep(step_index=1, step_type="PROC_STEP", name="ADSL", source_code=sas)
        r_code, conf, method = self.r_engine.translate_step(step)
        try:
            res_df, _ = run_r_subprocess(r_code, input_df, env_dict={"DM": input_df})
            self.assertEqual(len(res_df), 1)
            self.assertEqual(res_df.iloc[0]["USUBJID"], "P1")
        except RuntimeError as e:
            if "there is no package called" in str(e):
                pass
            else:
                raise


if __name__ == "__main__":
    unittest.main()
