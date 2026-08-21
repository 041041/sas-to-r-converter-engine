import unittest
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath("."))

from app import ConversionFailedError, is_valid_r_code, validate_r_syntax, call_llm_api
from semantic_validator import validate_semantic_completeness


class TestFailedConversionUX(unittest.TestCase):

    def test_conversion_failed_error_attributes(self):
        err = ConversionFailedError(
            "Semantic completeness failed",
            candidate_code="ADSL <- DM",
            contract_pass=True,
            syntax_pass=True,
            semantic_pass=False,
            missing_cols=["AGE_MONTHS"],
            gemini_failed=True,
            groq_failed=True
        )
        self.assertEqual(err.candidate_code, "ADSL <- DM")
        self.assertTrue(err.contract_pass)
        self.assertTrue(err.syntax_pass)
        self.assertFalse(err.semantic_pass)
        self.assertEqual(err.missing_cols, ["AGE_MONTHS"])
        self.assertTrue(err.gemini_failed)
        self.assertTrue(err.groq_failed)

    def test_candidate_code_preserves_strict_validation(self):
        invalid_r = "data ADSL; set DM; run;"
        self.assertFalse(is_valid_r_code(invalid_r))
        self.assertFalse(validate_r_syntax(invalid_r))

    def test_semantic_validation_rejects_incomplete_candidate(self):
        sas_code = "data ADSL; set DM; AGE_MONTHS = AGE * 12; run;"
        incomplete_r = "ADSL <- DM"
        is_comp, exp_c, pres_c, miss_c = validate_semantic_completeness(sas_code, incomplete_r)
        self.assertFalse(is_comp)
        self.assertIn("AGE_MONTHS", miss_c)

    @patch("app.get_llm_router")
    def test_rule_engine_candidate_preserved_on_llm_failure(self, mock_get_router):
        mock_router = MagicMock()
        mock_router.generate.side_effect = RuntimeError("LLM conversion failed. Gemini primary and Groq fallback both failed.")
        mock_get_router.return_value = mock_router

        sas_step = "data ADSL; set DM; AGE_MONTHS = AGE * 12; run;"
        initial_rule_candidate = "ADSL <- DM"

        with self.assertRaises(ConversionFailedError) as ctx:
            call_llm_api(sas_step, [], ["DM"], "Modern R (tidyverse)", initial_candidate=initial_rule_candidate)

        err = ctx.exception
        self.assertEqual(err.candidate_code, initial_rule_candidate)
        self.assertTrue(err.contract_pass)
        self.assertTrue(err.syntax_pass)
        self.assertFalse(err.semantic_pass)
        self.assertIn("AGE_MONTHS", err.missing_cols)
        self.assertTrue(err.gemini_failed)
        self.assertTrue(err.groq_failed)

    @patch("app.get_llm_router")
    def test_no_candidate_preserved_when_no_initial_or_llm_output(self, mock_get_router):
        mock_router = MagicMock()
        mock_router.generate.side_effect = RuntimeError("LLM network timeout")
        mock_get_router.return_value = mock_router

        sas_step = "data ADSL; set DM; run;"
        with self.assertRaises(ConversionFailedError) as ctx:
            call_llm_api(sas_step, [], ["DM"], "Modern R (tidyverse)", initial_candidate=None)

        err = ctx.exception
        self.assertIsNone(err.candidate_code)

    @patch("app.get_llm_router")
    def test_llm_successful_path_replaces_initial_candidate(self, mock_get_router):
        mock_router = MagicMock()
        mock_resp = MagicMock()
        mock_resp.fallback_occurred = False
        mock_resp.text = "ADSL <- DM %>%\n  dplyr::mutate(AGE_MONTHS = AGE * 12)\nADSL"
        mock_router.generate.return_value = mock_resp
        mock_get_router.return_value = mock_router

        sas_step = "data ADSL; set DM; AGE_MONTHS = AGE * 12; run;"
        res = call_llm_api(sas_step, ["AGE"], ["DM"], "Modern R (tidyverse)", initial_candidate="ADSL <- DM")
        self.assertIn("AGE_MONTHS = AGE * 12", res)


if __name__ == "__main__":
    unittest.main()
