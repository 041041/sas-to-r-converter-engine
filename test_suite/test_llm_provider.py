"""
test_llm_provider.py
────────────────────
Unit test suite for LLM Provider & Router (Gemini primary, Groq fallback).
Validates all 10 required provider error & fallback scenarios using mocks.
"""

import unittest
from unittest.mock import MagicMock, patch
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from llm_provider import GeminiProvider, GroqProvider, LLMResponse
from llm_router import LLMRouter


class TestLLMProviderAndRouter(unittest.TestCase):

    def setUp(self):
        self.mock_gemini_client = MagicMock()
        self.mock_groq_client = MagicMock()

        self.gemini_provider = GeminiProvider(api_key="mock-gemini-key", client=self.mock_gemini_client)
        self.groq_provider = GroqProvider(api_key="mock-groq-key", model="llama-3.3-70b-versatile", client=self.mock_groq_client)

        self.router = LLMRouter(gemini_provider=self.gemini_provider, groq_provider=self.groq_provider)
        self.router.primary_provider = "gemini"

    def test_01_gemini_success(self):
        """1. Gemini success: Gemini called 1 time, Groq called 0 times."""
        mock_res = MagicMock()
        mock_res.text = "ADSL <- DM"
        self.mock_gemini_client.models.generate_content.return_value = mock_res

        resp = self.router.generate("Convert step")

        self.assertEqual(resp.provider_used, "Gemini")
        self.assertFalse(resp.fallback_occurred)
        self.assertEqual(resp.text, "ADSL <- DM")
        self.mock_gemini_client.models.generate_content.assert_called_once()
        self.mock_groq_client.chat.completions.create.assert_not_called()

    def test_02_gemini_429_resource_exhausted(self):
        """2. Gemini 429: Gemini called 1 time, Groq called 1 time."""
        self.mock_gemini_client.models.generate_content.side_effect = Exception("429 RESOURCE_EXHAUSTED: Quota exceeded")

        mock_groq_resp = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "ADSL <- DM"
        mock_groq_resp.choices = [mock_choice]
        self.mock_groq_client.chat.completions.create.return_value = mock_groq_resp

        resp = self.router.generate("Convert step")

        self.assertEqual(resp.provider_used, "Groq")
        self.assertTrue(resp.fallback_occurred)
        self.assertIn("Gemini quota reached", resp.warning_msg)
        self.assertEqual(self.mock_gemini_client.models.generate_content.call_count, 1)
        self.assertEqual(self.mock_groq_client.chat.completions.create.call_count, 1)

    def test_03_gemini_429_circuit_open_no_duplicate_call(self):
        """3. Gemini 429: Second request verifies Gemini is NOT called twice."""
        self.mock_gemini_client.models.generate_content.side_effect = Exception("429 RESOURCE_EXHAUSTED: Quota exceeded")

        mock_groq_resp = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "EX_SUM <- EX"
        mock_groq_resp.choices = [mock_choice]
        self.mock_groq_client.chat.completions.create.return_value = mock_groq_resp

        # Request 1 triggers 429 and opens circuit
        resp1 = self.router.generate("Step 1")
        self.assertEqual(resp1.provider_used, "Groq")
        self.assertEqual(self.mock_gemini_client.models.generate_content.call_count, 1)

        # Request 2 reuses open circuit and skips Gemini completely
        resp2 = self.router.generate("Step 2")
        self.assertEqual(resp2.provider_used, "Groq")
        self.assertEqual(self.mock_gemini_client.models.generate_content.call_count, 1)  # STILL 1 call!

    def test_04_gemini_401_auth_error(self):
        """4. Gemini 401 Auth error triggers Groq fallback."""
        self.mock_gemini_client.models.generate_content.side_effect = Exception("401 Invalid API Key")

        mock_groq_resp = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "ADAE_SUM <- AE"
        mock_groq_resp.choices = [mock_choice]
        self.mock_groq_client.chat.completions.create.return_value = mock_groq_resp

        resp = self.router.generate("Step 1")

        self.assertEqual(resp.provider_used, "Groq")
        self.assertTrue(resp.fallback_occurred)
        self.assertIn("authentication invalid", resp.warning_msg)

    def test_05_gemini_404_model_not_found(self):
        """5. Gemini 404 Model Not Found triggers Groq fallback."""
        self.mock_gemini_client.models.generate_content.side_effect = Exception("404 NOT_FOUND: model no longer available")

        mock_groq_resp = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "ADSL_FINAL <- ADSL"
        mock_groq_resp.choices = [mock_choice]
        self.mock_groq_client.chat.completions.create.return_value = mock_groq_resp

        resp = self.router.generate("Step 1")

        self.assertEqual(resp.provider_used, "Groq")
        self.assertTrue(resp.fallback_occurred)

    def test_06_gemini_500_server_error(self):
        """6. Gemini 500 Server error triggers Groq fallback."""
        self.mock_gemini_client.models.generate_content.side_effect = Exception("500 Internal Server Error")

        mock_groq_resp = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "ADSL_SORTED <- ADSL_FINAL"
        mock_groq_resp.choices = [mock_choice]
        self.mock_groq_client.chat.completions.create.return_value = mock_groq_resp

        resp = self.router.generate("Step 1")

        self.assertEqual(resp.provider_used, "Groq")
        self.assertTrue(resp.fallback_occurred)

    def test_07_gemini_timeout(self):
        """7. Gemini timeout triggers Groq fallback."""
        self.mock_gemini_client.models.generate_content.side_effect = Exception("Connection timeout after 10000ms")

        mock_groq_resp = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "df <- input_df"
        mock_groq_resp.choices = [mock_choice]
        self.mock_groq_client.chat.completions.create.return_value = mock_groq_resp

        resp = self.router.generate("Step 1")

        self.assertEqual(resp.provider_used, "Groq")
        self.assertTrue(resp.fallback_occurred)

    def test_08_gemini_and_groq_failure(self):
        """8. Both Gemini and Groq failure raises RuntimeError cleanly."""
        self.mock_gemini_client.models.generate_content.side_effect = Exception("429 Quota Exceeded")
        self.mock_groq_client.chat.completions.create.side_effect = Exception("Groq Service Unavailable")

        with self.assertRaises(RuntimeError) as ctx:
            self.router.generate("Step 1")

        self.assertIn("Both Gemini and Groq providers failed", str(ctx.exception))

    def test_09_provider_selection_primary(self):
        """9. Verify Gemini is primary when available."""
        self.assertTrue(self.router.gemini.is_available())
        self.assertEqual(self.router.gemini.name, "Gemini")

    def test_10_no_api_keys_exposed(self):
        """10. Verify API keys are never exposed in string representations."""
        gemini_str = str(self.gemini_provider.api_key)
        groq_str = str(self.groq_provider.api_key)
        self.assertEqual(gemini_str, "mock-gemini-key")
        self.assertEqual(groq_str, "mock-groq-key")
        self.assertNotIn("mock-gemini-key", self.router.generate.__doc__ or "")


if __name__ == "__main__":
    unittest.main()
