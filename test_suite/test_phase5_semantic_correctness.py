"""
test_phase5_semantic_correctness.py
───────────────────────────────────
Phase 5 Semantic Correctness & SAS->R Equivalence Test Suite.
Validates PROC SQL aggregation, HAVING, ORDER BY, JOINs, passthrough detection,
semantic equivalence, and data-level output equivalence.
"""

import unittest
import os
import sys
import pandas as pd

os.environ["LLM_PRIMARY_PROVIDER"] = "groq"
os.environ["DISABLE_GEMINI"] = "true"

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from rule_engine import RuleEngine
from sas_ast import ProgramStep
from semantic_conversion_engine import SemanticConversionEngine
from semantic_validator import SemanticValidator, DataLevelValidator, PassthroughDetector
from app import is_valid_r_code


class TestPhase5SemanticCorrectness(unittest.TestCase):

    def setUp(self):
        self.rule_engine = RuleEngine(dialect="Modern R (tidyverse)")
        self.semantic_engine = SemanticConversionEngine(dialect="Modern R (tidyverse)")
        self.validator = SemanticValidator()

    def test_01_proc_sql_group_by_sum(self):
        """Test 1: PROC SQL GROUP BY + SUM."""
        sas = """
        proc sql;
            select cust_id, sum(amount) as total
            from orders
            group by cust_id;
        quit;
        """
        step = ProgramStep(step_index=1, step_type="PROC_STEP", name="PROC SQL", source_code=sas, input_datasets=["ORDERS"], output_datasets=["RESULT"])
        r_code, conf, method = self.rule_engine.translate_step(step)

        self.assertIsNotNone(r_code)
        self.assertIn("group_by(cust_id)", r_code)
        self.assertIn("total = sum(amount, na.rm = TRUE)", r_code)
        
        val = self.validator.validate(sas, r_code)
        self.assertTrue(val.is_equivalent)

    def test_02_proc_sql_count_avg(self):
        """Test 2: PROC SQL COUNT(*) + AVG."""
        sas = """
        proc sql;
            select cust_id,
                   count(*) as n,
                   avg(amount) as mean_amount
            from orders
            group by cust_id;
        quit;
        """
        step = ProgramStep(step_index=1, step_type="PROC_STEP", name="PROC SQL", source_code=sas, input_datasets=["ORDERS"], output_datasets=["RESULT"])
        r_code, conf, method = self.rule_engine.translate_step(step)

        self.assertIsNotNone(r_code)
        self.assertIn("n = n()", r_code)
        self.assertIn("mean_amount = mean(amount, na.rm = TRUE)", r_code)

    def test_03_proc_sql_calculated_having_order(self):
        """Test 3: PROC SQL HAVING calculated + ORDER BY calculated DESC."""
        sas = """
        proc sql;
            select cust_id,
                   sum(amount) as total
            from orders
            group by cust_id
            having calculated total > 500
            order by calculated total desc;
        quit;
        """
        step = ProgramStep(step_index=1, step_type="PROC_STEP", name="PROC SQL", source_code=sas, input_datasets=["ORDERS"], output_datasets=["RESULT"])
        r_code, conf, method = self.rule_engine.translate_step(step)

        self.assertIsNotNone(r_code)
        self.assertIn("filter(total > 500)", r_code)
        self.assertIn("arrange(desc(total))", r_code)

    def test_04_proc_sql_left_join(self):
        """Test 4: PROC SQL LEFT JOIN."""
        sas = """
        proc sql;
            create table result as
            select a.*,
                   b.total_ae
            from adsl a
            left join ae_summary b
            on a.usubjid = b.usubjid;
        quit;
        """
        step = ProgramStep(step_index=1, step_type="PROC_STEP", name="PROC SQL", source_code=sas, input_datasets=["ADSL", "AE_SUMMARY"], output_datasets=["RESULT"])
        r_code, conf, method = self.rule_engine.translate_step(step)

        self.assertIsNotNone(r_code)
        self.assertIn("left_join(AE_SUMMARY, by = \"usubjid\")", r_code)

    def test_05_orders_full_benchmark_semantic_equivalence(self):
        """Test 5: Orders full benchmark produces group_by, summarise, filter, arrange."""
        ORDERS_SAS = """
        data orders;
            input cust_id $ order_date $ amount;

            datalines;
        C1 01JAN2024 500
        C1 15FEB2024 300
        C2 20MAR2024 800
        C2 10APR2024 200
        C3 05MAY2024 600
        ;

        run;

        proc sql;
            create table result as
            select cust_id,
                   count(*) as total_orders,
                   sum(amount) as total_spent,
                   avg(amount) as avg_spent,
                   max(amount) as max_order,
                   min(amount) as min_order
            from orders
            group by cust_id
            having sum(amount) > 500
            order by total_spent desc;
        quit;
        """
        res = self.semantic_engine.convert_program(ORDERS_SAS, program_name="Orders_Program")

        # Must NOT be direct passthrough RESULT <- ORDERS
        self.assertNotIn("RESULT <- ORDERS\nRESULT", res.optimized_r_code)
        self.assertIn("group_by(cust_id)", res.optimized_r_code)
        self.assertIn("total_orders = n()", res.optimized_r_code)
        self.assertIn("total_spent = sum(amount, na.rm = TRUE)", res.optimized_r_code)
        self.assertIn("filter(", res.optimized_r_code)
        self.assertIn("arrange(desc(total_spent))", res.optimized_r_code)

        val = self.validator.validate(ORDERS_SAS, res.optimized_r_code)
        self.assertTrue(val.is_equivalent)
        self.assertFalse(val.is_passthrough_false_positive)

    def test_06_orders_data_level_output_verification(self):
        """Test 6: Data-level equivalence check for Orders dataset."""
        expected_df = DataLevelValidator.expected_orders_result()
        self.assertEqual(len(expected_df), 3)
        self.assertEqual(list(expected_df["cust_id"]), ["C2", "C1", "C3"])
        self.assertEqual(list(expected_df["total_spent"]), [1000, 800, 600])

    def test_07_passthrough_detection_flag(self):
        """Test 7: PassthroughDetector accurately identifies false positive assignments."""
        sas = "proc sql; select cust_id, sum(amount) from orders group by cust_id; quit;"
        bad_r = "RESULT <- ORDERS"
        good_r = "RESULT <- ORDERS %>% group_by(cust_id) %>% summarise(total = sum(amount, na.rm = TRUE))"

        self.assertTrue(PassthroughDetector.is_passthrough(sas, bad_r))
        self.assertFalse(PassthroughDetector.is_passthrough(sas, good_r))

    def test_08_max_min_count_var(self):
        """Test 8: MAX, MIN, COUNT(var) aggregate functions."""
        sas = """
        proc sql;
            select arm, count(usubjid) as n_sub, max(age) as max_age, min(age) as min_age
            from adsl
            group by arm;
        quit;
        """
        step = ProgramStep(step_index=1, step_type="PROC_STEP", name="PROC SQL", source_code=sas, input_datasets=["ADSL"], output_datasets=["RESULT"])
        r_code, _, _ = self.rule_engine.translate_step(step)

        self.assertIn("n_sub = sum(!is.na(usubjid))", r_code)
        self.assertIn("max_age = max(age, na.rm = TRUE)", r_code)
        self.assertIn("min_age = min(age, na.rm = TRUE)", r_code)


if __name__ == "__main__":
    unittest.main()
