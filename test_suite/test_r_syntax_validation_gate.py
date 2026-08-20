import unittest
import os
import sys

sys.path.insert(0, os.path.abspath("."))

from app import validate_r_syntax, call_llm_api
from llm_provider import LLMResponse

class MockRouterForSyntaxTest:
    def __init__(self, responses):
        self.responses = responses
        self.call_count = 0
        self.prompts_received = []

    def generate(self, prompt):
        self.prompts_received.append(prompt)
        resp_text = self.responses[self.call_count]
        self.call_count += 1
        return LLMResponse(text=resp_text, provider_used="Gemini", model_used="gemini-3.6-flash")


class TestRSyntaxValidationGate(unittest.TestCase):

    def test_a_clearly_malformed_r(self):
        """Test A: Unclosed dataframe expression fails syntax validation."""
        code_a = """df <- data.frame(
  A = c(1, 2),
  B = c(3, 4)"""
        self.assertFalse(validate_r_syntax(code_a))

    def test_b_missing_comma_between_mutate_expressions(self):
        """Test B: Missing comma between mutate assignments fails syntax validation."""
        code_b = """df <- ADSL %>%
  mutate(
    AGE_GROUP = case_when(
      AGE >= 65 ~ "ELDERLY",
      TRUE ~ "YOUNG"
    )
    RISK_LEVEL = case_when(
      TRUE ~ "LOW"
    )
  )
df"""
        self.assertFalse(validate_r_syntax(code_b))

    def test_c_valid_patient_risk(self):
        """Test C: Valid PATIENT_RISK passes syntax validation."""
        code_c = """PATIENT_RISK <- ADSL %>%
  filter(!is.na(AGE) & !is.na(BASELINE)) %>%
  mutate(
    AGE_GROUP = case_when(
      AGE >= 65 ~ "ELDERLY",
      AGE >= 50 ~ "MIDDLE",
      TRUE ~ "YOUNG"
    ),
    RISK_LEVEL = case_when(
      AGE >= 65 & TRT01A == "DrugB" ~ "HIGH",
      AGE >= 65 ~ "MODERATE",
      AGE >= 50 & TRT01A == "DrugB" ~ "MODERATE",
      TRUE ~ "LOW"
    ),
    BASELINE_GROUP = case_when(
      BASELINE >= 150 ~ "HIGH_BASELINE",
      BASELINE >= 125 ~ "MEDIUM_BASELINE",
      TRUE ~ "LOW_BASELINE"
    )
  ) %>%
  select(
    USUBJID, SEX, AGE, TRT01A, BASELINE,
    AGE_GROUP, RISK_LEVEL, BASELINE_GROUP
  ) %>%
  arrange(RISK_LEVEL, desc(AGE))
PATIENT_RISK"""
        self.assertTrue(validate_r_syntax(code_c))

    def test_d_llm_syntax_retry_path_success(self):
        """Test D: 1st response syntax failure -> 1 retry -> 2nd valid response accepted."""
        malformed_llm = """```r
PATIENT_RISK <- ADSL %>%
  filter(!is.na(AGE) & !is.na(BASELINE)) %>%
  mutate(
    AGE_GROUP = case_when(
      AGE >= 65 ~ "ELDERLY",
      TRUE ~ "YOUNG"
    )
    RISK_LEVEL = case_when(
      TRUE ~ "LOW"
    )
  )
PATIENT_RISK
```"""
        valid_llm = """```r
PATIENT_RISK <- ADSL %>%
  filter(!is.na(AGE) & !is.na(BASELINE)) %>%
  mutate(
    AGE_GROUP = case_when(
      AGE >= 65 ~ "ELDERLY",
      TRUE ~ "YOUNG"
    ),
    RISK_LEVEL = case_when(
      TRUE ~ "LOW"
    )
  ) %>%
  select(AGE, BASELINE, SEX, AGE_GROUP, RISK_LEVEL)
PATIENT_RISK
```"""
        router = MockRouterForSyntaxTest([malformed_llm, valid_llm])
        import app
        app.get_llm_router = lambda: router

        sas_step = "PROC SQL; CREATE TABLE PATIENT_RISK AS SELECT AGE, BASELINE, SEX FROM ADSL; QUIT;"
        res_r = call_llm_api(sas_step, [], ["ADSL"])

        # Exactly 1 retry (2 total generate calls)
        self.assertEqual(router.call_count, 2)
        self.assertIn("failed R syntax parsing", router.prompts_received[1])
        self.assertTrue(validate_r_syntax(res_r))

    def test_e_llm_syntax_retry_path_double_failure(self):
        """Test E: 1st response syntax failure -> 2nd response syntax failure -> REJECTED (NO 3rd retry)."""
        malformed_llm = """```r
PATIENT_RISK <- ADSL %>%
  mutate(
    AGE_GROUP = case_when(
      AGE >= 65 ~ "ELDERLY"
    )
    RISK_LEVEL = "LOW"
  )
df
```"""
        router = MockRouterForSyntaxTest([malformed_llm, malformed_llm])
        import app
        app.get_llm_router = lambda: router

        sas_step = "PROC SQL; CREATE TABLE PATIENT_RISK AS SELECT AGE FROM ADSL; QUIT;"
        with self.assertRaises(RuntimeError) as ctx:
            call_llm_api(sas_step, [], ["ADSL"])

        self.assertIn("R syntax validation", str(ctx.exception))
        self.assertEqual(router.call_count, 2)

if __name__ == "__main__":
    unittest.main()
