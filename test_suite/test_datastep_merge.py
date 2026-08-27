import unittest
import os
import sys

sys.path.insert(0, os.path.abspath("."))

from sas_ast import ProgramStep
from rule_engine import RuleEngine
from app import is_valid_r_code, validate_r_syntax, run_r_subprocess
import pandas as pd


class TestDataStepMerge(unittest.TestCase):

    def setUp(self):
        self.r_engine = RuleEngine(dialect="Modern R (tidyverse)")

    def test_a_merge_if_a_and_b(self):
        sas = """data ADSL;
    merge DM(in=a) AE(in=b);
    by USUBJID;
    if a and b;
run;"""
        step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas)
        r_code, conf, method = self.r_engine.translate_step(step)
        self.assertIsNotNone(r_code)
        self.assertEqual(method, "Rule_DataStepMerge")
        self.assertEqual(conf, 0.90)
        self.assertIn("dplyr::inner_join", r_code)
        self.assertIn('by = "USUBJID"', r_code)
        self.assertTrue(is_valid_r_code(r_code))
        self.assertTrue(validate_r_syntax(r_code))

    def test_b_merge_if_a(self):
        sas = """data ADSL;
    merge DM(in=a) AE(in=b);
    by USUBJID;
    if a;
run;"""
        step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas)
        r_code, conf, method = self.r_engine.translate_step(step)
        self.assertIsNotNone(r_code)
        self.assertIn("dplyr::left_join", r_code)
        self.assertTrue(is_valid_r_code(r_code))
        self.assertTrue(validate_r_syntax(r_code))

    def test_c_merge_if_b(self):
        sas = """data ADSL;
    merge DM(in=a) AE(in=b);
    by USUBJID;
    if b;
run;"""
        step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas)
        r_code, conf, method = self.r_engine.translate_step(step)
        self.assertIsNotNone(r_code)
        self.assertIn("dplyr::right_join", r_code)
        self.assertTrue(is_valid_r_code(r_code))
        self.assertTrue(validate_r_syntax(r_code))

    def test_d_two_level_dataset_names(self):
        sas = "data ADSL; merge SDTM.DM(in=a) WORK.AE(in=b); by USUBJID; if a and b; run;"
        step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas)
        r_code, conf, method = self.r_engine.translate_step(step)
        self.assertIsNotNone(r_code)
        self.assertIn("DM %>%", r_code)
        self.assertIn("dplyr::inner_join(\n    AE,", r_code)
        self.assertTrue(is_valid_r_code(r_code))
        self.assertTrue(validate_r_syntax(r_code))

    def test_e_multiline_merge(self):
        sas = """data ADSL;
    merge DM(in=a) 
          AE(in=b);
    by USUBJID;
    if a and b;
run;"""
        step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas)
        r_code, conf, method = self.r_engine.translate_step(step)
        self.assertIsNotNone(r_code)
        self.assertIn("dplyr::inner_join", r_code)

    def test_f_single_line_merge(self):
        sas = "data ADSL; merge DM(in=a) AE(in=b); by USUBJID; if a and b; run;"
        step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas)
        r_code, conf, method = self.r_engine.translate_step(step)
        self.assertIsNotNone(r_code)
        self.assertIn("dplyr::inner_join", r_code)

    def test_g_negative_no_by_clause(self):
        sas = "data ADSL; merge DM(in=a) AE(in=b); if a and b; run;"
        step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas)
        r_code, conf, method = self.r_engine.translate_step(step)
        self.assertIsNone(r_code)

    def test_h_negative_three_datasets(self):
        sas = "data ADSL; merge DM(in=a) AE(in=b) EX(in=c); by USUBJID; if a and b; run;"
        step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas)
        r_code, conf, method = self.r_engine.translate_step(step)
        self.assertIsNone(r_code)

    def test_i_negative_multiple_by_variables(self):
        sas = "data ADSL; merge DM(in=a) AE(in=b); by USUBJID VISIT; if a and b; run;"
        step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas)
        r_code, conf, method = self.r_engine.translate_step(step)
        self.assertIsNone(r_code)

    def test_j_negative_unhandled_do_loop(self):
        sas = "data ADSL; merge DM(in=a) AE(in=b); by USUBJID; do i=1 to 5; x=i; output; end; run;"
        step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas)
        r_code, conf, method = self.r_engine.translate_step(step)
        self.assertIsNone(r_code)

    def test_k_execution_and_value_equivalence(self):
        df_dm = pd.DataFrame({"USUBJID": ["P1", "P2"], "AGE": [50, 60]})
        df_ae = pd.DataFrame({"USUBJID": ["P1", "P3"], "AEDECOD": ["HEADACHE", "NAUSEA"]})
        sas = "data ADSL; merge DM(in=a) AE(in=b); by USUBJID; if a and b; run;"
        step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas)
        r_code, conf, method = self.r_engine.translate_step(step)

        try:
            res_df, _ = run_r_subprocess(r_code, df_dm, env_dict={"DM": df_dm, "AE": df_ae})
            self.assertEqual(len(res_df), 1)
            self.assertEqual(res_df.iloc[0]["USUBJID"], "P1")
            self.assertEqual(res_df.iloc[0]["AGE"], 50)
            self.assertEqual(res_df.iloc[0]["AEDECOD"], "HEADACHE")
        except RuntimeError as e:
            if "there is no package called" in str(e):
                pass
            else:
                raise


if __name__ == "__main__":
    unittest.main()
