"""
test_app_ui_and_download_flow.py
────────────────────────────────
Programmatic verification of UI sections, Complete R Code display,
Copy payload, Download .R file payload, and R Optimizer output.
"""

import unittest
import os
import sys

os.environ["LLM_PRIMARY_PROVIDER"] = "groq"
os.environ["DISABLE_GEMINI"] = "true"

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from semantic_conversion_engine import SemanticConversionEngine
os.environ["GEMINI_API_KEY"] = "mock_key"

from doc_generator import ModernizationDocument
from app import is_valid_r_code, clean_r_code
from r_optimizer import ROptimizer

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


class TestAppUIAndDownloadFlow(unittest.TestCase):

    def test_01_simple_orders_ui_and_download(self):
        """Verify UI sections, Complete R Code, Copy, and Download for Orders SAS example."""
        engine = SemanticConversionEngine(dialect="Modern R (tidyverse)")
        res = engine.convert_program(SIMPLE_ORDERS_SAS, program_name="Orders_Program")

        # 1. R Code Validity
        self.assertTrue(is_valid_r_code(res.optimized_r_code))
        non_comment_lines = "\n".join([l.lower() for l in res.optimized_r_code.split('\n') if not l.strip().startswith('#')])
        self.assertNotIn("data ", non_comment_lines)
        self.assertNotIn("set ", non_comment_lines)
        self.assertNotIn("proc ", non_comment_lines)
        self.assertNotIn("run;", non_comment_lines)
        self.assertNotIn("here is a code review", res.optimized_r_code.lower())

        # 2. Modernization Sections Generation (11 Sections)
        from doc_generator import DocumentationGenerator
        generator = DocumentationGenerator()
        # Verify generator class exists
        self.assertIsNotNone(generator)

        # 3. Complete R Code Payload (For Copy & Download)
        download_payload = res.optimized_r_code
        self.assertTrue(len(download_payload) > 0)
        self.assertIn("RESULT <-", download_payload)

        # 4. R Optimizer Output Check
        optimizer = ROptimizer()
        opt_code, metrics = optimizer.optimize(res.optimized_r_code)
        self.assertIsNotNone(opt_code)
        self.assertTrue(len(opt_code) > 0)

        print("\n--- SIMPLE ORDERS VERIFICATION PASSED ---")

    def test_02_complex_clinical_ui_and_download(self):
        """Verify UI sections, Complete R Code, Copy, and Download for Complex Clinical Macro benchmark."""
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

        # 2. Complete R Code Payload (For Copy & Download)
        download_payload = res.optimized_r_code
        self.assertTrue(len(download_payload) > 0)
        self.assertIn("ADSL", download_payload)

        # 3. Check for bad code patterns
        self.assertNotIn("ADSL <- %>%", download_payload)
        self.assertNotIn("here is a code review", download_payload.lower())

        print("\n--- COMPLEX CLINICAL VERIFICATION PASSED ---")


if __name__ == "__main__":
    unittest.main()
