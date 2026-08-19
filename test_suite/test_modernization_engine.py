"""
test_suite/test_modernization_engine.py
────────────────────────────────────────
Automated Regression Test Suite for Enterprise SAS Modernization Engine.
"""

from __future__ import annotations
import unittest

import sas_ast
import sas_parser
import dependency_graph
import rule_engine
import r_optimizer
import infra_analyzer
import sas_step_converter
import doc_generator
from doc_renderers import md_renderer


class TestSASModernizationEngine(unittest.TestCase):

    def setUp(self):
        self.sample_sas = """
        libname source '/clinical/data';
        filename raw '/raw/data.csv';

        %macro process_clinical_data(study=ABC101, min_age=18);
            %let run_date = 2026-08-19;

            %if &min_age >= 18 %then %do;
                data work.adsl_filtered;
                    set source.adsl;
                    if age >= &min_age;
                run;
            %end;

            proc sort data=work.adsl_filtered out=adsl_sorted;
                by arm descending age;
            run;

            proc freq data=adsl_sorted;
                tables arm*sex;
            run;
        %mend process_clinical_data;
        """

    def test_parser_and_ast(self):
        ast = sas_parser.parse_sas_program(self.sample_sas)
        self.assertIn("SOURCE", ast.infrastructure.libnames)
        self.assertIn("RAW", ast.infrastructure.filenames)
        self.assertIn("PROCESS_CLINICAL_DATA", ast.macros)
        macro = ast.macros["PROCESS_CLINICAL_DATA"]
        self.assertEqual(len(macro.parameters), 2)
        self.assertGreater(ast.complexity.score, 0)

    def test_dependency_graph(self):
        ast = sas_parser.parse_sas_program(self.sample_sas)
        graph = dependency_graph.build_dependency_graph(ast)
        self.assertIn("ADSL_FILTERED", graph.dataset_nodes)
        self.assertIn("ADSL_SORTED", graph.dataset_nodes)

    def test_rule_engine(self):
        engine = rule_engine.RuleEngine(dialect="Modern R (tidyverse)")
        step = sas_ast.ProgramStep(1, "PROC_STEP", "PROC SORT", "proc sort data=adsl out=adsl_sort; by arm descending age; run;")
        r_code, conf, method = engine.translate_step(step)
        self.assertIsNotNone(r_code)
        self.assertIn("arrange(arm, desc(age))", r_code)

    def test_r_optimizer(self):
        opt = r_optimizer.ROptimizer(dialect="Modern R (tidyverse)")
        verbose_r = """
        library(dplyr)
        library(dplyr)
        df1 <- input_data
        df2 <- df1 %>% filter(AGE >= 18)
        df2
        """
        clean_r, metrics = opt.optimize(verbose_r)
        self.assertIn("library(dplyr)", clean_r)
        self.assertEqual(clean_r.count("library(dplyr)"), 1)
        self.assertGreaterEqual(metrics.line_reduction_pct, 0.0)

    def test_infra_analyzer(self):
        ast = sas_parser.parse_sas_program(self.sample_sas)
        analyzer = infra_analyzer.InfrastructureAnalyzer()
        config = analyzer.analyze(ast.infrastructure)
        self.assertIn('lib_source <- "/clinical/data"', config.r_config_code)

    def test_full_converter_and_doc_generator(self):
        converter = sas_step_converter.SASStepConverter(dialect="Modern R (tidyverse)")
        result = converter.convert_program(self.sample_sas)
        self.assertIsNotNone(result.full_optimized_r)

        doc_gen = doc_generator.DocumentationGenerator()
        doc = doc_gen.generate_document(result, program_name="Test_Study_Modernization")
        markdown = md_renderer.render_markdown(doc)

        self.assertIn("# 🚀 SAS Modernization Report: Test_Study_Modernization", markdown)
        self.assertIn("## 1. Executive Summary", markdown)
        self.assertIn("## 6. R Code Optimization Metrics", markdown)


if __name__ == "__main__":
    unittest.main()
