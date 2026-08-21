import unittest
import os
import sys

sys.path.insert(0, os.path.abspath("."))

from sas_ast import ProgramStep
from rule_engine import RuleEngine


class TestDataStepNormalization(unittest.TestCase):

    def setUp(self):
        self.r_engine = RuleEngine(dialect="Modern R (tidyverse)")

    def test_a_singleline_simple_assignment(self):
        sas = "data ADSL; set DM; AGE_MONTHS = AGE * 12; run;"
        p_step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas, input_datasets=["DM"], output_datasets=["ADSL"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNotNone(code)
        self.assertIn("AGE_MONTHS = AGE * 12", code)

    def test_b_multiline_simple_assignment(self):
        sas = """data ADSL;
    set DM;
    AGE_MONTHS = AGE * 12;
run;"""
        p_step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas, input_datasets=["DM"], output_datasets=["ADSL"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNotNone(code)
        self.assertIn("AGE_MONTHS = AGE * 12", code)

    def test_c_singleline_if_then(self):
        sas = 'data ADSL; set DM; if AGE >= 65 then AGEGR1 = "OLD"; run;'
        p_step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas, input_datasets=["DM"], output_datasets=["ADSL"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNotNone(code)
        self.assertIn("AGEGR1 = case_when", code)
        self.assertIn("AGE >= 65 ~ \"OLD\"", code)

    def test_d_multiline_if_then(self):
        sas = """data ADSL;
    set DM;
    if AGE >= 65 then
        AGEGR1 = "OLD";
run;"""
        p_step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas, input_datasets=["DM"], output_datasets=["ADSL"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNotNone(code)
        self.assertIn("AGEGR1 = case_when", code)
        self.assertIn("AGE >= 65 ~ \"OLD\"", code)

    def test_e_singleline_if_then_else(self):
        sas = 'data ADSL; set DM; if SEX = "F" then SEX_LABEL = "FEMALE"; else SEX_LABEL = "MALE"; run;'
        p_step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas, input_datasets=["DM"], output_datasets=["ADSL"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNotNone(code)
        self.assertIn("SEX_LABEL = case_when", code)
        self.assertIn("SEX == \"F\" ~ \"FEMALE\"", code)
        self.assertIn("TRUE ~ \"MALE\"", code)

    def test_f_multiple_assignments_one_line(self):
        sas = "data ADSL; set DM; AGE_MONTHS = AGE * 12; AGE_YEARS = AGE; RISK_SCORE = AGE * 2 + BASELINE; run;"
        p_step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas, input_datasets=["DM"], output_datasets=["ADSL"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNotNone(code)
        self.assertIn("AGE_MONTHS = AGE * 12", code)
        self.assertIn("AGE_YEARS = AGE", code)
        self.assertIn("RISK_SCORE = AGE * 2 + BASELINE", code)

    def test_g_negative_comparison(self):
        sas = "data ADSL; set DM; if AGE >= 65; run;"
        p_step = ProgramStep(step_index=1, step_type="DATA_STEP", name="ADSL", source_code=sas, input_datasets=["DM"], output_datasets=["ADSL"])
        code, conf, method = self.r_engine.translate_step(p_step)
        self.assertIsNotNone(code)
        self.assertIn("filter(AGE >= 65)", code)
        self.assertNotIn("AGE = ", code)


if __name__ == "__main__":
    unittest.main()
