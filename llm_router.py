"""
llm_router.py
─────────────
Centralized LLM Router managing Gemini primary and Groq fallback.
Enforces instant Groq fallback on 429 RESOURCE_EXHAUSTED without duplicate Gemini retries.
"""

from __future__ import annotations
import os
import logging
from typing import Optional
from llm_provider import GeminiProvider, GroqProvider, LLMResponse

logger = logging.getLogger("LLMRouter")


class LLMRouter:
    """
    Centralized Router enforcing:
    Primary: Gemini (gemini-3.6-flash)
    Fallback: Groq (llama-3.3-70b-versatile)
    """

    def __init__(self, gemini_provider: Optional[GeminiProvider] = None, groq_provider: Optional[GroqProvider] = None):
        self.gemini = gemini_provider or GeminiProvider()
        self.groq = groq_provider or GroqProvider()
        self.circuit_open_gemini: bool = False
        self.primary_provider: str = os.environ.get("LLM_PRIMARY_PROVIDER", "gemini").lower()
        self.fallback_provider: str = "groq"
        self.gemini_call_count: int = 0
        self.groq_call_count: int = 0

    def generate(self, prompt: str) -> LLMResponse:
        """
        Executes prompt generation with Gemini Primary and Groq Fallback.
        """
        disable_gemini = os.environ.get("DISABLE_GEMINI", "false").lower() in ("true", "1", "yes")
        
        # Groq-Primary mode (only if explicitly overridden via env)
        if self.primary_provider == "groq" or disable_gemini:
            logger.info("[LLM Router] Mode: GROQ PRIMARY (Gemini disabled)")
            return self._call_groq_primary(prompt)

        # Gemini Primary Mode (DEFAULT)
        # If Gemini circuit is open (previously hit 429), skip Gemini and go straight to Groq fallback
        if self.circuit_open_gemini:
            logger.info("[LLM] Primary: Gemini (Circuit OPEN due to 429)")
            logger.info("[LLM] Gemini retry: SKIPPED")
            logger.info("[LLM] Fallback: Groq")
            return self._call_groq_fallback(prompt, warning="Gemini quota reached — switched to Groq.")

        # Try Primary Gemini Provider
        if self.gemini.is_available():
            logger.info("[LLM] Primary: Gemini (gemini-3.6-flash)")
            self.gemini_call_count += 1
            try:
                text, model_used = self.gemini.generate(prompt)
                logger.info(f"[LLM] Gemini: SUCCESS (Model: {model_used})")
                return LLMResponse(
                    text=text,
                    provider_used="Gemini",
                    model_used=model_used,
                    fallback_occurred=False
                )
            except Exception as e:
                err_msg = str(e)
                err_lower = err_msg.lower()
                logger.warning(f"[LLM] Gemini failed ({err_msg}). Falling back to Groq...")

                if any(k in err_lower for k in ["429", "resource_exhausted", "quota", "rate_limit"]):
                    self.circuit_open_gemini = True
                    return self._call_groq_fallback(prompt, warning="Gemini quota reached — switched to Groq.", error_type="429 RESOURCE_EXHAUSTED")
                elif any(k in err_lower for k in ["401", "403", "invalid_api_key", "permission_denied"]):
                    return self._call_groq_fallback(prompt, warning="Gemini authentication invalid — switched to Groq.", error_type="AUTH_ERROR")
                elif any(k in err_lower for k in ["404", "not_found"]):
                    return self._call_groq_fallback(prompt, warning="Gemini model unavailable — switched to Groq.", error_type="MODEL_404")
                else:
                    return self._call_groq_fallback(prompt, warning="Gemini service unavailable — switched to Groq.", error_type="SERVER_ERROR")

        # Gemini unavailable (e.g. key missing)
        logger.info("[LLM] Gemini provider unavailable -> routing to Groq fallback")
        return self._call_groq_fallback(prompt, warning="Gemini disabled/unavailable — switched to Groq.")

    def _call_groq_primary(self, prompt: str) -> LLMResponse:
        self.groq_call_count += 1
        if not self.groq.is_available():
            raise RuntimeError("LLM conversion failed. Gemini primary and Groq fallback both failed. Manual review required.")
        try:
            text, model_used = self.groq.generate(prompt)
            return LLMResponse(
                text=text,
                provider_used="Groq",
                model_used=model_used,
                fallback_occurred=False
            )
        except Exception as ge:
            logger.error(f"[LLM Router] Groq failed: {ge}")
            raise RuntimeError("LLM conversion failed. Gemini primary and Groq fallback both failed. Manual review required.") from ge

    def _call_groq_fallback(self, prompt: str, warning: str, error_type: Optional[str] = None) -> LLMResponse:
        self.groq_call_count += 1
        if self.groq.is_available():
            try:
                text, model_used = self.groq.generate(prompt)
                logger.info(f"[LLM] Groq: SUCCESS (Model: {model_used})")
                return LLMResponse(
                    text=text,
                    provider_used="Groq",
                    model_used=model_used,
                    fallback_occurred=True,
                    warning_msg=warning,
                    error_type=error_type
                )
            except Exception as ge:
                logger.error(f"[LLM Router] Groq fallback failed: {ge}")
                raise RuntimeError("LLM conversion failed. Gemini primary and Groq fallback both failed. Manual review required.") from ge
        else:
            raise RuntimeError("LLM conversion failed. Gemini primary and Groq fallback both failed. Manual review required.")


# Global router singleton
_global_router: Optional[LLMRouter] = None


def get_llm_router() -> LLMRouter:
    """Returns global LLMRouter singleton."""
    global _global_router
    if _global_router is None:
        _global_router = LLMRouter()
    return _global_router
