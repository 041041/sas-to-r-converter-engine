"""
llm_router.py
─────────────
Centralized LLM Router managing Gemini primary and Groq fallback.
Enforces instant Groq fallback on 429 RESOURCE_EXHAUSTED without duplicate Gemini retries.
"""

from __future__ import annotations
import logging
from typing import Optional
from llm_provider import GeminiProvider, GroqProvider, LLMResponse

logger = logging.getLogger("LLMRouter")


class LLMRouter:
    """
    Centralized Router enforcing:
    Primary: Gemini (gemini-2.5-flash)
    Fallback: Groq (llama-3.3-70b-versatile)
    """

    def __init__(self, gemini_provider: Optional[GeminiProvider] = None, groq_provider: Optional[GroqProvider] = None):
        self.gemini = gemini_provider or GeminiProvider()
        self.groq = groq_provider or GroqProvider()
        self.circuit_open_gemini: bool = False

    def generate(self, prompt: str) -> LLMResponse:
        """
        Executes prompt generation with primary Gemini and automatic fallback to Groq.
        """
        # If Gemini circuit is open (previously hit 429), skip Gemini and go straight to Groq
        if self.circuit_open_gemini:
            logger.info("[LLM] Primary: Gemini (Circuit OPEN due to 429)")
            logger.info("[LLM] Gemini retry: SKIPPED")
            logger.info("[LLM] Fallback: Groq")
            return self._call_groq_fallback(prompt, warning="Gemini quota reached — switched to Groq.")

        # Try Primary Gemini Provider
        if self.gemini.is_available():
            logger.info("[LLM] Primary: Gemini")
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

                # 1. Check for 429 RESOURCE_EXHAUSTED / Quota Limit
                if any(k in err_lower for k in ["429", "resource_exhausted", "quota", "rate_limit"]):
                    logger.warning("[LLM] Gemini: 429 RESOURCE_EXHAUSTED")
                    logger.warning("[LLM] Gemini retry: SKIPPED")
                    logger.warning("[LLM] Fallback: Groq")
                    self.circuit_open_gemini = True
                    return self._call_groq_fallback(
                        prompt,
                        warning="Gemini quota reached — switched to Groq.",
                        error_type="429 RESOURCE_EXHAUSTED"
                    )

                # 2. Check for 401 / 403 Auth errors
                elif any(k in err_lower for k in ["401", "403", "invalid_api_key", "permission_denied"]):
                    logger.warning(f"[LLM] Gemini: AUTH_ERROR ({err_msg})")
                    logger.warning("[LLM] Gemini retry: SKIPPED")
                    logger.warning("[LLM] Fallback: Groq")
                    return self._call_groq_fallback(
                        prompt,
                        warning="Gemini authentication invalid — switched to Groq.",
                        error_type="AUTH_ERROR"
                    )

                # 3. Check for 404 Model Not Found
                elif any(k in err_lower for k in ["404", "not_found"]):
                    logger.warning(f"[LLM] Gemini: MODEL_404 ({err_msg})")
                    logger.warning("[LLM] Gemini retry: SKIPPED")
                    logger.warning("[LLM] Fallback: Groq")
                    return self._call_groq_fallback(
                        prompt,
                        warning="Gemini model unavailable — switched to Groq.",
                        error_type="MODEL_404"
                    )

                # 4. Server error / Timeout / Network error
                else:
                    logger.warning(f"[LLM] Gemini: SERVER_ERROR ({err_msg})")
                    logger.warning("[LLM] Gemini retry: SKIPPED")
                    logger.warning("[LLM] Fallback: Groq")
                    return self._call_groq_fallback(
                        prompt,
                        warning="Gemini service unavailable — switched to Groq.",
                        error_type="SERVER_ERROR"
                    )

        # Gemini unavailable
        logger.info("[LLM] Gemini provider unavailable -> routing to Groq")
        logger.info("[LLM] Fallback: Groq")
        return self._call_groq_fallback(prompt, warning="Gemini uninitialized — switched to Groq.")

    def _call_groq_fallback(self, prompt: str, warning: str, error_type: Optional[str] = None) -> LLMResponse:
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
                logger.error(f"[LLM] Groq: FAILED ({ge})")
                raise RuntimeError(f"Both Gemini and Groq providers failed. Groq error: {ge}") from ge
        else:
            raise RuntimeError(f"Both Gemini and Groq providers are unavailable. {warning}")


# Global router singleton
_global_router: Optional[LLMRouter] = None


def get_llm_router() -> LLMRouter:
    """Returns global LLMRouter singleton."""
    global _global_router
    if _global_router is None:
        _global_router = LLMRouter()
    return _global_router
