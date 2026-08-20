import unittest
import os
import sys

sys.path.insert(0, os.path.abspath("."))

from app import call_llm_api
from llm_provider import LLMResponse
from semantic_validator import validate_semantic_completeness

class MockRouterWithRetry:
    def __init__(self, responses):
        self.responses = responses
        self.call_count = 0
        self.prompts_received = []

    def generate(self, prompt):
        self.prompts_received.append(prompt)
        resp_text = self.responses[self.call_count]
        self.call_count += 1
        return LLMResponse(text=resp_text, provider_used="Gemini", model_used="gemini-3.6-flash")


class TestSemanticCompletenessRetryPath(unittest.TestCase):

    def setUp(self):
        self.sas_trt_final = """proc sql;
    create table TRT_FINAL as
    select
        a.TRT01A,

        count(distinct a.USUBJID) as PATIENTS,

        sum(
            case
                when a.AGE >= 65 then 1
                else 0
            end
        ) as ELDERLY_PATIENTS,

        sum(
            case
                when a.RISK_LEVEL = "HIGH" then 1
                else 0
            end
        ) as HIGH_RISK_PATIENTS,

        sum(
            case
                when b.SERIOUS_AE > 0 then 1
                else 0
            end
        ) as PATIENTS_WITH_SERIOUS_AE,

        sum(
            case
                when b.SEVERE_AE > 0 then 1
                else 0
            end
        ) as PATIENTS_WITH_SEVERE_AE,

        avg(a.AGE) as MEAN_AGE,

        avg(a.BASELINE) as MEAN_BASELINE

    from PATIENT_RISK as a

    left join AE_SUMMARY as b
        on a.USUBJID = b.USUBJID

    where a.TRT01A is not null

    group by
        a.TRT01A

    having calculated PATIENTS > 1

    order by
        calculated HIGH_RISK_PATIENTS desc,
        calculated PATIENTS_WITH_SERIOUS_AE desc;

quit;"""

        self.r_incomplete = """```r
df <- PATIENT_RISK %>%
  dplyr::left_join(AE_SUMMARY, by = "USUBJID") %>%
  dplyr::group_by(TRT01A) %>%
  dplyr::summarise(
      MEAN_AGE = mean(AGE, na.rm = TRUE),
      MEAN_BASELINE = mean(BASELINE, na.rm = TRUE)
  )
df
```"""

        self.r_complete = """```r
df <- PATIENT_RISK %>%
  dplyr::left_join(AE_SUMMARY, by = "USUBJID") %>%
  dplyr::group_by(TRT01A) %>%
  dplyr::summarise(
      PATIENTS = n_distinct(USUBJID),
      ELDERLY_PATIENTS = sum(if_else(AGE >= 65, 1, 0), na.rm = TRUE),
      HIGH_RISK_PATIENTS = sum(if_else(RISK_LEVEL == "HIGH", 1, 0), na.rm = TRUE),
      PATIENTS_WITH_SERIOUS_AE = sum(if_else(SERIOUS_AE > 0, 1, 0), na.rm = TRUE),
      PATIENTS_WITH_SEVERE_AE = sum(if_else(SEVERE_AE > 0, 1, 0), na.rm = TRUE),
      MEAN_AGE = mean(AGE, na.rm = TRUE),
      MEAN_BASELINE = mean(BASELINE, na.rm = TRUE),
      .groups = "drop"
  ) %>%
  dplyr::filter(PATIENTS > 1) %>%
  dplyr::arrange(desc(HIGH_RISK_PATIENTS), desc(PATIENTS_WITH_SERIOUS_AE))
df
```"""

    def test_positive_retry_path(self):
        """Scenario 1: Incomplete 1st response -> Complete 2nd response -> Conversion ACCEPTED."""
        router = MockRouterWithRetry([self.r_incomplete, self.r_complete])
        import app
        app.get_llm_router = lambda: router

        result_r = call_llm_api(self.sas_trt_final, [], ["PATIENT_RISK", "AE_SUMMARY"])

        # 1. Verify router was called exactly twice (1 initial call + 1 retry)
        self.assertEqual(router.call_count, 2)
        
        # 2. Verify retry prompt contains all 5 missing variables
        retry_prompt = router.prompts_received[1]
        self.assertIn("CRITICAL CORRECTION REQUIRED", retry_prompt)
        missing_vars = ["PATIENTS", "ELDERLY_PATIENTS", "HIGH_RISK_PATIENTS", "PATIENTS_WITH_SERIOUS_AE", "PATIENTS_WITH_SEVERE_AE"]
        for var in missing_vars:
            self.assertIn(var, retry_prompt)

        # 3. Verify final R code contains all 8 expected variables
        is_comp, _, pres_c, miss_c = validate_semantic_completeness(self.sas_trt_final, result_r)
        self.assertTrue(is_comp)
        self.assertEqual(len(miss_c), 0)

    def test_second_negative_path(self):
        """Scenario 2: Incomplete 1st response -> Still incomplete 2nd response -> REJECTED, NO 3rd retry."""
        router = MockRouterWithRetry([self.r_incomplete, self.r_incomplete])
        import app
        app.get_llm_router = lambda: router

        with self.assertRaises(RuntimeError) as ctx:
            call_llm_api(self.sas_trt_final, [], ["PATIENT_RISK", "AE_SUMMARY"])

        self.assertIn("semantic completeness validation", str(ctx.exception))
        # Verify exactly 2 LLM attempts were made (1 initial + 1 retry), NO 3rd retry
        self.assertEqual(router.call_count, 2)

if __name__ == "__main__":
    unittest.main()
