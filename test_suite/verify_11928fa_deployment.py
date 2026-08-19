"""
verify_11928fa_deployment.py
────────────────────────────
Deployment verification for commit 11928fa.
Verifies session_state clear_all stability, top-level module imports with missing GEMINI_API_KEY,
Groq provider selection, 0 Gemini calls, Orders SAS conversion, Complex Clinical Macro conversion,
and R output contract validation.
"""

import unittest
import os
import sys

os.environ["LLM_PRIMARY_PROVIDER"] = "groq"
os.environ["DISABLE_GEMINI"] = "true"
os.environ.pop("GEMINI_API_KEY", None)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from semantic_conversion_engine import SemanticConversionEngine
from app import is_valid_r_code, clear_all
from llm_router import get_llm_router
from r_optimizer import ROptimizer
import streamlit as st


class TestDeployment11928fa(unittest.TestCase):

    def test_01_module_imports_without_gemini_key(self):
        """Verifies top-level modules import without ValueError when GEMINI_API_KEY is missing."""
        import graph_builder
        import table_builder
        import listing_builder
        import tlf_shell_builder

        self.assertIsNone(graph_builder.gemini_client)
        tb_g, tb_gr = table_builder._make_clients()
        self.assertIsNone(tb_g)

    def test_02_clear_all_session_state_stability(self):
        """Verifies clear_all() executes cleanly without AttributeError when upload_key is absent."""
        if "upload_key" in st.session_state:
            del st.session_state["upload_key"]
        
        # Call clear_all() when key is missing
        clear_all()
        self.assertEqual(st.session_state.upload_key, 1)
        
        # Call clear_all() again when key is present
        clear_all()
        self.assertEqual(st.session_state.upload_key, 2)

    def test_03_groq_primary_zero_gemini_calls(self):
        """Verifies Groq is active primary provider and Gemini calls == 0."""
        router = get_llm_router()
        self.assertEqual(router.primary_provider, "groq")
        self.assertEqual(router.gemini_call_count, 0)

    def test_04_simple_orders_conversion(self):
        """Verifies simple ORDERS SAS example converts to valid executable R."""
        SIMPLE_ORDERS_SAS = """
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
        engine = SemanticConversionEngine(dialect="Modern R (tidyverse)")
        res = engine.convert_program(SIMPLE_ORDERS_SAS, program_name="Orders_Program")

        self.assertTrue(is_valid_r_code(res.optimized_r_code))
        self.assertIn("RESULT <-", res.optimized_r_code)
        
        router = get_llm_router()
        self.assertEqual(router.gemini_call_count, 0)

    def test_05_complex_clinical_macro_conversion(self):
        """Verifies complex clinical macro benchmark converts cleanly without bad R syntax."""
        COMPLEX_SAS = """
        libname SDTM "/clinical/data/sdtm";
        libname ADAM "/clinical/data/adam";
        %let ds1 = DM;
        %let ds2 = AE;
        %let ds3 = EX;

        %macro build_pipeline();
            data ADAM.adsl;
                set SDTM.&ds1;
                if age >= 18;
            run;
            proc sql;
                create table ADAM.ex_sum as
                select usubjid, count(*) as exposure_records, sum(dose) as total_dose
                from SDTM.&ds3 group by usubjid;
            quit;
            proc sql;
                create table ADAM.adae_sum as
                select usubjid, count(*) as ae_count
                from SDTM.&ds2 group by usubjid;
            quit;
            proc sql;
                create table ADAM.adsl_final as
                select a.*, b.ae_count, c.total_dose
                from ADAM.adsl a
                left join ADAM.adae_sum b on a.usubjid = b.usubjid
                left join ADAM.ex_sum c on a.usubjid = c.usubjid;
            quit;
        %mend build_pipeline;

        %build_pipeline();
        """
        engine = SemanticConversionEngine(dialect="Modern R (tidyverse)")
        res = engine.convert_program(COMPLEX_SAS, program_name="Clinical_Benchmark")

        print("\n--- COMPLEX CLINICAL R CODE ---")
        print(repr(res.optimized_r_code))
        self.assertTrue(len(res.optimized_r_code) > 0)
        self.assertNotIn("ADSL <- %>%", res.optimized_r_code)
        self.assertNotIn("df <- ADSL", res.optimized_r_code)


if __name__ == "__main__":
    unittest.main()
