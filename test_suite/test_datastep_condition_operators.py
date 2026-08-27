import unittest
import os
import sys

sys.path.insert(0, os.path.abspath("."))

from sas_ast import ProgramStep
from rule_engine import RuleEngine
from app import is_valid_r_code, validate_r_syntax, run_r_subprocess
import pandas as pd


class TestDataStepConditionOperators(unittest.TestCase):

    def setUp(self):
        self.r_engine = RuleEngine(dialect="Modern R (tidyverse)")

    def test_a_char_ne_empty_string(self):
        sas = """data ADSL;
    set DM;
    if EXSTDTC ne '' then SAFFL = 'Y';
    else SAFFL = 'N';
run;"""
        step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas)
        r_code, conf, method = self.r_engine.translate_step(step)
        self.assertIsNotNone(r_code)
        self.assertIn("!is.na(EXSTDTC)", r_code)
        self.assertIn('EXSTDTC != ""', r_code)
        self.assertTrue(is_valid_r_code(r_code))
        self.assertTrue(validate_r_syntax(r_code))

    def test_b_char_ne_non_empty(self):
        sas = "data ADSL; set DM; if EXSTDTC ne 'ABC' then FLAG = 'Y'; run;"
        step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas)
        r_code, conf, method = self.r_engine.translate_step(step)
        self.assertIsNotNone(r_code)
        self.assertIn("EXSTDTC != 'ABC'", r_code)
        self.assertTrue(validate_r_syntax(r_code))

    def test_c_numeric_ne(self):
        sas = "data ADSL; set DM; if AGE ne 65 then FLAG = 'Y'; run;"
        step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas)
        r_code, conf, method = self.r_engine.translate_step(step)
        self.assertIsNotNone(r_code)
        self.assertIn("AGE != 65", r_code)
        self.assertTrue(validate_r_syntax(r_code))

    def test_d_eq(self):
        sas = "data ADSL; set DM; if AGE eq 65 then FLAG = 'Y'; run;"
        step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas)
        r_code, conf, method = self.r_engine.translate_step(step)
        self.assertIsNotNone(r_code)
        self.assertIn("AGE == 65", r_code)
        self.assertTrue(validate_r_syntax(r_code))

    def test_e_gt(self):
        sas = "data ADSL; set DM; if AGE gt 65 then FLAG = 'Y'; run;"
        step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas)
        r_code, conf, method = self.r_engine.translate_step(step)
        self.assertIsNotNone(r_code)
        self.assertIn("AGE > 65", r_code)
        self.assertTrue(validate_r_syntax(r_code))

    def test_f_ge(self):
        sas = "data ADSL; set DM; if AGE ge 65 then FLAG = 'Y'; run;"
        step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas)
        r_code, conf, method = self.r_engine.translate_step(step)
        self.assertIsNotNone(r_code)
        self.assertIn("AGE >= 65", r_code)
        self.assertTrue(validate_r_syntax(r_code))

    def test_g_lt(self):
        sas = "data ADSL; set DM; if AGE lt 65 then FLAG = 'Y'; run;"
        step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas)
        r_code, conf, method = self.r_engine.translate_step(step)
        self.assertIsNotNone(r_code)
        self.assertIn("AGE < 65", r_code)
        self.assertTrue(validate_r_syntax(r_code))

    def test_h_le(self):
        sas = "data ADSL; set DM; if AGE le 65 then FLAG = 'Y'; run;"
        step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas)
        r_code, conf, method = self.r_engine.translate_step(step)
        self.assertIsNotNone(r_code)
        self.assertIn("AGE <= 65", r_code)
        self.assertTrue(validate_r_syntax(r_code))

    def test_i_caret_equal(self):
        sas = "data ADSL; set DM; if AGE ^= 65 then FLAG = 'Y'; run;"
        step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas)
        r_code, conf, method = self.r_engine.translate_step(step)
        self.assertIsNotNone(r_code)
        self.assertIn("AGE != 65", r_code)
        self.assertTrue(validate_r_syntax(r_code))

    def test_j_and(self):
        sas = "data ADSL; set DM; if AGE ge 65 and SEX eq 'F' then FLAG = 'Y'; run;"
        step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas)
        r_code, conf, method = self.r_engine.translate_step(step)
        self.assertIsNotNone(r_code)
        self.assertIn("AGE >= 65 & SEX == 'F'", r_code)
        self.assertTrue(validate_r_syntax(r_code))

    def test_k_or(self):
        sas = "data ADSL; set DM; if SEX eq 'F' or SEX eq 'M' then FLAG = 'Y'; run;"
        step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas)
        r_code, conf, method = self.r_engine.translate_step(step)
        self.assertIsNotNone(r_code)
        self.assertIn("SEX == 'F' | SEX == 'M'", r_code)
        self.assertTrue(validate_r_syntax(r_code))

    def test_l_existing_equals(self):
        sas = "data ADSL; set DM; if AGE = 65 then FLAG = 'Y'; run;"
        step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas)
        r_code, conf, method = self.r_engine.translate_step(step)
        self.assertIsNotNone(r_code)
        self.assertIn("AGE == 65", r_code)
        self.assertTrue(validate_r_syntax(r_code))

    def test_m_regression_if_then_else(self):
        sas = "data ADSL; set DM; if AGE >= 65 then AGEGR = 'OLD'; else AGEGR = 'YOUNG'; run;"
        step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas)
        r_code, conf, method = self.r_engine.translate_step(step)
        self.assertIsNotNone(r_code)
        self.assertIn("AGE >= 65 ~ 'OLD'", r_code)
        self.assertTrue(validate_r_syntax(r_code))

    def test_n_date_literal_regression(self):
        sas = "data ADSL; set DM; if EXSTDTC >= '01JAN2024'd then FLAG = 'Y'; run;"
        step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas)
        r_code, conf, method = self.r_engine.translate_step(step)
        self.assertIsNotNone(r_code)
        self.assertIn('as.Date("2024-01-01")', r_code)
        self.assertTrue(validate_r_syntax(r_code))

    def test_o_string_safety(self):
        sas = "data ADSL; set DM; if ARM eq 'PLACEBO AND CONTROL' then FLAG = 'Y'; run;"
        step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas)
        r_code, conf, method = self.r_engine.translate_step(step)
        self.assertIsNotNone(r_code)
        self.assertIn("ARM == 'PLACEBO AND CONTROL'", r_code)
        self.assertTrue(validate_r_syntax(r_code))

    def test_g4_execution_and_value_equivalence(self):
        df_dm = pd.DataFrame({"USUBJID": ["P1", "P2", "P3"], "EXSTDTC": ["2024-01-01", "", None]})
        sas = """data ADSL;
    set DM;
    if EXSTDTC ne '' then SAFFL = 'Y';
    else SAFFL = 'N';
run;"""
        step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas)
        r_code, conf, method = self.r_engine.translate_step(step)

        try:
            res_df, _ = run_r_subprocess(r_code, df_dm, env_dict={"DM": df_dm})
            self.assertEqual(len(res_df), 3)
            self.assertEqual(list(res_df["SAFFL"]), ["Y", "N", "N"])
        except RuntimeError as e:
            if "there is no package called" in str(e):
                pass
            else:
                raise


if __name__ == "__main__":
    unittest.main()
