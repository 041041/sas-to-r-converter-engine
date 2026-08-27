"""
Phase 8.46 Live Path-B Macro Invocation Integration Regression Test
"""

import re
import pytest
from macro_converter import parse_sas_source, convert_macros_to_r, classify_macro
from macro_processor import expand_sas_macros, SASMacroProcessor
from sas_step_converter import SASStepConverter
from rule_engine import RuleEngine
from sas_parser import ProgramStep


def test_phase8_46_live_path_b_macro_invocation_end_to_end():
    sas_script = """
%macro filter_dataset(data=, var=, out=);
    data &out;
        set &data;
        if not missing(&var);
    run;
%mend;

%filter_dataset(data=DM, var=USUBJID, out=DM_CLEAN);
%filter_dataset(data=AE, var=AEDECOD, out=AE_CLEAN);
"""

    raw_sas_input = sas_script

    # 1. Authoritative macro extraction & classification
    parsed_source = parse_sas_source(raw_sas_input)
    _macro_defs = parsed_source["macro_definitions"]
    assert "FILTER_DATASET" in _macro_defs
    assert classify_macro("FILTER_DATASET", _macro_defs["FILTER_DATASET"], all_macro_defs=_macro_defs) == "PATH_B"

    # 2. Convert macro definition to R utility function
    macro_result = convert_macros_to_r(
        macro_definitions=_macro_defs,
        macro_calls=parsed_source.get("macro_calls", []),
        dialect="Modern R (dplyr)"
    )
    r_functions = macro_result.get("r_functions", "")
    assert "filter_dataset <- function(data, var, out)" in r_functions or "filter_dataset <- function" in r_functions
    assert ".data[[var]]" in r_functions

    # 3. Macro expansion with expand_path_b=False preserves invocation statements
    has_path_b = True
    unexp_sas, mac_warnings, _ = expand_sas_macros(raw_sas_input, [], expand_path_b=not has_path_b)

    step_pattern = re.compile(
        r"((?:data|proc)\s+.*?;.*?(?:run|quit);|%(?!(?:macro|mend|let|put|include|if|then|else|do|end)\b)[a-zA-Z_]\w*\s*(?:\([^)]*\))?\s*;)",
        re.DOTALL | re.IGNORECASE
    )
    steps = step_pattern.findall(unexp_sas)
    assert len(steps) == 2, f"Expected 2 macro call steps, found: {len(steps)}"

    # 4. RuleEngine translates MACRO_CALL steps to reusable R function calls
    r_engine = RuleEngine(dialect="Modern R (dplyr)")
    translated_steps = []

    for i, step_code in enumerate(steps, 1):
        m_match = re.search(r"%(\w+)", step_code, re.I)
        sname = f"%{m_match.group(1).upper()}" if m_match else f"MACRO_CALL_{i}"

        prog_step = ProgramStep(
            step_index=i,
            step_type="MACRO_CALL",
            name=sname,
            source_code=step_code,
            input_datasets=[],
            output_datasets=[sname]
        )
        r_rule_code, conf, method = r_engine.translate_step(prog_step)
        assert conf >= 0.85
        assert method == "Rule_MacroCall"
        translated_steps.append(r_rule_code)

    # 5. Requirement 10 & 11 direct assertions
    assert "DM_CLEAN <- filter_dataset(DM, \"USUBJID\")" in translated_steps
    assert "AE_CLEAN <- filter_dataset(AE, \"AEDECOD\")" in translated_steps

    # Direct assertion: MUST NOT reduce calls to inline identity assignments
    assert "DM_CLEAN <- DM" not in translated_steps
    assert "AE_CLEAN <- AE" not in translated_steps

    # 6. Combined program output verification
    full_r_program = (
        "library(tidyverse)\n\n" +
        "# ── Reusable Modernized R Functions ──\n" + r_functions + "\n\n" +
        "\n".join(translated_steps)
    )

    assert "DM_CLEAN <- filter_dataset(DM, \"USUBJID\")" in full_r_program
    assert "AE_CLEAN <- filter_dataset(AE, \"AEDECOD\")" in full_r_program
    assert "filter_dataset <- function" in full_r_program
    assert ".data[[var]]" in full_r_program
