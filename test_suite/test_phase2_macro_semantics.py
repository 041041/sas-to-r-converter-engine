"""
test_suite/test_phase2_macro_semantics.py
──────────────────────────────────────────
Automated Unit & Integration Test Suite for Phase 2 Macro Execution Semantics Engine.
Tests all Phase 2J mandatory regression test cases.
"""

from __future__ import annotations
import unittest
import pandas as pd

from macro_execution_context import MacroExecutionContext
from macro_functions import MacroFunctionRegistry, evaluate_macro_functions_in_text
from macro_semantics_engine import SASMacroSemanticsEngine
import sas_step_converter


class TestPhase2MacroSemantics(unittest.TestCase):

    def setUp(self):
        self.engine = SASMacroSemanticsEngine()

    def test_1_simple_let_and_if(self):
        sas_code = """
        %let age=18;
        data result;
            set dm;
            if age >= &age;
        run;
        """
        expanded, ast, evidence, report = self.engine.process_program(sas_code)
        self.assertIn("filter(age >= 18)", sas_step_converter.SASStepConverter().convert_program(sas_code).full_optimized_r)
        self.assertEqual(report.r_syntax_status, "PASS")

    def test_2_dynamic_reference(self):
        ctx = MacroExecutionContext()
        ctx.set_variable("ds1", "DM")
        ctx.set_variable("ds2", "AE")
        
        ctx.set_variable("i", "1")
        self.assertEqual(ctx.resolve_expression("&&ds&i"), "DM")
        
        ctx.set_variable("i", "2")
        self.assertEqual(ctx.resolve_expression("&&ds&i"), "AE")

    def test_3_nested_macro_scope(self):
        sas_code = """
        %macro outer(data=);
            %macro inner(input=);
                proc sort data=&input;
                run;
            %mend inner;

            %inner(input=&data);
        %mend outer;

        %outer(data=adsl);
        """
        expanded, ast, evidence, report = self.engine.process_program(sas_code)
        self.assertIn("OUTER", ast.macros)
        self.assertIn("INNER", ast.macros)

    def test_4_macro_functions(self):
        txt = "%let name=%upcase(adsl); %let part=%substr(abcdef,2,3); %let n=%length(abcdef);"
        reg = MacroFunctionRegistry()
        self.assertEqual(reg.evaluate("UPCASE", "adsl")[0], "ADSL")
        self.assertEqual(reg.evaluate("SUBSTR", "abcdef, 2, 3")[0], "bcd")
        self.assertEqual(reg.evaluate("LENGTH", "abcdef")[0], "6")

    def test_5_macro_arithmetic(self):
        reg = MacroFunctionRegistry()
        self.assertEqual(reg.evaluate("EVAL", "10 + 20")[0], "30")

    def test_6_dynamic_dataset_generation(self):
        sas_code = """
        %macro gen_loop(count=3);
            %do i=1 %to &count;
                data output_&i;
                    set input_&i;
                run;
            %end;
        %mend gen_loop;

        %gen_loop(count=3);
        """
        expanded, ast, evidence, report = self.engine.process_program(sas_code)
        self.assertIn("output_1", expanded.lower())
        self.assertIn("output_2", expanded.lower())
        self.assertIn("output_3", expanded.lower())

    def test_7_clinical_style_macro(self):
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
        expanded, ast, evidence, report = self.engine.process_program(sas_code)
        self.assertIn("SDTM", ast.infrastructure.libnames)
        self.assertIn("ADAM", ast.infrastructure.libnames)
        self.assertEqual(report.r_syntax_status, "PASS")


if __name__ == "__main__":
    unittest.main()
