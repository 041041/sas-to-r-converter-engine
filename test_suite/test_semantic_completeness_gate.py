import unittest
from semantic_validator import validate_semantic_completeness, extract_expected_sas_columns, SemanticValidator

class TestSemanticCompletenessGate(unittest.TestCase):

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

    def test_extract_expected_sas_columns(self):
        expected_cols = extract_expected_sas_columns(self.sas_trt_final)
        required = [
            "TRT01A", "PATIENTS", "ELDERLY_PATIENTS", "HIGH_RISK_PATIENTS",
            "PATIENTS_WITH_SERIOUS_AE", "PATIENTS_WITH_SEVERE_AE", "MEAN_AGE", "MEAN_BASELINE"
        ]
        for col in required:
            self.assertIn(col, expected_cols)

    def test_negative_incomplete_r_code(self):
        r_incomplete = """TRT_FINAL <- PATIENT_RISK %>%
  dplyr::left_join(AE_SUMMARY, by = "USUBJID") %>%
  dplyr::group_by(TRT01A) %>%
  dplyr::summarise(
      MEAN_AGE = mean(AGE, na.rm = TRUE),
      MEAN_BASELINE = mean(BASELINE, na.rm = TRUE)
  )
df"""
        is_comp, exp_cols, pres_cols, miss_cols = validate_semantic_completeness(self.sas_trt_final, r_incomplete)
        
        self.assertFalse(is_comp)
        self.assertIn("PATIENTS", miss_cols)
        self.assertIn("ELDERLY_PATIENTS", miss_cols)
        self.assertIn("HIGH_RISK_PATIENTS", miss_cols)
        self.assertIn("PATIENTS_WITH_SERIOUS_AE", miss_cols)
        self.assertIn("PATIENTS_WITH_SEVERE_AE", miss_cols)
        
        # Test full SemanticValidator
        validator = SemanticValidator()
        res = validator.validate(self.sas_trt_final, r_incomplete)
        self.assertFalse(res.is_equivalent)

    def test_positive_complete_r_code(self):
        r_complete = """TRT_FINAL <- PATIENT_RISK %>%
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
df"""
        is_comp, exp_cols, pres_cols, miss_cols = validate_semantic_completeness(self.sas_trt_final, r_complete)
        self.assertTrue(is_comp)
        self.assertEqual(len(miss_cols), 0)
        
        validator = SemanticValidator()
        res = validator.validate(self.sas_trt_final, r_complete)
        self.assertTrue(res.is_equivalent)

if __name__ == "__main__":
    unittest.main()
