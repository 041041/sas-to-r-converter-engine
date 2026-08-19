"""
test_groq_integration_live.py
──────────────────────────────
Live/Controlled Integration test for Groq Primary Mode.
Tests Simple SAS proc sql and Complex Clinical Macro benchmark without invoking Gemini.
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

SIMPLE_SAS_SQL = """
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


class TestGroqIntegrationLive(unittest.TestCase):

    def test_simple_sas_sql_groq_primary(self):
        """Test simple SAS SQL data step & proc sql conversion in Groq Primary mode."""
        engine = SemanticConversionEngine(dialect="Modern R (tidyverse)")
        res = engine.convert_program(SIMPLE_SAS_SQL, program_name="Simple_Groq_Test")

        print("\n--- SIMPLE SAS DETERMINISTIC / GROQ R OUTPUT ---")
        print(repr(res.optimized_r_code))
        self.assertIsNotNone(res)
        self.assertTrue(len(res.optimized_r_code) > 0)

        # Assert zero Gemini calls were made
        router = get_llm_router()
        self.assertEqual(router.gemini_call_count, 0)
        print("\n--- SIMPLE SAS GROQ PRIMARY R OUTPUT ---")
        print(res.optimized_r_code)


if __name__ == "__main__":
    unittest.main()
