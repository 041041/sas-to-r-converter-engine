import unittest
import os
import sys

sys.path.insert(0, os.path.abspath("."))

from sas_parser import parse_sas_program
from rule_engine import RuleEngine
from sas_step_converter import SASStepConverter
from app import is_valid_r_code, validate_r_syntax
from semantic_validator import extract_expected_sas_columns, validate_semantic_completeness


class TestMultistepProgramDispatch(unittest.TestCase):

    def setUp(self):
        self.r_engine = RuleEngine(dialect="Modern R (tidyverse)")
        self.converter = SASStepConverter(dialect="Modern R (tidyverse)")

    def _convert_multistep_sas(self, sas_code):
        ast = parse_sas_program(sas_code)
        r_blocks = []
        for step in ast.steps:
            code, conf, method = self.r_engine.translate_step(step)
            if code:
                r_blocks.append(code)
        return "\n\n".join(r_blocks) if r_blocks else None

    def test_a_data_plus_proc_sql(self):
        sas = "data ADSL; set SDTM.DM; if AGE >= 18; run; proc sql; create table ADAE as select a.USUBJID, b.AEDECOD from ADSL as a inner join AE as b on a.USUBJID = b.USUBJID; quit;"
        r_code = self._convert_multistep_sas(sas)
        self.assertIsNotNone(r_code)
        self.assertTrue(is_valid_r_code(r_code))
        self.assertTrue(validate_r_syntax(r_code))
        self.assertIn("ADSL <- DM", r_code)
        self.assertIn("ADAE <- ADSL", r_code)
        is_c, _, _, miss_c = validate_semantic_completeness(sas, r_code)
        self.assertTrue(is_c, f"Missing columns: {miss_c}")

    def test_b_proc_sql_plus_data(self):
        sas = "proc sql; create table DM_SUB as select USUBJID, AGE from SDTM.DM where AGE >= 18; quit; data ADSL; set DM_SUB; AGE_MONTHS = AGE * 12; run;"
        r_code = self._convert_multistep_sas(sas)
        self.assertIsNotNone(r_code)
        self.assertTrue(is_valid_r_code(r_code))
        self.assertTrue(validate_r_syntax(r_code))
        self.assertIn("DM_SUB <- DM", r_code)
        self.assertIn("ADSL <- DM_SUB", r_code)
        is_c, _, _, miss_c = validate_semantic_completeness(sas, r_code)
        self.assertTrue(is_c, f"Missing columns: {miss_c}")

    def test_c_two_data_steps(self):
        sas = "data ADSL; set SDTM.DM; if AGE >= 18; run; data ADSL2; set ADSL; AGE_MONTHS = AGE * 12; run;"
        r_code = self._convert_multistep_sas(sas)
        self.assertIsNotNone(r_code)
        self.assertTrue(is_valid_r_code(r_code))
        self.assertTrue(validate_r_syntax(r_code))
        self.assertIn("ADSL <- DM", r_code)
        self.assertIn("ADSL2 <- ADSL", r_code)
        is_c, _, _, miss_c = validate_semantic_completeness(sas, r_code)
        self.assertTrue(is_c, f"Missing columns: {miss_c}")

    def test_d_two_proc_sql_steps(self):
        sas = "proc sql; create table DM_SUB as select USUBJID, AGE from SDTM.DM where AGE >= 18; quit; proc sql; create table SUMMARY as select count(*) as N from DM_SUB; quit;"
        r_code = self._convert_multistep_sas(sas)
        self.assertIsNotNone(r_code)
        self.assertTrue(is_valid_r_code(r_code))
        self.assertTrue(validate_r_syntax(r_code))
        self.assertIn("DM_SUB <- DM", r_code)
        self.assertIn("SUMMARY <- DM_SUB", r_code)
        is_c, _, _, miss_c = validate_semantic_completeness(sas, r_code)
        self.assertTrue(is_c, f"Missing columns: {miss_c}")

    def test_e_single_step_regression(self):
        sas = "proc sql; create table ADSL as select USUBJID, AGE from SDTM.DM where AGE >= 65; quit;"
        r_code = self._convert_multistep_sas(sas)
        self.assertIsNotNone(r_code)
        self.assertTrue(is_valid_r_code(r_code))
        self.assertTrue(validate_r_syntax(r_code))
        self.assertIn("ADSL <- DM", r_code)
        is_c, _, _, miss_c = validate_semantic_completeness(sas, r_code)
        self.assertTrue(is_c, f"Missing columns: {miss_c}")

    def test_f_case_34_exact(self):
        sas = """data ADSL;
    set SDTM.DM;
    if AGE >= 18;
run;

proc sql;
    create table ADAE as
    select
        a.USUBJID,
        b.AEDECOD
    from ADSL as a
    inner join AE as b
        on a.USUBJID = b.USUBJID;
quit;"""
        r_code = self._convert_multistep_sas(sas)
        self.assertIsNotNone(r_code)
        self.assertTrue(is_valid_r_code(r_code))
        self.assertTrue(validate_r_syntax(r_code))
        self.assertIn("ADSL <- DM", r_code)
        self.assertIn("ADAE <- ADSL", r_code)
        self.assertIn("USUBJID", r_code)
        self.assertIn("AEDECOD", r_code)
        is_c, _, _, miss_c = validate_semantic_completeness(sas, r_code)
        self.assertTrue(is_c, f"Missing columns: {miss_c}")

    def test_g_case_35_exact(self):
        sas = """data ADSL;
    set SDTM.DM;
    AGE_GROUP = ifc(AGE >= 65, 'OLD', 'YOUNG');
run;

proc sql;
    create table SUMMARY as
    select
        AGE_GROUP,
        count(*) as N
    from ADSL
    group by AGE_GROUP;
quit;"""
        r_code = self._convert_multistep_sas(sas)
        self.assertIsNotNone(r_code)
        self.assertTrue(is_valid_r_code(r_code))
        self.assertTrue(validate_r_syntax(r_code))
        self.assertIn("ADSL <- DM", r_code)
        self.assertIn("SUMMARY <- ADSL", r_code)
        self.assertIn("AGE_GROUP", r_code)
        self.assertIn("N =", r_code)
        is_c, _, _, miss_c = validate_semantic_completeness(sas, r_code)
        self.assertTrue(is_c, f"Missing columns: {miss_c}")


if __name__ == "__main__":
    unittest.main()
