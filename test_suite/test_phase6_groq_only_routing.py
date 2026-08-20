"""
test_phase6_groq_only_routing.py
───────────────────────────────────
Phase 6 Validation Suite for Groq-Only LLM Routing & Zero Gemini Calls.
Verifies hard safety guards, Streamlit Cloud secret resolution, Groq failure handling,
and semantic correctness across Phase 5 and Phase 5.5 benchmarks.
"""

import os
import unittest
from unittest.mock import patch, MagicMock

# Force Groq-only environment variables
os.environ["LLM_PRIMARY_PROVIDER"] = "groq"
os.environ["DISABLE_GEMINI"] = "true"

from llm_provider import GeminiProvider, GroqProvider, GeminiDisabledError, LLMResponse
from llm_router import LLMRouter, get_llm_router
from macro_converter import LLMConverter, MacroIR
from semantic_conversion_engine import SemanticConversionEngine
from semantic_validator import SemanticValidator


class TestPhase6GroqOnlyRouting(unittest.TestCase):
    """Suite testing Groq-only routing and Gemini hard elimination."""

    def setUp(self):
        os.environ["LLM_PRIMARY_PROVIDER"] = "groq"
        os.environ["DISABLE_GEMINI"] = "true"
        self.router = LLMRouter()
        self.semantic_engine = SemanticConversionEngine(dialect="Modern R (tidyverse)")
        self.validator = SemanticValidator()

    def test_01_groq_key_loaded_from_st_secrets(self):
        """TEST 1: Verify Groq key is loaded from Streamlit secrets."""
        mock_secrets = {"GROQ_API_KEY": "gsk_mock_secret_key_12345"}
        with patch("streamlit.secrets", mock_secrets, create=True):
            groq_p = GroqProvider()
            key = groq_p._fetch_api_key()
            self.assertEqual(key, "gsk_mock_secret_key_12345")
            self.assertTrue(groq_p.is_available())

    def test_02_groq_is_primary_provider(self):
        """TEST 2: Verify Groq is designated as the primary LLM provider."""
        self.assertEqual(self.router.primary_provider, "groq")

    def test_02b_groq_model_is_llama_3_3_70b_versatile(self):
        """TEST 2B: Verify GroqProvider default model is llama-3.3-70b-versatile and deprecated model is NOT used."""
        groq_p = GroqProvider()
        self.assertEqual(groq_p.model, "llama-3.3-70b-versatile")
        
        # Verify fallback list in GroqProvider.generate contains NO decommissioned llama-3.1 model
        mock_client = MagicMock()
        groq_p_mock = GroqProvider(api_key="mock", client=mock_client)
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock(message=MagicMock(content="R code"))]
        mock_client.chat.completions.create.return_value = mock_resp
        
        groq_p_mock.generate("test prompt")
        called_models = [call.kwargs.get("model") for call in mock_client.chat.completions.create.call_args_list]
        for m in called_models:
            self.assertNotEqual(m, "llama-3.1-70b-versatile", "Decommissioned model llama-3.1-70b-versatile MUST NOT be used!")

    def test_03_gemini_is_disabled(self):
        """TEST 3: Verify GeminiProvider reports is_available() == False."""
        gemini_p = GeminiProvider()
        self.assertFalse(gemini_p.is_available())

    def test_04_gemini_local_hard_guard(self):
        """TEST 4: Attempting Gemini generation raises GeminiDisabledError locally without network call."""
        gemini_p = GeminiProvider()
        with patch("google.genai.Client", side_effect=AssertionError("SDK should not be invoked")):
            with self.assertRaises(GeminiDisabledError):
                gemini_p.generate("Test prompt")

    def test_05_groq_success_produces_r_code(self):
        """TEST 5: Verify Groq success returns valid LLMResponse."""
        mock_groq = MagicMock()
        mock_groq.is_available.return_value = True
        mock_groq.generate.return_value = ("df <- input_df %>% dplyr::filter(age > 18)\ndf", "llama-3.3-70b-versatile")

        router = LLMRouter(groq_provider=mock_groq)
        resp = router.generate("Convert SAS step")
        self.assertEqual(resp.provider_used, "Groq")
        self.assertEqual(resp.model_used, "llama-3.3-70b-versatile")
        self.assertIn("filter(age > 18)", resp.text)
        self.assertFalse(resp.fallback_occurred)

    def test_06_groq_failure_does_not_invoke_gemini(self):
        """TEST 6: Groq failure raises controlled error and DOES NOT call Gemini."""
        mock_groq = MagicMock()
        mock_groq.is_available.return_value = True
        mock_groq.generate.side_effect = Exception("Groq API rate limit or outage")

        mock_gemini = MagicMock()
        mock_gemini.generate.side_effect = AssertionError("CRITICAL SECURITY ERROR: Gemini provider was invoked on Groq failure!")

        router = LLMRouter(gemini_provider=mock_gemini, groq_provider=mock_groq)

        with self.assertRaises(RuntimeError) as ctx:
            router.generate("Convert SAS step")

        self.assertIn("GROQ conversion failed. Gemini fallback is disabled. Manual review required.", str(ctx.exception))
        mock_gemini.generate.assert_not_called()

    def test_07_macro_converter_uses_groq_only(self):
        """TEST 7: LLMConverter routes through router without calling Gemini."""
        ir = MacroIR(name="TEST_MACRO", params=["in_ds"], body_raw="data out; set in_ds; run;")
        with patch.object(LLMRouter, "generate") as mock_gen:
            mock_gen.return_value = LLMResponse(
                text="test_macro <- function(in_ds) { return(in_ds) }",
                provider_used="Groq",
                model_used="llama-3.3-70b-versatile"
            )
            converter = LLMConverter(groq_client=MagicMock(), gemini_client=None)
            res_code, conf = converter.convert(ir, "Modern R (dplyr)")
            self.assertIn("test_macro <- function", res_code)
            self.assertEqual(conf, 0.75)
            mock_gen.assert_called_once()

    def test_08_app_py_no_gemini_fallback(self):
        """TEST 8: Verify call_llm_api uses router and does not invoke Gemini."""
        from app import call_llm_api
        with patch.object(LLMRouter, "generate") as mock_gen:
            mock_gen.return_value = LLMResponse(
                text="df <- ORDERS %>% dplyr::filter(amount > 500)\ndf",
                provider_used="Groq",
                model_used="llama-3.3-70b-versatile"
            )
            code = call_llm_api("TASK: Convert SAS step", [], [])
            self.assertIn("dplyr::filter(amount > 500)", code)

    def test_09_r_autofix_no_gemini_fallback(self):
        """TEST 9: R auto-fix repair uses router and does not invoke Gemini."""
        from app import fix_r_code_on_mismatch
        with patch.object(LLMRouter, "generate") as mock_gen:
            mock_gen.return_value = LLMResponse(
                text="df <- ORDERS %>% dplyr::filter(total_spent > 500)\ndf",
                provider_used="Groq",
                model_used="llama-3.3-70b-versatile"
            )
            repaired = fix_r_code_on_mismatch("df <- ORDERS", "data step;", [], None, None, "Modern R")
            self.assertIn("total_spent > 500", repaired)

    def test_10_complex_clinical_macro_groq_conversion(self):
        """TEST 10: Complex clinical macro converts through Groq engine."""
        sas_code = """
        %macro build_ae(input=AE, output=ADAE_SUM);
            proc sql;
                create table ADAM.&output as
                select usubjid, count(*) as total_ae
                from SDTM.&input
                group by usubjid;
            quit;
        %mend build_ae;
        %build_ae(input=AE, output=ADAE_SUM);
        """
        res = self.semantic_engine.convert_program(sas_code, program_name="Clinical_Groq_Test")
        self.assertIsNotNone(res)
        self.assertIn("ADAE_SUM", res.optimized_r_code)

    def test_11_orders_proc_sql_semantic_equivalence(self):
        """TEST 11: Phase 5 Orders example produces correct tidyverse aggregation & filter."""
        sas_code = """
        proc sql;
            create table ORDERS as
            select cust_id,
                   count(*) as total_orders,
                   sum(amount) as total_spent,
                   avg(amount) as avg_spent,
                   max(amount) as max_order,
                   min(amount) as min_order
            from input_df
            group by cust_id
            having sum(amount) > 500
            order by total_spent desc;
        quit;
        """
        res = self.semantic_engine.convert_program(sas_code, program_name="Orders_Test")
        val_res = self.validator.validate(sas_code, res.optimized_r_code)
        self.assertTrue(val_res.is_equivalent)
        self.assertIn("dplyr::filter(total_spent > 500)", res.optimized_r_code)
        self.assertIn("dplyr::arrange(desc(total_spent))", res.optimized_r_code)

    def test_12_user_clinical_macro_full_completeness(self):
        """TEST 12: User complex clinical macro passes strict 100% semantic validation."""
        sas_code = """
        options mprint mlogic symbolgen;
        libname SDTM "/clinical/data/sdtm";
        libname ADAM "/clinical/data/adam";
        filename setup "/clinical/config/setup.sas";
        %include setup;

        %let study_id = STUDY001;
        %let min_age = 18;
        %let population = SAFFL;
        %let ds1 = DM;
        %let ds2 = AE;
        %let ds3 = EX;

        %macro build_population(input=DM, output=ADSL, age=18, flag=SAFFL);
            data ADAM.&output;
                set SDTM.&input;
                if age >= &age;
                if &flag = "Y";
                if sex = "M" then SEXN = 1;
                else if sex = "F" then SEXN = 2;
                else SEXN = .;

                length STUDY $20;
                STUDY = "&study_id";
            run;

            proc sort data=ADAM.&output out=ADAM.&output._SORTED;
                by usubjid descending age;
            run;
        %mend build_population;

        %macro summarize_ae(input=AE, output=ADAE_SUM);
            proc sql;
                create table ADAM.&output as
                select usubjid,
                       count(*) as total_ae,
                       sum(case when serious = "Y" then 1 else 0 end) as serious_ae,
                       max(severity) as max_severity
                from SDTM.&input
                group by usubjid
                having count(*) > 0
                order by total_ae desc;
            quit;
        %mend summarize_ae;

        %macro build_analysis(study=&study_id, input_lib=SDTM, output_lib=ADAM, min_age=&min_age, population_flag=&population);
            %local i current_ds dataset_count today study_suffix;
            %let today = %sysfunc(today(), yymmddn8.);
            %let study_suffix = %substr(&study, %length(&study)-2, 3);
            %let dataset_count = 3;

            %do i = 1 %to &dataset_count;
                %let current_ds = &&ds&i;
                %if %upcase(&current_ds) = DM %then %do;
                    %build_population(input=&current_ds, output=ADSL, age=&min_age, flag=&population_flag);
                %end;
                %else %if %upcase(&current_ds) = AE %then %do;
                    %summarize_ae(input=&current_ds, output=ADAE_SUM);
                %end;
                %else %if %upcase(&current_ds) = EX %then %do;
                    proc sql;
                        create table ADAM.EX_SUM as
                        select usubjid, count(*) as exposure_records, sum(dose) as total_dose, mean(dose) as avg_dose, max(dose) as max_dose, min(dose) as min_dose
                        from SDTM.&current_ds
                        group by usubjid
                        having sum(dose) > 0
                        order by total_dose desc;
                    quit;
                %end;
            %end;

            proc sql;
                create table ADAM.ADSL_FINAL as
                select a.*, b.total_ae, b.serious_ae, b.max_severity
                from ADAM.ADSL_SORTED as a
                left join ADAM.ADAE_SUM as b
                on a.usubjid = b.usubjid
                order by a.usubjid;
            quit;

            data ADAM.ADSL_FINAL;
                set ADAM.ADSL_FINAL;
                length STUDYID $20 ANALYSIS_DATE $8 RISK_CATEGORY $20;
                STUDYID = "&study";
                ANALYSIS_DATE = "&today";

                if total_ae >= 5 then RISK_CATEGORY = "HIGH";
                else if total_ae >= 2 then RISK_CATEGORY = "MEDIUM";
                else RISK_CATEGORY = "LOW";

                if age >= &min_age and &population_flag = "Y" then ANALYSIS_FLAG = "Y";
                else ANALYSIS_FLAG = "N";
            run;

            proc sort data=ADAM.ADSL_FINAL out=ADAM.ADSL_FINAL;
                by descending total_ae usubjid;
            run;

        %mend build_analysis;

        %build_analysis(study=STUDY001, input_lib=SDTM, output_lib=ADAM, min_age=18, population_flag=SAFFL);
        """
        res = self.semantic_engine.convert_program(sas_code, program_name="Phase5_5_Full")
        val_res = self.validator.validate(sas_code, res.optimized_r_code)
        self.assertTrue(val_res.is_equivalent)
        self.assertEqual(val_res.confidence_score, 100.0)

    def test_13_zero_gemini_calls_monkeypatch_guard(self):
        """TEST 13: Monkeypatch Gemini API calls to mathematically guarantee zero Gemini calls."""
        gemini_call_counter = {"count": 0}

        def fake_gemini_generate(*args, **kwargs):
            gemini_call_counter["count"] += 1
            raise AssertionError("Gemini SDK call attempted during test suite execution!")

        with patch.object(GeminiProvider, "generate", side_effect=fake_gemini_generate):
            # Run conversion through engine
            sas_code = "data test; set raw; run;"
            res = self.semantic_engine.convert_program(sas_code)
            self.assertIsNotNone(res)
            self.assertEqual(gemini_call_counter["count"], 0)


if __name__ == "__main__":
    unittest.main()
