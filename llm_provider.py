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
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.client = client
        self.preferred_models = [
            "gemini-2.5-flash",
            "gemini-1.5-flash",
            "gemini-2.0-flash-exp",
            "gemini-3.6-flash",
            "gemini-pro"
        ]

    def _get_client(self) -> Any:
        if os.environ.get("DISABLE_GEMINI", "true").lower() in ("true", "1", "yes"):
            return None
        if os.environ.get("LLM_PRIMARY_PROVIDER", "groq").lower() == "groq":
            return None
        if self.client:
            return self.client
        if not self.api_key:
            return None
        try:
            from google import genai
            self.client = genai.Client(api_key=self.api_key)
            return self.client
        except Exception as e:
            logger.warning(f"[LLM] Failed to initialize Gemini client: {e}")
            return None

    def is_available(self) -> bool:
        if os.environ.get("DISABLE_GEMINI", "true").lower() in ("true", "1", "yes"):
            return False
        if os.environ.get("LLM_PRIMARY_PROVIDER", "groq").lower() == "groq":
            return False
        return bool(self._get_client() or self.api_key)

    def generate(self, prompt: str) -> tuple[str, str]:
        if os.environ.get("DISABLE_GEMINI", "true").lower() in ("true", "1", "yes") or os.environ.get("LLM_PRIMARY_PROVIDER", "groq").lower() == "groq":
            raise GeminiDisabledError("Gemini API calls hard disabled in development mode.")

        client = self._get_client()
        if not client:
            raise RuntimeError("Gemini API key missing or client uninitialized.")

        last_err = None
        for model in self.preferred_models:
            try:
                res = client.models.generate_content(model=model, contents=prompt)
                if res and hasattr(res, "text") and res.text:
                    return res.text.strip(), model
                elif res and hasattr(res, "content") and res.content:
                    return str(res.content).strip(), model
            except Exception as e:
                last_err = e
                err_msg = str(e).lower()
                # If 429 quota or auth error, raise immediately to router for Groq fallback
                if any(k in err_msg for k in ["429", "resource_exhausted", "quota", "rate_limit"]):
                    raise e
                if any(k in err_msg for k in ["401", "403", "invalid_api_key", "permission_denied"]):
                    raise e
                if any(k in err_msg for k in ["404", "not_found", "no longer available"]):
                    logger.info(f"[LLM] Gemini Model {model} returned 404, cascading to next Gemini model...")
                    continue
                raise e

        if last_err:
            raise last_err
        raise RuntimeError("Gemini content generation failed across all models.")


class GroqProvider(BaseLLMProvider):
    """Secondary Fallback LLM Provider wrapping Groq API."""
    name: str = "Groq"

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, client: Optional[Any] = None):
        self.api_key = api_key
        self.model = model or os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
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

        models_to_try = [self.model, "llama-3.3-70b-versatile", "llama-3.1-70b-versatile", "llama3-70b-8192"]
        seen = set()
        models_to_try = [m for m in models_to_try if m and not (m in seen or seen.add(m))]

        last_err = None
        for m in models_to_try:
            try:
                resp = client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model=m,
                    temperature=0.1
                )
                if resp and resp.choices and resp.choices[0].message.content:
                    return resp.choices[0].message.content.strip(), m
            except Exception as e:
                last_err = e
                err_msg = str(e).lower()
                if "404" in err_msg or "model_not_found" in err_msg:
                    logger.info(f"[LLM] Groq model {m} not found, cascading to next Groq model...")
                    continue
                raise e

        if last_err:
            raise last_err
        raise RuntimeError("Groq content generation failed across all models.")
