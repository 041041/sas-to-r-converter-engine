"""
test_diagnostic_trace.py
─────────────────────────
Diagnostic trace script reproducing and mapping the exact call stack,
LLM response flow, and acceptance point for SAS responses in app.py.
"""

import unittest
from unittest.mock import patch, MagicMock
import sys
import os

os.environ["GEMINI_API_KEY"] = "mock_key_for_diagnostic"

from app import clean_r_code, call_llm_api
from llm_router import get_llm_router

TEST_SAS_INPUT = """
data ADAM.ADSL;
    set SDTM.&;
    if age >= 18;
    if SAFFL = "Y";

    if sex = "M" then SEXN = 1;
    else if sex = "F" then SEXN = 2;
    else SEXN = .;

    length STUDY $20;
    STUDY = "STUDY001";
run;
"""

RAW_GROQ_SAS_REVIEW_RESPONSE = """Here is the corrected code with explanations...

The macro reference `&` in `set SDTM.&;` is incomplete. Here is the corrected code:

```sas
data ADAM.ADSL;
    set SDTM.ADSL;
    if age >= 18;
    if SAFFL = "Y";

    if sex = "M" then SEXN = 1;
    else if sex = "F" then SEXN = 2;
    else SEXN = .;

    length STUDY $20;
    STUDY = "STUDY001";
run;
```
"""


class TestDiagnosticTrace(unittest.TestCase):

    def test_trace_sas_acceptance_in_clean_r_code(self):
        """Traces how clean_r_code accepts SAS review text as R code."""
        cleaned = clean_r_code(RAW_GROQ_SAS_REVIEW_RESPONSE)

        print("\n--- RAW GROQ LLM RESPONSE ---")
        print(RAW_GROQ_SAS_REVIEW_RESPONSE)
        print("--- CLEANED OUTPUT PRODUCED BY clean_r_code ---")
        print(cleaned)

        # Assert that clean_r_code produced SAS code
        self.assertIn("data ADAM.ADSL;", cleaned)
        self.assertIn("if sex = \"M\" then SEXN = 1;", cleaned)


if __name__ == "__main__":
    unittest.main()
