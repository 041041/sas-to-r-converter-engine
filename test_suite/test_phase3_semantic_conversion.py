"""
test_suite/test_phase3_semantic_conversion.py
───────────────────────────────────────────────
Automated Unit & Integration Test Suite for Phase 3 Semantic Conversion Engine.
Validates all 12 mandatory Phase 3 test benchmarks.
"""

from __future__ import annotations
import unittest
import pandas as pd

from semantic_conversion_engine import SemanticConversionEngine
from sas_semantic_ir import build_semantic_ir
import sas_parser


class TestPhase3SemanticConversion(unittest.TestCase):

    def setUp(self):
        self.engine = SemanticConversionEngine(dialect="Modern R (tidyverse)")

    def test_1_macro_params_to_r_function(self):
        sas_code = """
        %macro filter_data(input=dm, output=dm_filtered, age=18);
            data &output;
                set &input;
                if age >= &age;
            run;
        %mend filter_data;

        %filter_data(input=dm, output=dm_filtered, age=18);
        """
        res = self.engine.convert_program(sas_code, program_name="Test1_MacroParams")
        self.assertIn("filter_data <- function(", res.r_functions_code)
        self.assertEqual(res.confidence_report.r_syntax_status, "PASS")

    def test_2_macro_if_to_r_conditional(self):
        sas_code = """
        %let flag = Y;
        %macro check_flag();
            %if &flag = Y %then %do;
                proc sort data=dm out=dm_sorted; by usubjid; run;
            %end;
        %mend check_flag;
        %check_flag();
        """
        res = self.engine.convert_program(sas_code, program_name="Test2_MacroIf")
        self.assertIn("dm_sorted", res.optimized_r_code.lower())

    def test_3_macro_do_to_r_loop(self):
        sas_code = """
        %macro loop_test();
            %do i=1 %to 3;
                data out_&i; set in_&i; run;
            %end;
        %mend loop_test;
        %loop_test();
        """
        res = self.engine.convert_program(sas_code, program_name="Test3_MacroDo")
        self.assertIn("out_1", res.optimized_r_code.lower())

    def test_4_dynamic_dataset_names(self):
        sas_code = """
        %macro gen_subsets();
            %let prefix = subset;
            %do i=1 %to 2;
                data &prefix._&i; set raw; if grp = &i; run;
            %end;
        %mend gen_subsets;
        %gen_subsets();
        """
        res = self.engine.convert_program(sas_code, program_name="Test4_DynamicDS")
        self.assertIn("subset_1", res.optimized_r_code.lower())

    def test_5_data_step_vectorized(self):
        sas_code = """
        data adsl;
            set dm;
            if age >= 18;
        run;
        """
        res = self.engine.convert_program(sas_code, program_name="Test5_VectorizedData")
        self.assertIn("filter(age >= 18)", res.optimized_r_code)

    def test_6_proc_sort_arrange(self):
        sas_code = """
        proc sort data=dm out=dm_sorted;
            by arm descending age;
        run;
        """
        res = self.engine.convert_program(sas_code, program_name="Test6_ProcSort")
        self.assertIn("arrange(arm, desc(age))", res.optimized_r_code)

    def test_7_proc_sql_join(self):
        sas_code = """
        proc sql;
            create table adsl as
            select a.usubjid, a.age, b.trt01p
            from dm a
            left join ex b
              on a.usubjid = b.usubjid;
        quit;
        """
        res = self.engine.convert_program(sas_code, program_name="Test7_ProcSqlJoin")
        self.assertIn("left_join", res.optimized_r_code.lower())

    def test_8_proc_freq_count(self):
        sas_code = """
        proc freq data=dm;
            tables sex;
        run;
        """
        res = self.engine.convert_program(sas_code, program_name="Test8_ProcFreq")
        self.assertIn("count", res.optimized_r_code.lower())

    def test_9_proc_means_summarise(self):
        sas_code = """
        proc means data=dm;
            class trt01p;
            var age;
        run;
        """
        res = self.engine.convert_program(sas_code, program_name="Test9_ProcMeans")
        self.assertIn("summarise", res.optimized_r_code.lower())

    def test_10_clinical_macro(self):
        sas_code = """
        libname sdtm "/clinical/sdtm";
        libname adam "/clinical/adam";

        %macro build_clinical_adae(sdtm_lib=sdtm, adam_lib=adam, pop_flag=SAFFL);
            proc sql;
                create table adam.adsl_pop as
                select usubjid, arm, &pop_flag
                from &sdtm_lib..dm
                where &pop_flag = 'Y';
            quit;

            proc sort data=adam.adsl_pop out=adam.adsl_sorted;
                by usubjid;
            run;
        %mend build_clinical_adae;

        %build_clinical_adae(sdtm_lib=sdtm, adam_lib=adam, pop_flag=SAFFL);
        """
        res = self.engine.convert_program(sas_code, program_name="Test10_ClinicalMacro")
        self.assertIn("lib_sdtm <- \"/clinical/sdtm\"", res.optimized_r_code)
        self.assertIn("arrange(usubjid)", res.optimized_r_code)

    def test_11_complex_nested_macro(self):
        sas_code = """
        %macro prepare_data(input=adsl);
            %macro clean_data(data=);
                data &data._clean;
                    set &data;
                    if age >= 18;
                run;
            %mend clean_data;

            %clean_data(data=&input);
        %mend prepare_data;

        %prepare_data(input=adsl);
        """
        res = self.engine.convert_program(sas_code, program_name="Test11_NestedMacro")
        self.assertIn("clean_data", res.r_functions_code.lower())

    def test_12_llm_fallback_case(self):
        sas_code = """
        proc custom_unsupported_proc data=dm;
            custom_statement var1 var2;
        run;
        """
        res = self.engine.convert_program(sas_code, program_name="Test12_LLMFallback")
        self.assertIn("custom_unsupported_proc", res.optimized_r_code.lower())


if __name__ == "__main__":
    unittest.main()
