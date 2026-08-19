"""
test_offline_baseline_verification.py
──────────────────────────────────────
Offline Mock Verification for Known-Good Baseline Commit ffc5268.
Verifies the application backend pipeline, macro resolution, dynamic references,
dataset lineage, semantic IR, optimizer, and documentation generator with ZERO live Gemini API calls.
"""

import unittest
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sas_parser import parse_sas_program
from macro_semantics_engine import SASMacroSemanticsEngine
from dependency_graph import build_dependency_graph
from sas_semantic_ir import build_semantic_ir
from semantic_conversion_engine import SemanticConversionEngine
from sas_step_converter import SASStepConverter
from doc_generator import DocumentationGenerator
from doc_renderers import md_renderer

SIMPLE_SAS = """
data adsl;
    set sdtm.dm;
    if age >= 18;
run;
"""

COMPLEX_SAS_MACRO = """
libname SDTM "/clinical/data/sdtm";
libname ADAM "/clinical/data/adam";
filename setup "/clinical/config/setup.sas";
%include setup;

%let study = CLINICAL_ABC;
%let today = %sysfunc(today(), yymmddn8.);
%let ds1 = DM;
%let ds2 = AE;
%let ds3 = EX;

%macro build_clinical_pipeline(sdtm_lib=SDTM, adam_lib=ADAM, min_age=18);
    %local i current_ds;
    
    /* 1. ADSL Base Step */
    data &adam_lib..adsl;
        set &sdtm_lib..&ds1;
        if age >= &min_age;
    run;

    /* 2. EX_SUM Exposure Aggregation Step */
    proc sql;
        create table &adam_lib..ex_sum as
        select usubjid,
               count(*) as exposure_records,
               sum(dose) as total_dose,
               mean(dose) as avg_dose
        from &sdtm_lib..&ds3
        group by usubjid;
    quit;

    /* 3. ADAE_SUM Adverse Event Aggregation Step */
    proc sql;
        create table &adam_lib..adae_sum as
        select usubjid,
               count(*) as ae_count
        from &sdtm_lib..&ds2
        group by usubjid;
    quit;

    /* 4. ADSL_FINAL Multi-Join Step */
    proc sql;
        create table &adam_lib..adsl_final as
        select a.*, b.ae_count, c.total_dose
        from &adam_lib..adsl a
        left join &adam_lib..adae_sum b on a.usubjid = b.usubjid
        left join &adam_lib..ex_sum c on a.usubjid = c.usubjid;
    quit;

    /* 5. ADSL_SORTED Sort Step */
    proc sort data=&adam_lib..adsl_final out=&adam_lib..adsl_sorted;
        by usubjid;
    run;
%mend build_clinical_pipeline;

/* Invoke Clinical Macro */
%build_clinical_pipeline(sdtm_lib=SDTM, adam_lib=ADAM, min_age=18);
"""


class TestOfflineBaselineVerification(unittest.TestCase):

    def test_01_simple_sas_offline_conversion(self):
        """Verify simple SAS conversion pipeline without calling Gemini."""
        engine = SemanticConversionEngine(dialect="Modern R (tidyverse)")
        res = engine.convert_program(SIMPLE_SAS, program_name="Simple_Offline_Test")
        self.assertIsNotNone(res)
        self.assertIn("ADSL <- DM", res.optimized_r_code)
        self.assertEqual(res.confidence_report.r_syntax_status, "PASS")

    def test_02_complex_macro_resolution_and_ast_offline(self):
        """Verify complex SAS macro resolution, AST, dynamic macro vars offline."""
        macro_eng = SASMacroSemanticsEngine()
        exp_sas, ast, evidence, report = macro_eng.process_program(COMPLEX_SAS_MACRO)

        self.assertIsNotNone(exp_sas)
        self.assertIn("data ADAM.adsl;", exp_sas)
        self.assertIn("set SDTM.DM;", exp_sas)
        self.assertIn("from SDTM.EX", exp_sas)
        self.assertIn("from SDTM.AE", exp_sas)
        self.assertEqual(len(ast.steps), 5)

    def test_03_dependency_graph_and_lineage_offline(self):
        """Verify dependency graph & lineage nodes offline."""
        macro_eng = SASMacroSemanticsEngine()
        exp_sas, ast, evidence, report = macro_eng.process_program(COMPLEX_SAS_MACRO)
        graph = build_dependency_graph(ast)
        self.assertIsNotNone(graph)
        all_nodes = [n.upper() for n in graph.dataset_nodes.keys()]
        self.assertTrue(len(all_nodes) >= 4)

    def test_04_semantic_ir_offline(self):
        """Verify Semantic IR operation mapping offline."""
        macro_eng = SASMacroSemanticsEngine()
        exp_sas, ast, evidence, report = macro_eng.process_program(COMPLEX_SAS_MACRO)
        sem_ir = build_semantic_ir(ast, exp_sas)
        self.assertIsNotNone(sem_ir)
        self.assertEqual(len(sem_ir.pipeline_operations), 5)

    def test_05_doc_generator_10_sections_offline(self):
        """Verify 10-section documentation generator constructs report offline without calling LLM."""
        converter = SASStepConverter(dialect="Modern R (tidyverse)")
        conv_res = converter.convert_program(SIMPLE_SAS)
        doc_gen = DocumentationGenerator()
        mod_doc = doc_gen.generate_document(conv_res, program_name="Offline_Doc_Test")
        md_text = md_renderer.render_markdown(mod_doc)

        self.assertIsNotNone(md_text)
        self.assertIn("1. Executive Summary", md_text)
        self.assertIn("10. Conversion Confidence", md_text)

    def test_06_mock_llm_full_converter_pipeline(self):
        """Verify step converter pipeline using a mocked LLM response."""
        with patch.dict(os.environ, {"GEMINI_API_KEY": "mock_key_for_offline_test"}), \
             patch("semantic_conversion_engine.SemanticConversionEngine.convert_program") as mock_conv:
            mock_conv.return_value = MagicMock(converted_steps=[MagicMock()], optimized_r_code="ADSL <- DM")
            converter = SASStepConverter(dialect="Modern R (tidyverse)")
            res = converter.convert_program(SIMPLE_SAS)
            self.assertIsNotNone(res)


if __name__ == "__main__":
    unittest.main()
