"""
test_disable_gemini_guard.py
────────────────────────────
Unit test verifying that setting DISABLE_GEMINI=true prevents any network call to Gemini,
raises GeminiDisabledForDevelopment internally, and routes cleanly to Groq without HTTP 429 errors.
"""

import unittest
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from llm_provider import GeminiProvider, GroqProvider, GeminiDisabledForDevelopment
from llm_router import LLMRouter


class TestDisableGeminiGuard(unittest.TestCase):

    def test_disable_gemini_guard_prevents_network_call(self):
        """Verifies DISABLE_GEMINI=true blocks Gemini SDK calls and triggers Groq fallback."""
        mock_gemini_client = MagicMock()
        mock_groq_client = MagicMock()

        mock_groq_choice = MagicMock()
        mock_groq_choice.message.content = "ADSL <- DM"
        mock_groq_resp = MagicMock(choices=[mock_groq_choice])
        mock_groq_client.chat.completions.create.return_value = mock_groq_resp

        gemini_p = GeminiProvider(api_key="mock-key", client=mock_gemini_client)
        groq_p = GroqProvider(api_key="mock-key", client=mock_groq_client)
        router = LLMRouter(gemini_provider=gemini_p, groq_provider=groq_p)
        router.primary_provider = "gemini"

        with patch.dict(os.environ, {"DISABLE_GEMINI": "true"}):
            resp = router.generate("TASK: Convert SAS step")

            self.assertEqual(resp.provider_used, "Groq")
            self.assertFalse(resp.fallback_occurred)

            # CRITICAL VERIFICATION: Gemini SDK client models.generate_content WAS NEVER CALLED!
            mock_gemini_client.models.generate_content.assert_not_called()
            mock_groq_client.chat.completions.create.assert_called_once()

    def test_direct_gemini_provider_raises_disabled_error(self):
        """Verifies GeminiProvider.generate() raises GeminiDisabledError directly."""
        mock_client = MagicMock()
        p = GeminiProvider(api_key="mock-key", client=mock_client)
        from llm_provider import GeminiDisabledError
        with patch.dict(os.environ, {"DISABLE_GEMINI": "true"}):
            with self.assertRaises(GeminiDisabledError):
                p.generate("Test prompt")
            mock_client.models.generate_content.assert_not_called()


if __name__ == "__main__":
    unittest.main()
