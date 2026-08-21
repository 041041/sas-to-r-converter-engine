import unittest
import os
import sys

sys.path.insert(0, os.path.abspath("."))

from semantic_validator import extract_expected_sas_columns


class TestDataStepColumnExtraction(unittest.TestCase):

    def test_a_simple_assignment(self):
        sas = "data ADSL; set SDTM.DM; AGE_MONTHS = AGE * 12; run;"
        cols = extract_expected_sas_columns(sas)
        self.assertEqual(cols, ["AGE_MONTHS"])

    def test_b_if_then_assignment(self):
        sas = 'data ADSL; set SDTM.DM; if AGE >= 65 then AGEGR1 = "OLD"; run;'
        cols = extract_expected_sas_columns(sas)
        self.assertEqual(cols, ["AGEGR1"])

    def test_c_if_then_else_assignment(self):
        sas = 'data ADSL; set SDTM.DM; if SEX = "F" then SEX_LABEL = "FEMALE"; else SEX_LABEL = "MALE"; run;'
        cols = extract_expected_sas_columns(sas)
        self.assertEqual(cols, ["SEX_LABEL"])

    def test_d_multiline_assignment(self):
        sas = """data ADSL;
            set SDTM.DM;
            if AGE >= 65 then
                AGEGR1 = "OLD";
        run;"""
        cols = extract_expected_sas_columns(sas)
        self.assertEqual(cols, ["AGEGR1"])

    def test_e_multiple_assignments(self):
        sas = """data ADSL;
            set SDTM.DM;
            AGE_MONTHS = AGE * 12;
            AGE_YEARS = AGE;
            RISK_SCORE = AGE * 2 + BASELINE;
        run;"""
        cols = extract_expected_sas_columns(sas)
        self.assertEqual(cols, ["AGE_MONTHS", "AGE_YEARS", "RISK_SCORE"])

    def test_f_negative_comparison(self):
        sas = "data ADSL; set SDTM.DM; if AGE >= 65; run;"
        cols = extract_expected_sas_columns(sas)
        self.assertEqual(cols, [])

    def test_g_clinical_test_case(self):
        sas = """data ADSL_DERIVED;
    set ADSL;

    AGE_MONTHS = AGE * 12;

    if AGE >= 65 then
        AGE_GROUP = "ELDERLY";
    else if AGE >= 50 then
        AGE_GROUP = "MIDDLE";
    else
        AGE_GROUP = "YOUNG";

    BASELINE_CHANGE = BASELINE * 0.10;

    if SEX = "F" then
        SEX_LABEL = "FEMALE";
    else
        SEX_LABEL = "MALE";
run;"""
        cols = extract_expected_sas_columns(sas)
        self.assertEqual(cols, ["AGE_MONTHS", "AGE_GROUP", "BASELINE_CHANGE", "SEX_LABEL"])


if __name__ == "__main__":
    unittest.main()
