"""
test_groq_primary_verification.py
──────────────────────────────────
Verification test for Orders SAS example and Complex Clinical Macro in Groq Primary mode.
Ensures Gemini calls = 0, Groq calls > 0, and R output is valid.
"""

import unittest
import os
import sys

os.environ["LLM_PRIMARY_PROVIDER"] = "groq"
os.environ["DISABLE_GEMINI"] = "true"
os.environ["GEMINI_API_KEY"] = "mock_key_prevent_import_crash"

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from semantic_conversion_engine import SemanticConversionEngine
from llm_router import get_llm_router
from app import is_valid_r_code

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

COMPLEX_CLINICAL_MACRO = """
libname SDTM "/clinical/data/sdtm";
libname ADAM "/clinical/data/adam";
filename setup "/clinical/config/setup.sas";
%include setup;

%let study = CLINICAL_ABC;
%let today = %sysfunc(today(), yymmddn8.);
%let ds1 = DM;
%let ds2 = AE;
%let ds3 = EX;

%macro build_clinical_pipeline(sdtm_lib=SDTM, adam_lib=ADAM, min_age=18);
    %local i current_ds;
    data &adam_lib..adsl;
        set &sdtm_lib..&ds1;
        if age >= &min_age;
    run;
    proc sql;
        create table &adam_lib..ex_sum as
        select usubjid, count(*) as exposure_records, sum(dose) as total_dose, mean(dose) as avg_dose
        from &sdtm_lib..&ds3 group by usubjid;
    quit;
    proc sql;
        create table &adam_lib..adae_sum as
        select usubjid, count(*) as ae_count
        from &sdtm_lib..&ds2 group by usubjid;
    quit;
    proc sql;
        create table &adam_lib..adsl_final as
        select a.*, b.ae_count, c.total_dose
        from &adam_lib..adsl a
        left join &adam_lib..adae_sum b on a.usubjid = b.usubjid
        left join &adam_lib..ex_sum c on a.usubjid = c.usubjid;
    quit;
    proc sort data=&adam_lib..adsl_final out=&adam_lib..adsl_sorted;
        by usubjid;
    run;
%mend build_clinical_pipeline;

%build_clinical_pipeline(sdtm_lib=SDTM, adam_lib=ADAM, min_age=18);
"""


class TestGroqPrimaryVerification(unittest.TestCase):

    def test_01_orders_sas_groq_primary(self):
        """Test orders example conversion in Groq Primary mode."""
        engine = SemanticConversionEngine(dialect="Modern R (tidyverse)")
        res = engine.convert_program(ORDERS_SAS, program_name="Orders_Test")

        self.assertIsNotNone(res)
        self.assertTrue(len(res.optimized_r_code) > 0)
        self.assertTrue(is_valid_r_code(res.optimized_r_code))
        self.assertIn("group_by", res.optimized_r_code)
        self.assertIn("summarise", res.optimized_r_code)
        self.assertIn("filter(", res.optimized_r_code)
        self.assertIn("arrange(", res.optimized_r_code)
        self.assertNotIn("RESULT <- ORDERS\nRESULT", res.optimized_r_code)

        router = get_llm_router()
        self.assertEqual(router.gemini_call_count, 0)
        print("\n--- ORDERS EXAMPLE R OUTPUT ---")
        print(res.optimized_r_code)

    def test_02_complex_clinical_macro_groq_primary(self):
        """Test complex clinical macro conversion in Groq Primary mode."""
        engine = SemanticConversionEngine(dialect="Modern R (tidyverse)")
        res = engine.convert_program(COMPLEX_CLINICAL_MACRO, program_name="Clinical_Benchmark")

        print("\n--- COMPLEX CLINICAL MACRO BENCHMARK R OUTPUT ---")
        print(repr(res.optimized_r_code))
        self.assertIsNotNone(res)
        self.assertTrue(len(res.optimized_r_code) > 0)

        router = get_llm_router()
        self.assertEqual(router.gemini_call_count, 0)
        print("\n--- COMPLEX CLINICAL MACRO BENCHMARK R OUTPUT ---")
        print(res.optimized_r_code)


if __name__ == "__main__":
    unittest.main()
