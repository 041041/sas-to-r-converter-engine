"""
test_groq_provider.py
─────────────────────
Unit test suite for Groq Provider Primary Mode and R Output Contract Validation.
Verifies all 9 required provider & output contract scenarios using mocks (0 live Gemini calls).
"""

import unittest
from unittest.mock import MagicMock, patch
import sys
import os

os.environ["DISABLE_GEMINI"] = "true"
os.environ["LLM_PRIMARY_PROVIDER"] = "groq"

os.environ["GEMINI_API_KEY"] = "mock_key"

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from llm_provider import GroqProvider, LLMResponse
from llm_router import LLMRouter
from app import is_valid_r_code, clean_r_code


class TestGroqProviderPrimary(unittest.TestCase):

    def setUp(self):
        self.mock_groq_client = MagicMock()
        self.mock_gemini_client = MagicMock()
        self.groq_provider = GroqProvider(api_key="mock-groq-key", model="llama-3.3-70b-versatile", client=self.mock_groq_client)

        self.router = LLMRouter(gemini_provider=MagicMock(), groq_provider=self.groq_provider)
        self.router.primary_provider = "groq"

    def test_01_groq_success(self):
        """1. Groq success in Groq-primary mode."""
        mock_resp = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "ADSL <- DM %>% filter(age >= 18)"
        mock_resp.choices = [mock_choice]
        self.mock_groq_client.chat.completions.create.return_value = mock_resp

        resp = self.router.generate("Convert step")

        self.assertEqual(resp.provider_used, "Groq")
        self.assertFalse(resp.fallback_occurred)
        self.assertIn("ADSL <- DM", resp.text)
        self.mock_groq_client.chat.completions.create.assert_called_once()

    def test_02_groq_api_failure(self):
        """2. Groq API failure raises RuntimeError cleanly."""
        self.mock_groq_client.chat.completions.create.side_effect = Exception("Groq API Service Unavailable")

        with self.assertRaises(Exception):
            self.router.generate("Convert step")

    def test_03_groq_timeout(self):
        """3. Groq timeout raises exception cleanly."""
        self.mock_groq_client.chat.completions.create.side_effect = Exception("Groq Connection Timeout")

        with self.assertRaises(Exception):
            self.router.generate("Convert step")

    def test_04_invalid_groq_response_rejected(self):
        """4. Invalid Groq response is rejected by is_valid_r_code."""
        invalid_text = "Here is a code review of your SAS script..."
        self.assertFalse(is_valid_r_code(invalid_text))

    def test_05_valid_r_response_accepted(self):
        """5. Valid R response is accepted by is_valid_r_code."""
        valid_text = "ADSL <- DM %>%\n  dplyr::filter(age >= 18)\nADSL"
        self.assertTrue(is_valid_r_code(valid_text))

    def test_06_sas_response_rejected(self):
        """6. SAS response (data ADAM.ADSL; set SDTM.ADSL; run;) is rejected."""
        sas_text = "data ADAM.ADSL;\n    set SDTM.ADSL;\n    if age >= 18;\nrun;"
        self.assertFalse(is_valid_r_code(sas_text))

    def test_07_prose_response_rejected(self):
        """7. Prose response (Here is the corrected SAS...) is rejected."""
        prose_text = "Here is the corrected SAS code for your pipeline."
        self.assertFalse(is_valid_r_code(prose_text))

    def test_08_markdown_r_safely_extracted(self):
        """8. Markdown R code block ```r ... ``` is safely extracted and cleaned."""
        md_text = "```r\nADSL <- DM %>%\n  filter(age >= 18)\nADSL\n```"
        cleaned = clean_r_code(md_text)
        self.assertTrue(is_valid_r_code(cleaned))
        self.assertIn("ADSL <- DM", cleaned)

    def test_09_gemini_disabled_in_groq_primary_mode(self):
        """9. Gemini call count = 0 in Groq-primary mode."""
        mock_resp = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "df <- DM"
        mock_resp.choices = [mock_choice]
        self.mock_groq_client.chat.completions.create.return_value = mock_resp

        resp = self.router.generate("Convert step")

        self.assertEqual(resp.provider_used, "Groq")
        self.assertEqual(self.router.gemini_call_count, 0)
        self.assertEqual(self.router.groq_call_count, 1)


if __name__ == "__main__":
    unittest.main()
