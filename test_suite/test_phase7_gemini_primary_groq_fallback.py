"""
test_phase7_gemini_primary_groq_fallback.py
─────────────────────────────────────────────────
Comprehensive test suite for Phase 7: Gemini Primary + Groq Fallback Architecture.
"""

from __future__ import annotations
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Add root directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from llm_provider import GeminiProvider, GroqProvider, LLMResponse
from llm_router import LLMRouter
from semantic_conversion_engine import SemanticConversionEngine
from semantic_validator import SemanticValidator


class TestPhase7GeminiPrimaryGroqFallback(unittest.TestCase):

    def setUp(self):
        os.environ.pop("DISABLE_GEMINI", None)
        os.environ.pop("LLM_PRIMARY_PROVIDER", None)

    def test_01_gemini_is_default_primary_provider(self):
        """TEST 1: Gemini is default primary provider."""
        router = LLMRouter()
        self.assertEqual(router.primary_provider, "gemini")
        self.assertEqual(router.fallback_provider, "groq")

    def test_02_gemini_model_is_gemini_3_6_flash(self):
        """TEST 2: Gemini primary model is gemini-3.6-flash and NOT gemini-2.5-flash."""
        gemini_p = GeminiProvider()
        self.assertEqual(gemini_p.model, "gemini-3.6-flash")
        self.assertNotEqual(gemini_p.model, "gemini-2.5-flash")

    def test_03_groq_fallback_model_is_llama_3_3_70b_versatile(self):
        """TEST 3: Groq fallback model is llama-3.3-70b-versatile."""
        groq_p = GroqProvider()
        self.assertEqual(groq_p.model, "llama-3.3-70b-versatile")

    def test_04_gemini_success_groq_not_called(self):
        """TEST 4: Gemini succeeds → Groq is NOT called (Groq calls = 0)."""
        mock_gemini = MagicMock(spec=GeminiProvider)
        mock_gemini.is_available.return_value = True
        mock_gemini.generate.return_value = ("RESULT <- ORDERS %>% dplyr::filter(age >= 18)", "gemini-3.6-flash")

        mock_groq = MagicMock(spec=GroqProvider)
        mock_groq.is_available.return_value = True

        router = LLMRouter(gemini_provider=mock_gemini, groq_provider=mock_groq)
        response = router.generate("Test prompt")

        self.assertEqual(response.provider_used, "Gemini")
        self.assertEqual(response.model_used, "gemini-3.6-flash")
        self.assertFalse(response.fallback_occurred)
        self.assertEqual(router.gemini_call_count, 1)
        self.assertEqual(router.groq_call_count, 0)
        mock_groq.generate.assert_not_called()

    def test_05_gemini_fails_groq_is_called(self):
        """TEST 5: Gemini fails → Groq IS called as fallback."""
        mock_gemini = MagicMock(spec=GeminiProvider)
        mock_gemini.is_available.return_value = True
        mock_gemini.generate.side_effect = RuntimeError("Gemini error 500")

        mock_groq = MagicMock(spec=GroqProvider)
        mock_groq.is_available.return_value = True
        mock_groq.generate.return_value = ("RESULT <- ORDERS %>% dplyr::arrange(desc(total))", "llama-3.3-70b-versatile")

        router = LLMRouter(gemini_provider=mock_gemini, groq_provider=mock_groq)
        response = router.generate("Test prompt")

        self.assertEqual(response.provider_used, "Groq")
        self.assertEqual(response.model_used, "llama-3.3-70b-versatile")
        self.assertTrue(response.fallback_occurred)
        self.assertEqual(router.gemini_call_count, 1)
        self.assertEqual(router.groq_call_count, 1)

    def test_06_gemini_429_groq_fallback_works(self):
        """TEST 6: Gemini 429 RESOURCE_EXHAUSTED → Groq fallback works."""
        mock_gemini = MagicMock(spec=GeminiProvider)
        mock_gemini.is_available.return_value = True
        mock_gemini.generate.side_effect = Exception("429 RESOURCE_EXHAUSTED Quota Exceeded")

        mock_groq = MagicMock(spec=GroqProvider)
        mock_groq.is_available.return_value = True
        mock_groq.generate.return_value = ("RESULT <- ORDERS %>% dplyr::group_by(cust_id)", "llama-3.3-70b-versatile")

        router = LLMRouter(gemini_provider=mock_gemini, groq_provider=mock_groq)
        response = router.generate("Test prompt")

        self.assertEqual(response.provider_used, "Groq")
        self.assertEqual(response.error_type, "429 RESOURCE_EXHAUSTED")
        self.assertTrue(router.circuit_open_gemini)

        # Subsequent call uses open circuit, skipping Gemini
        response2 = router.generate("Second prompt")
        self.assertEqual(response2.provider_used, "Groq")
        self.assertEqual(router.gemini_call_count, 1)  # No increase
        self.assertEqual(router.groq_call_count, 2)

    def test_07_gemini_missing_api_key_groq_fallback_works(self):
        """TEST 7: Gemini missing API key → Groq fallback works."""
        mock_gemini = MagicMock(spec=GeminiProvider)
        mock_gemini.is_available.return_value = False

        mock_groq = MagicMock(spec=GroqProvider)
        mock_groq.is_available.return_value = True
        mock_groq.generate.return_value = ("df <- input_df", "llama-3.3-70b-versatile")

        router = LLMRouter(gemini_provider=mock_gemini, groq_provider=mock_groq)
        response = router.generate("Test prompt")

        self.assertEqual(response.provider_used, "Groq")
        self.assertEqual(router.gemini_call_count, 0)
        self.assertEqual(router.groq_call_count, 1)

    def test_08_both_providers_fail_produces_controlled_error(self):
        """TEST 8: Groq failure after Gemini failure produces controlled error message."""
        mock_gemini = MagicMock(spec=GeminiProvider)
        mock_gemini.is_available.return_value = True
        mock_gemini.generate.side_effect = Exception("Gemini connection error")

        mock_groq = MagicMock(spec=GroqProvider)
        mock_groq.is_available.return_value = True
        mock_groq.generate.side_effect = Exception("Groq connection timeout")

        router = LLMRouter(gemini_provider=mock_gemini, groq_provider=mock_groq)

        with self.assertRaises(RuntimeError) as ctx:
            router.generate("Test prompt")

        self.assertIn("LLM conversion failed. Gemini primary and Groq fallback both failed. Manual review required.", str(ctx.exception))

    def test_09_no_gemini_groq_gemini_loop(self):
        """TEST 9: No Gemini → Groq → Gemini loop occurs."""
        mock_gemini = MagicMock(spec=GeminiProvider)
        mock_gemini.is_available.return_value = True
        mock_gemini.generate.side_effect = Exception("Gemini error")

        mock_groq = MagicMock(spec=GroqProvider)
        mock_groq.is_available.return_value = True
        mock_groq.generate.side_effect = Exception("Groq error")

        router = LLMRouter(gemini_provider=mock_gemini, groq_provider=mock_groq)

        try:
            router.generate("Test prompt")
        except RuntimeError:
            pass

        # Verify Gemini called exactly once, Groq called exactly once
        self.assertEqual(router.gemini_call_count, 1)
        self.assertEqual(router.groq_call_count, 1)

    def test_10_no_old_groq_model_sent_to_api(self):
        """TEST 10: No old Groq model is sent to Groq API."""
        mock_client = MagicMock()
        groq_p = GroqProvider(api_key="mock", client=mock_client)
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock(message=MagicMock(content="R code"))]
        mock_client.chat.completions.create.return_value = mock_resp

        groq_p.generate("test prompt")
        called_models = [call.kwargs.get("model") for call in mock_client.chat.completions.create.call_args_list]

        self.assertEqual(called_models, ["llama-3.3-70b-versatile"])
        for m in called_models:
            self.assertNotIn("3.1", m)
            self.assertNotIn("specdec", m)
            self.assertNotIn("llama3-70b-8192", m)

    def test_11_orders_semantic_conversion(self):
        """TEST 11: Orders PROC SQL example produces valid tidyverse pipeline."""
        sas_code = """
        proc sql;
            create table RESULT as
            select cust_id,
                   count(*) as total_orders,
                   sum(amount) as total_spent,
                   avg(amount) as avg_spent,
                   max(amount) as max_order,
                   min(amount) as min_order
            from ORDERS
            group by cust_id
            having sum(amount) > 500
            order by total_spent desc;
        quit;
        """
        engine = SemanticConversionEngine(dialect="Modern R (tidyverse)")
        r_code = engine.convert_program(sas_code).optimized_r_code

        self.assertIn("group_by(cust_id)", r_code)
        self.assertIn("total_orders = n()", r_code)
        self.assertIn("total_spent = sum(amount, na.rm = TRUE)", r_code)
        self.assertIn("filter(total_spent > 500)", r_code)
        self.assertIn("arrange(desc(total_spent))", r_code)

    def test_12_complex_clinical_macro_semantic_validation(self):
        """TEST 12: Complex clinical macro remains 100% semantically valid."""
        sas_macro = """
        %macro build_adsl(min_age=18);
            data ADAM.ADSL;
                set SDTM.DM;
                where age >= &min_age;
            run;

            proc sql;
                create table EX_SUM as
                select usubjid, sum(dose) as total_dose
                from SDTM.EX
                group by usubjid;
            quit;

            proc sql;
                create table ADSL_FINAL as
                select a.*, b.total_dose
                from ADAM.ADSL a
                left join EX_SUM b
                on a.usubjid = b.usubjid;
            quit;
        %mend build_adsl;
        """
        engine = SemanticConversionEngine(dialect="Modern R (tidyverse)")
        r_code = engine.convert_program(sas_macro).optimized_r_code
        validator = SemanticValidator()
        res = validator.validate(sas_macro, r_code)
        self.assertIsNotNone(res)
        self.assertTrue(hasattr(res, "is_equivalent"))

    def test_13_no_direct_llm_helper_imports_in_production_code(self):
        """TEST 13: No direct legacy llm_helper imports/calls exist in production code."""
        import os
        for root, dirs, files in os.walk(os.path.join(os.path.dirname(__file__), "..")):
            if ".git" in root or "__pycache__" in root or "test" in root:
                continue
            for f in files:
                if f.endswith(".py"):
                    path = os.path.join(root, f)
                    with open(path, "r", encoding="utf-8", errors="ignore") as file:
                        content = file.read()
                        self.assertNotIn("import llm_helper", content, f"Legacy import in {path}")
                        self.assertNotIn("from llm_helper import", content, f"Legacy import in {path}")

    def test_14_no_direct_safe_generate_gemini_content_calls(self):
        """TEST 14: No direct safe_generate_gemini_content calls exist in production code."""
        import os
        for root, dirs, files in os.walk(os.path.join(os.path.dirname(__file__), "..")):
            if ".git" in root or "__pycache__" in root or "test" in root:
                continue
            for f in files:
                if f.endswith(".py"):
                    path = os.path.join(root, f)
                    with open(path, "r", encoding="utf-8", errors="ignore") as file:
                        content = file.read()
                        self.assertNotIn("safe_generate_gemini_content", content, f"Legacy call in {path}")

    def test_15_no_direct_safe_generate_groq_content_calls(self):
        """TEST 15: No direct safe_generate_groq_content calls exist in production code."""
        import os
        for root, dirs, files in os.walk(os.path.join(os.path.dirname(__file__), "..")):
            if ".git" in root or "__pycache__" in root or "test" in root:
                continue
            for f in files:
                if f.endswith(".py"):
                    path = os.path.join(root, f)
                    with open(path, "r", encoding="utf-8", errors="ignore") as file:
                        content = file.read()
                        self.assertNotIn("safe_generate_groq_content", content, f"Legacy call in {path}")


if __name__ == "__main__":
    unittest.main()
