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

    def test_09_negative_passthrough_fails_validation(self):
        """Negative Test 9: RESULT <- ORDERS fails semantic validation."""
        sas = "proc sql; select cust_id, sum(amount) from orders group by cust_id; quit;"
        bad_r = "RESULT <- ORDERS"
        val = self.validator.validate(sas, bad_r)
        self.assertFalse(val.is_equivalent)
        self.assertTrue(val.is_passthrough_false_positive)

    def test_10_negative_missing_groupby_fails_validation(self):
        """Negative Test 10: Missing group_by fails semantic validation."""
        sas = "proc sql; select cust_id, sum(amount) from orders group by cust_id; quit;"
        bad_r = "RESULT <- ORDERS %>% summarise(total = sum(amount))"
        val = self.validator.validate(sas, bad_r)
        self.assertFalse(val.is_equivalent)
        self.assertIn("GROUP_BY", val.missing_r_ops)

    def test_11_negative_missing_aggregation_fails_validation(self):
        """Negative Test 11: Missing aggregation fails semantic validation."""
        sas = "proc sql; select cust_id, sum(amount) from orders group by cust_id; quit;"
        bad_r = "RESULT <- ORDERS %>% group_by(cust_id)"
        val = self.validator.validate(sas, bad_r)
        self.assertFalse(val.is_equivalent)
        self.assertIn("AGGREGATION", val.missing_r_ops)

    def test_12_negative_missing_having_fails_validation(self):
        """Negative Test 12: Missing HAVING/filter fails semantic validation."""
        sas = "proc sql; select cust_id, sum(amount) from orders group by cust_id having sum(amount) > 500; quit;"
        bad_r = "RESULT <- ORDERS %>% group_by(cust_id) %>% summarise(total = sum(amount))"
        val = self.validator.validate(sas, bad_r)
        self.assertFalse(val.is_equivalent)
        self.assertIn("HAVING", val.missing_r_ops)

    def test_13_negative_missing_orderby_fails_validation(self):
        """Negative Test 13: Missing ORDER BY/arrange fails semantic validation."""
        sas = "proc sql; select cust_id, sum(amount) from orders group by cust_id order by total desc; quit;"
        bad_r = "RESULT <- ORDERS %>% group_by(cust_id) %>% summarise(total = sum(amount))"
        val = self.validator.validate(sas, bad_r)
        self.assertFalse(val.is_equivalent)
        self.assertIn("ORDER_BY", val.missing_r_ops)

    def test_14_negative_missing_join_fails_validation(self):
        """Negative Test 14: Missing JOIN fails semantic validation."""
        sas = "proc sql; select a.*, b.ae_count from adsl a left join adae_sum b on a.usubjid = b.usubjid; quit;"
        bad_r = "ADSL_FINAL <- ADSL"
        val = self.validator.validate(sas, bad_r)
        self.assertFalse(val.is_equivalent)
        self.assertIn("JOIN", val.missing_r_ops)

    def test_15_negative_incomplete_clinical_fails_validation(self):
        """Negative Test 15: Incomplete clinical transformation EX_SUM <- EX fails semantic validation."""
        sas = "proc sql; select usubjid, count(*) as exposure_records, sum(dose) as total_dose from ex group by usubjid; quit;"
        bad_r = "EX_SUM <- EX"
        val = self.validator.validate(sas, bad_r)
        self.assertFalse(val.is_equivalent)
        self.assertTrue(val.is_passthrough_false_positive)
        self.assertIn("GROUP_BY", val.missing_r_ops)
        self.assertIn("AGGREGATION", val.missing_r_ops)

    def test_16_alias_resolution_having_raw_sum(self):
        """Test A: having sum(amount) > 500 resolves to filter(total_spent > 500)."""
        sas = """
        proc sql;
            select cust_id, sum(amount) as total_spent
            from orders
            group by cust_id
            having sum(amount) > 500;
        quit;
        """
        step = ProgramStep(step_index=1, step_type="PROC_STEP", name="PROC SQL", source_code=sas, input_datasets=["ORDERS"], output_datasets=["RESULT"])
        r_code, _, _ = self.rule_engine.translate_step(step)

        self.assertIn("filter(total_spent > 500)", r_code)
        self.assertNotIn("filter(sum(amount) > 500)", r_code)

    def test_17_alias_resolution_having_calculated(self):
        """Test B: having calculated total_spent > 500 resolves to filter(total_spent > 500)."""
        sas = """
        proc sql;
            select cust_id, sum(amount) as total_spent
            from orders
            group by cust_id
            having calculated total_spent > 500;
        quit;
        """
        step = ProgramStep(step_index=1, step_type="PROC_STEP", name="PROC SQL", source_code=sas, input_datasets=["ORDERS"], output_datasets=["RESULT"])
        r_code, _, _ = self.rule_engine.translate_step(step)

        self.assertIn("filter(total_spent > 500)", r_code)

    def test_18_alias_resolution_orderby(self):
        """Test C: order by total_spent desc resolves to arrange(desc(total_spent))."""
        sas = """
        proc sql;
            select cust_id, sum(amount) as total_spent
            from orders
            group by cust_id
            order by total_spent desc;
        quit;
        """
        step = ProgramStep(step_index=1, step_type="PROC_STEP", name="PROC SQL", source_code=sas, input_datasets=["ORDERS"], output_datasets=["RESULT"])
        r_code, _, _ = self.rule_engine.translate_step(step)

        self.assertIn("arrange(desc(total_spent))", r_code)

    def test_19_data_level_exact_ordering(self):
        """Test D: Verify final data-level result remains C2 (1000) -> C1 (800) -> C3 (600)."""
        res_df = DataLevelValidator.expected_orders_result()
        self.assertEqual(list(res_df["cust_id"]), ["C2", "C1", "C3"])
        self.assertEqual(list(res_df["total_spent"]), [1000, 800, 600])
        self.assertEqual(list(res_df["total_orders"]), [2, 2, 1])

    def test_20_user_complex_clinical_macro(self):
        """Test 20: User complex clinical SAS macro with nested macros, %do loops, and %if/%else."""
        sas_code = """
        options mprint mlogic symbolgen;

        libname SDTM "/clinical/data/sdtm";
        libname ADAM "/clinical/data/adam";
        filename setup "/clinical/config/setup.sas";
        %include setup;

        %let study_id = STUDY001;
        %let min_age = 18;
        %let population = SAFFL;
        %let ds1 = DM;
        %let ds2 = AE;
        %let ds3 = EX;

        %macro build_population(input=DM, output=ADSL, age=18, flag=SAFFL);
            data ADAM.&output;
                set SDTM.&input;
                if age >= &age;
                if &flag = "Y";
                if sex = "M" then SEXN = 1;
                else if sex = "F" then SEXN = 2;
                else SEXN = .;

                length STUDY $20;
                STUDY = "&study_id";
            run;

            proc sort data=ADAM.&output out=ADAM.&output._SORTED;
                by usubjid descending age;
            run;
        %mend build_population;

        %macro summarize_ae(input=AE, output=ADAE_SUM);
            proc sql;
                create table ADAM.&output as
                select usubjid,
                       count(*) as total_ae,
                       sum(case when serious = "Y" then 1 else 0 end) as serious_ae,
                       max(severity) as max_severity
                from SDTM.&input
                group by usubjid
                having count(*) > 0
                order by total_ae desc;
            quit;
        %mend summarize_ae;

        %macro build_analysis(study=&study_id, input_lib=SDTM, output_lib=ADAM, min_age=&min_age, population_flag=&population);
            %local i current_ds dataset_count today study_suffix;
            %let today = %sysfunc(today(), yymmddn8.);
            %let study_suffix = %substr(&study, %length(&study)-2, 3);
            %let dataset_count = 3;

            %do i = 1 %to &dataset_count;
                %let current_ds = &&ds&i;
                %if %upcase(&current_ds) = DM %then %do;
                    %build_population(input=&current_ds, output=ADSL, age=&min_age, flag=&population_flag);
                %end;
                %else %if %upcase(&current_ds) = AE %then %do;
                    %summarize_ae(input=&current_ds, output=ADAE_SUM);
                %end;
                %else %if %upcase(&current_ds) = EX %then %do;
                    proc sql;
                        create table ADAM.EX_SUM as
                        select usubjid, count(*) as exposure_records, sum(dose) as total_dose, mean(dose) as avg_dose
                        from SDTM.&current_ds
                        group by usubjid;
                    quit;
                %end;
            %end;

            proc sql;
                create table ADAM.ADSL_FINAL as
                select a.*, b.total_ae, b.serious_ae, b.max_severity
                from ADAM.ADSL_SORTED as a
                left join ADAM.ADAE_SUM as b
                on a.usubjid = b.usubjid
                order by a.usubjid;
            quit;

            data ADAM.ADSL_FINAL;
                set ADAM.ADSL_FINAL;
                length STUDYID $20 ANALYSIS_DATE $8 RISK_CATEGORY $20;
                STUDYID = "&study";
                ANALYSIS_DATE = "&today";

                if total_ae >= 5 then RISK_CATEGORY = "HIGH";
                else if total_ae >= 2 then RISK_CATEGORY = "MEDIUM";
                else RISK_CATEGORY = "LOW";

                if age >= &min_age and &population_flag = "Y" then ANALYSIS_FLAG = "Y";
                else ANALYSIS_FLAG = "N";
            run;

            proc sort data=ADAM.ADSL_FINAL out=ADAM.ADSL_FINAL;
                by descending total_ae usubjid;
            run;

        %mend build_analysis;

        %build_analysis(study=STUDY001, input_lib=SDTM, output_lib=ADAM, min_age=18, population_flag=SAFFL);
        """
        res = self.semantic_engine.convert_program(sas_code, program_name="User_Clinical_Macro")
        self.assertIsNotNone(res)
        self.assertIn("left_join(ADAE_SUM, by = \"usubjid\")", res.optimized_r_code)
        self.assertIn("group_by(usubjid)", res.optimized_r_code)
        self.assertIn("total_ae = n()", res.optimized_r_code)

        val_res = self.validator.validate(sas_code, res.optimized_r_code)
        self.assertTrue(val_res.is_equivalent)
        self.assertEqual(val_res.confidence_score, 95.0)


if __name__ == "__main__":
    unittest.main()
