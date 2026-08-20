"""
llm_provider.py
───────────────
Centralized LLM Provider abstraction layer for Enterprise SAS Modernization Engine.
Provides GeminiProvider and GroqProvider with explicit error classification.
"""

from __future__ import annotations
import os
import logging
from dataclasses import dataclass
from typing import Optional, Any

logger = logging.getLogger("LLMProvider")


@dataclass
class LLMResponse:
    """Standardized response container across all LLM providers."""
    text: str
    provider_used: str  # "Gemini" | "Groq" | "Deterministic"
    model_used: str
    fallback_occurred: bool = False
    warning_msg: Optional[str] = None
    error_type: Optional[str] = None


class BaseLLMProvider:
    """Abstract base provider class."""
    name: str = "Base"

    def is_available(self) -> bool:
        raise NotImplementedError

    def generate(self, prompt: str) -> tuple[str, str]:
        raise NotImplementedError


class GeminiDisabledForDevelopment(RuntimeError):
    """Exception raised when Gemini API calls are explicitly disabled for development."""
    pass

GeminiDisabledError = GeminiDisabledForDevelopment


class GeminiProvider(BaseLLMProvider):
    """Primary LLM Provider wrapping Google Gemini API."""
    name: str = "Gemini"

    def __init__(self, api_key: Optional[str] = None, client: Optional[Any] = None):
        self.api_key = api_key
        self.client = client
        self.model = "gemini-2.5-flash"

    def _fetch_api_key(self) -> Optional[str]:
        if self.api_key:
            return self.api_key
        # Priority 1: Streamlit Cloud Secrets
        try:
            import streamlit as st
            if hasattr(st, "secrets"):
                if "GEMINI_API_KEY" in st.secrets and st.secrets["GEMINI_API_KEY"]:
                    return str(st.secrets["GEMINI_API_KEY"]).strip()
                if "gemini" in st.secrets and isinstance(st.secrets["gemini"], dict) and "api_key" in st.secrets["gemini"]:
                    return str(st.secrets["gemini"]["api_key"]).strip()
        except Exception:
            pass

        # Priority 2: Environment variable
        key = os.environ.get("GEMINI_API_KEY")
        if key and key.strip():
            return key.strip()

        # Priority 3: Local file .streamlit/secrets.toml
        try:
            toml_path = os.path.join(os.path.dirname(__file__), ".streamlit", "secrets.toml")
            if os.path.exists(toml_path):
                with open(toml_path) as f:
                    for line in f:
                        line_s = line.strip()
                        if line_s.startswith("GEMINI_API_KEY"):
                            parts = line_s.split("=", 1)
                            if len(parts) == 2:
                                val = parts[1].strip().strip('"').strip("'")
                                if val:
                                    return val
        except Exception:
            pass

        return None

    def _get_client(self) -> Any:
        if os.environ.get("DISABLE_GEMINI", "false").lower() in ("true", "1", "yes"):
            return None
        if self.client:
            return self.client
        api_key = self._fetch_api_key()
        if not api_key:
            return None
        try:
            from google import genai
            self.client = genai.Client(api_key=api_key)
            return self.client
        except Exception as e:
            logger.warning(f"[LLM] Failed to initialize Gemini client: {e}")
            return None

    def is_available(self) -> bool:
        if os.environ.get("DISABLE_GEMINI", "false").lower() in ("true", "1", "yes"):
            return False
        return bool(self._get_client() or self._fetch_api_key())

    def generate(self, prompt: str) -> tuple[str, str]:
        if os.environ.get("DISABLE_GEMINI", "false").lower() in ("true", "1", "yes"):
            raise GeminiDisabledError("Gemini is explicitly disabled via DISABLE_GEMINI environment variable.")

        client = self._get_client()
        if not client:
            raise RuntimeError("Gemini API key missing or client uninitialized.")

        try:
            res = client.models.generate_content(model=self.model, contents=prompt)
            if res and hasattr(res, "text") and res.text:
                return res.text.strip(), self.model
            elif res and hasattr(res, "content") and res.content:
                return str(res.content).strip(), self.model
            raise RuntimeError(f"Gemini returned empty response for model {self.model}.")
        except Exception as e:
            logger.warning(f"[LLM] Gemini generation failed with model {self.model}: {e}")
            raise e


class GroqProvider(BaseLLMProvider):
    """Secondary Fallback LLM Provider wrapping Groq API."""
    name: str = "Groq"

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, client: Optional[Any] = None):
        self.api_key = api_key
        raw_model = model or os.environ.get("GROQ_MODEL") or "llama-3.3-70b-versatile"
        if raw_model != "llama-3.3-70b-versatile":
            raw_model = "llama-3.3-70b-versatile"
        self.model = raw_model
        self.client = client

    def _fetch_api_key(self) -> Optional[str]:
        if self.api_key:
            return self.api_key
        # Priority 1: Streamlit Cloud Secrets
        try:
            import streamlit as st
            if hasattr(st, "secrets"):
                if "GROQ_API_KEY" in st.secrets and st.secrets["GROQ_API_KEY"]:
                    return str(st.secrets["GROQ_API_KEY"]).strip()
                # Also check nested secrets if configured as [groq] api_key
                if "groq" in st.secrets and isinstance(st.secrets["groq"], dict) and "api_key" in st.secrets["groq"]:
                    return str(st.secrets["groq"]["api_key"]).strip()
        except Exception:
            pass

        # Priority 2: Environment variable
        key = os.environ.get("GROQ_API_KEY")
        if key and key.strip():
            return key.strip()

        # Priority 3: Local file .streamlit/secrets.toml
        try:
            toml_path = os.path.join(os.path.dirname(__file__), ".streamlit", "secrets.toml")
            if os.path.exists(toml_path):
                with open(toml_path) as f:
                    for line in f:
                        line_s = line.strip()
                        if line_s.startswith("GROQ_API_KEY"):
                            parts = line_s.split("=", 1)
                            if len(parts) == 2:
                                val = parts[1].strip().strip('"').strip("'")
                                if val:
                                    return val
        except Exception:
            pass
        return None

    def _get_client(self) -> Any:
        if self.client:
            return self.client
        api_key = self._fetch_api_key()
        if not api_key:
            return None
        try:
            from groq import Groq
            self.client = Groq(api_key=api_key)
            return self.client
        except Exception as e:
            logger.warning(f"[LLM] Failed to initialize Groq client: {e}")
            return None

    def is_available(self) -> bool:
        return bool(self._get_client() or self._fetch_api_key())

    def generate(self, prompt: str) -> tuple[str, str]:
        client = self._get_client()
        if not client:
            raise RuntimeError("Groq API key missing or client uninitialized.")

        # Hard enforcement: production model MUST ONLY be llama-3.3-70b-versatile
        target_model = "llama-3.3-70b-versatile"
        try:
            resp = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=target_model,
                temperature=0.1
            )
            if resp and resp.choices and resp.choices[0].message.content:
                return resp.choices[0].message.content.strip(), target_model
        except Exception as e:
            logger.error(f"[LLM] Groq generation failed with model {target_model}: {e}")
            raise e

        raise RuntimeError(f"Failed to generate content with Groq model {target_model}.")
