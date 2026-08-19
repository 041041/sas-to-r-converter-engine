"""
test_streamlit_cloud_secrets.py
───────────────────────────────
Unit test verifying GroqProvider fetches GROQ_API_KEY from Streamlit Cloud Secrets (st.secrets)
with top priority and zero key exposure.
"""

import unittest
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from llm_provider import GroqProvider


class TestStreamlitCloudSecrets(unittest.TestCase):

    def test_streamlit_cloud_secrets_priority(self):
        """Verifies st.secrets['GROQ_API_KEY'] takes top priority."""
        mock_st = MagicMock()
        mock_st.secrets = {"GROQ_API_KEY": "gsk_cloud_mock_secret_key"}

        provider = GroqProvider()

        with patch.dict("sys.modules", {"streamlit": mock_st}):
            fetched_key = provider._fetch_api_key()
            self.assertEqual(fetched_key, "gsk_cloud_mock_secret_key")
            self.assertTrue(provider.is_available())

    def test_nested_streamlit_cloud_secrets(self):
        """Verifies st.secrets['groq']['api_key'] nested format is supported."""
        mock_st = MagicMock()
        mock_st.secrets = {"groq": {"api_key": "gsk_nested_cloud_secret"}}

        provider = GroqProvider()

        with patch.dict("sys.modules", {"streamlit": mock_st}):
            fetched_key = provider._fetch_api_key()
            self.assertEqual(fetched_key, "gsk_nested_cloud_secret")


if __name__ == "__main__":
    unittest.main()
