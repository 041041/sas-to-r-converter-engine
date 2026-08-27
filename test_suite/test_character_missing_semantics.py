import unittest
import os
import sys

sys.path.insert(0, os.path.abspath("."))

from sas_ast import ProgramStep
from rule_engine import RuleEngine
from app import is_valid_r_code, validate_r_syntax, run_r_subprocess
import pandas as pd


class TestCharacterMissingSemantics(unittest.TestCase):

    def setUp(self):
        self.r_engine = RuleEngine(dialect="Modern R (tidyverse)")

    def test_i_ne_empty_string(self):
        sas = "data ADSL; set DM; if EXSTDTC ne ''; run;"
        step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas)
        r_code, conf, method = self.r_engine.translate_step(step)
        self.assertIsNotNone(r_code)
        self.assertIn('!is.na(EXSTDTC) & EXSTDTC != ""', r_code)
        self.assertTrue(is_valid_r_code(r_code))
        self.assertTrue(validate_r_syntax(r_code))

    def test_j_eq_empty_string(self):
        sas = "data ADSL; set DM; if EXSTDTC = ''; run;"
        step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas)
        r_code, conf, method = self.r_engine.translate_step(step)
        self.assertIsNotNone(r_code)
        self.assertIn('is.na(EXSTDTC) | EXSTDTC == ""', r_code)
        self.assertTrue(is_valid_r_code(r_code))
        self.assertTrue(validate_r_syntax(r_code))

    def test_k_uppercase_ne_empty_string(self):
        sas = "data ADSL; set DM; where EXSTDTC NE ''; run;"
        step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas)
        r_code, conf, method = self.r_engine.translate_step(step)
        self.assertIsNotNone(r_code)
        self.assertIn('!is.na(EXSTDTC) & EXSTDTC != ""', r_code)
        self.assertTrue(is_valid_r_code(r_code))
        self.assertTrue(validate_r_syntax(r_code))

    def test_l_uppercase_eq_empty_string(self):
        sas = "data ADSL; set DM; where EXSTDTC EQ ''; run;"
        step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas)
        r_code, conf, method = self.r_engine.translate_step(step)
        self.assertIsNotNone(r_code)
        self.assertIn('is.na(EXSTDTC) | EXSTDTC == ""', r_code)
        self.assertTrue(is_valid_r_code(r_code))
        self.assertTrue(validate_r_syntax(r_code))

    def test_n_proc_sql_character_where(self):
        sas = "proc sql; create table ADSL as select USUBJID, EXSTDTC from DM where EXSTDTC ne ''; quit;"
        step = ProgramStep(step_index=1, step_type="PROC_STEP", name="ADSL", source_code=sas)
        r_code, conf, method = self.r_engine.translate_step(step)
        self.assertIsNotNone(r_code)
        self.assertIn('!is.na(EXSTDTC) & EXSTDTC != ""', r_code)
        self.assertTrue(is_valid_r_code(r_code))
        self.assertTrue(validate_r_syntax(r_code))

    def test_p_execution_and_mixed_values_value_equivalence(self):
        # Create dataset with populated value, empty string, and NA
        input_df = pd.DataFrame({
            "USUBJID": ["P1", "P2", "P3"],
            "EXSTDTC": ["2024-01-01", "", None]
        })
        sas = "proc sql; create table ADSL as select USUBJID, EXSTDTC from DM where EXSTDTC ne ''; quit;"
        step = ProgramStep(step_index=1, step_type="PROC_STEP", name="ADSL", source_code=sas)
        r_code, conf, method = self.r_engine.translate_step(step)

        try:
            res_df, _ = run_r_subprocess(r_code, input_df, env_dict={"DM": input_df})
            # Expect only P1 to remain (populated value), excluding both "" and NA
            self.assertEqual(len(res_df), 1)
            self.assertEqual(res_df.iloc[0]["USUBJID"], "P1")
        except RuntimeError as e:
            if "there is no package called" in str(e):
                pass
            else:
                raise


if __name__ == "__main__":
    unittest.main()
