"""
test_offline_fallback_simulation.py
───────────────────────────────────
Integration simulation testing Gemini 429 quota exhaustion -> Groq fallback execution.
Verifies complete R code pipeline runs seamlessly without throwing raw 429 exceptions to UI.
"""

import unittest
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from llm_provider import GeminiProvider, GroqProvider
from llm_router import LLMRouter
from semantic_conversion_engine import SemanticConversionEngine

TEST_SAS_PROGRAM = """
data adsl;
    set sdtm.dm;
    if age >= 18;
run;
"""


class TestOfflineFallbackSimulation(unittest.TestCase):

    def test_simulated_gemini_429_to_groq_fallback_pipeline(self):
        """Simulate Gemini 429 quota exhaustion and verify Groq handles generation."""
        mock_gemini_client = MagicMock()
        mock_groq_client = MagicMock()

        mock_gemini_client.models.generate_content.side_effect = Exception("429 RESOURCE_EXHAUSTED: Quota exceeded")

        mock_groq_choice = MagicMock()
        mock_groq_choice.message.content = "ADSL <- DM %>%\n  dplyr::filter(age >= 18)\nADSL"
        mock_groq_resp = MagicMock(choices=[mock_groq_choice])
        mock_groq_client.chat.completions.create.return_value = mock_groq_resp

        gemini_p = GeminiProvider(api_key="mock-key", client=mock_gemini_client)
        groq_p = GroqProvider(api_key="mock-key", client=mock_groq_client)
        router = LLMRouter(gemini_provider=gemini_p, groq_provider=groq_p)

        # 1. Execute LLM Router call
        response = router.generate("TASK: Convert SAS step")

        # 2. Verify router output
        self.assertEqual(response.provider_used, "Groq")
        self.assertTrue(response.fallback_occurred)
        self.assertIn("Gemini quota reached", response.warning_msg)
        self.assertIn("ADSL <- DM", response.text)

        # 3. Verify Gemini was called ONCE, Groq was called ONCE
        mock_gemini_client.models.generate_content.assert_called_once()
        mock_groq_client.chat.completions.create.assert_called_once()

        # 4. Execute a second call: Verify Gemini circuit is open (0 further Gemini calls)
        response2 = router.generate("TASK: Convert step 2")
        self.assertEqual(response2.provider_used, "Groq")
        self.assertEqual(mock_gemini_client.models.generate_content.call_count, 1)  # Still 1 call!
        self.assertEqual(mock_groq_client.chat.completions.create.call_count, 2)


if __name__ == "__main__":
    unittest.main()
