"""
run_macro_stress_tests.py
─────────────────────────
Automated, deterministic, offline SAS macro stress test runner and failure minimizer.
Evaluates generated stress tests, classifies failure modes, generates failure artifacts,
and produces test_suite/MACRO_STRESS_TEST_REPORT.md.
"""

from __future__ import annotations
import sys
import os
import re
import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

# Ensure current working directory is in sys.path
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from sas_step_converter import SASStepConverter
from macro_processor import SASMacroProcessor
from macro_converter import parse_sas_source, classify_macro, convert_macros_to_r
from sas_parser import parse_sas_program

CASES_DIR = BASE_DIR / "test_suite" / "generated_macro_cases"
ARTIFACTS_DIR = BASE_DIR / "test_suite" / "failure_artifacts"
REPORT_PATH = BASE_DIR / "test_suite" / "MACRO_STRESS_TEST_REPORT.md"

# Clear old artifacts directory
if ARTIFACTS_DIR.exists():
    shutil.rmtree(ARTIFACTS_DIR)
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


def minimize_sas_code(sas_code: str, test_id: str, check_fail_fn) -> str:
    """
    Attempts statement-level reduction on failing SAS code while preserving the failure mode.
    Returns minimized SAS code.
    """
    lines = [l for l in sas_code.split("\n") if l.strip()]
    if len(lines) <= 5:
        return sas_code.strip()

    minimized = list(lines)
    for i in range(len(lines) - 1, -1, -1):
        candidate = lines[:i] + lines[i+1:]
        cand_code = "\n".join(candidate)
        if not cand_code.strip():
            continue
        try:
            is_still_failing, _ = check_fail_fn(cand_code)
            if is_still_failing:
                minimized = candidate
        except Exception:
            pass

    return "\n".join(minimized).strip()


def check_test_case(case_data: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[str], Dict[str, Any]]:
    """
    Executes a single test case through the conversion pipeline and checks all invariants.
    Returns (is_passed, failure_category, failure_details, actual_metadata).
    """
    test_id = case_data["test_id"]
    sas_code = case_data["sas_code"]
    expected = case_data["expected"]

    actual_metadata = {
        "macro_count": 0,
        "macro_names": [],
        "classifications": {},
        "output_datasets": [],
        "source_datasets": [],
        "path_b_utilities": [],
        "generated_r": "",
        "warnings": []
    }

    # 1. Parse SAS & Extract Macro Definitions
    try:
        parsed = parse_sas_source(sas_code)
        macro_defs = parsed.get("macro_definitions", {})
        macro_calls = parsed.get("macro_calls", [])
        actual_metadata["macro_count"] = len(macro_defs)
        actual_metadata["macro_names"] = list(macro_defs.keys())
    except Exception as e:
        return False, "PARSING_FAILURE", f"parse_sas_source failed: {str(e)}", actual_metadata

    # 2. Convert Macros & Classify
    try:
        conv_all_res = convert_macros_to_r(macro_defs, macro_calls, dialect="Modern R (dplyr)")
        classifications = conv_all_res.get("classifications", {})
        r_functions_str = conv_all_res.get("r_functions", "")
        actual_metadata["classifications"] = classifications
    except Exception as e:
        return False, "CLASSIFICATION_FAILURE", f"convert_macros_to_r failed: {str(e)}", actual_metadata

    # Check Classification Expectations
    exp_class = expected.get("classifications", {})
    for mname, exp_cls in exp_class.items():
        if classifications.get(mname) != exp_cls:
            return False, "CLASSIFICATION_FAILURE", f"Macro {mname} classified as {classifications.get(mname)}, expected {exp_cls}", actual_metadata

    # 3. Process Macros
    try:
        proc = SASMacroProcessor()
        proc.let_vars.update(parsed.get("global_vars", {}))
        has_path_b = any(c == "PATH_B" for c in classifications.values())
        unexp_sas, proc_warns, _ = proc.process(sas_code, expand_path_b=not has_path_b)
        actual_metadata["warnings"].extend(proc_warns)
    except Exception as e:
        return False, "MACRO_EXPANSION_FAILURE", f"SASMacroProcessor failed: {str(e)}", actual_metadata

    # Check Macro Expansion Warnings for unresolved errors
    for w in proc_warns:
        if "called but not defined" in w:
            return False, "MACRO_REGISTRATION_FAILURE", f"Processor warning: {w}", actual_metadata
        if "Unresolved macro variable" in w and not has_path_b:
            return False, "PARAMETER_SUBSTITUTION_FAILURE", f"Processor warning: {w}", actual_metadata

    # 4. Convert Program to R
    try:
        converter = SASStepConverter(dialect="Modern R (dplyr)")
        res = converter.convert_program(unexp_sas, raw_sas_code=sas_code)

        r_parts = []
        if r_functions_str:
            r_parts.append(r_functions_str)
        if res.full_optimized_r:
            r_parts.append(res.full_optimized_r)
        generated_r = "\n\n".join(r_parts)

        actual_metadata["generated_r"] = generated_r
        actual_metadata["output_datasets"] = [getattr(s, "output_dataset", "") for s in res.converted_steps if getattr(s, "output_dataset", "")]
        actual_metadata["source_datasets"] = list({l.dataset_name for l in res.ast.lineage if hasattr(l, "dataset_name")}) if res.ast.lineage else []
        
        # Extract PATH_B function names from r_functions_str
        created_funcs = re.findall(r'(\w+)\s*<-\s*function', r_functions_str, re.I)
        actual_metadata["path_b_utilities"] = created_funcs
    except Exception as e:
        return False, "R_GENERATION_FAILURE", f"SASStepConverter failed: {str(e)}", actual_metadata

    # 5. Check for Unresolved Residual Macro Artifacts
    unresolved_macro_vars = re.findall(r'&\b[a-zA-Z_]\w*', generated_r)
    unresolved_indirect = re.findall(r'&&\b[a-zA-Z_]\w*', generated_r)
    if unresolved_macro_vars or unresolved_indirect:
        return False, "PARAMETER_SUBSTITUTION_FAILURE", f"Unresolved macro variables in R output: {unresolved_macro_vars + unresolved_indirect}", actual_metadata

    if "TODO" in generated_r or "Manual review required" in generated_r:
        return False, "VALIDATION_FAILURE", f"R output contains TODO or Manual review markers: {generated_r[:150]}...", actual_metadata

    if "set_unresolved" in generated_r:
        return False, "MACRO_EXPANSION_FAILURE", f"R output contains set_unresolved: {generated_r[:150]}...", actual_metadata

    # 6. Invariant Checks for PATH_A
    for mname, cls in classifications.items():
        if cls == "PATH_A":
            pattern = rf'{mname.lower()}\s*<-\s*function'
            if re.search(pattern, r_functions_str, re.I):
                return False, "PATH_A_ROUTING_FAILURE", f"PATH_A macro {mname} was generated as a reusable R utility function", actual_metadata

    # 7. Invariant Checks for PATH_B
    for mname, cls in classifications.items():
        if cls == "PATH_B":
            pattern = rf'{mname.lower()}\s*<-\s*function'
            if not re.search(pattern, r_functions_str, re.I):
                return False, "PATH_B_ROUTING_FAILURE", f"PATH_B macro {mname} function definition not found in generated R functions", actual_metadata

    # 8. Check Invalid R Syntax patterns
    if re.search(r'filter\s*\(\s*not\s+missing\s*\(', generated_r, re.I):
        return False, "R_SYNTAX_FAILURE", "Generated R contains invalid 'filter(not missing(...))' syntax", actual_metadata
    if re.search(r'filter\s*\(\s*missing\s*\(', generated_r, re.I):
        return False, "R_SYNTAX_FAILURE", "Generated R contains invalid 'filter(missing(...))' syntax", actual_metadata
    if re.search(r'%\w+\s*\(', generated_r):
        return False, "R_SYNTAX_FAILURE", "Generated R contains residual '%func(...)' macro call syntax", actual_metadata

    # 9. Executable R Syntax Validation via Rscript if available
    if shutil.which("Rscript"):
        r_file_temp = ARTIFACTS_DIR / f"_temp_{test_id}.R"
        try:
            with open(r_file_temp, "w", encoding="utf-8") as f:
                f.write(generated_r)
            proc_r = subprocess.run(["Rscript", "-e", f"parse('{r_file_temp}')"], capture_output=True, text=True)
            if proc_r.returncode != 0:
                return False, "R_SYNTAX_FAILURE", f"Rscript syntax parse check failed: {proc_r.stderr.strip()}", actual_metadata
        except Exception:
            pass
        finally:
            if r_file_temp.exists():
                r_file_temp.unlink()

    return True, None, None, actual_metadata


def run_all_stress_tests(regression_mode: bool = False) -> Dict[str, Any]:
    """
    Runs all stress tests and outputs failure artifacts and markdown report.
    """
    case_files = sorted(list(CASES_DIR.glob("*.json")))
    if not case_files:
        print("❌ No test cases found in test_suite/generated_macro_cases! Run generate_macro_stress_tests.py first.")
        sys.exit(1)

    print(f"🚀 Running SAS Macro Stress Test Suite ({len(case_files)} cases)...")
    
    total = 0
    passed = 0
    failed = 0
    complexity_stats = {
        "BASIC": {"total": 0, "pass": 0, "fail": 0},
        "MODERATE": {"total": 0, "pass": 0, "fail": 0},
        "COMPLEX": {"total": 0, "pass": 0, "fail": 0},
        "VERY_COMPLEX": {"total": 0, "pass": 0, "fail": 0},
        "TORTURE": {"total": 0, "pass": 0, "fail": 0},
    }
    path_stats = {
        "PATH_A": {"total": 0, "pass": 0, "fail": 0},
        "PATH_B": {"total": 0, "pass": 0, "fail": 0},
    }
    failure_categories: Dict[str, int] = {}
    failure_list: List[Dict[str, Any]] = []

    for file_path in case_files:
        if file_path.name.startswith("_"):
            continue
        with open(file_path, "r", encoding="utf-8") as f:
            case_data = json.load(f)

        test_id = case_data["test_id"]
        comp = case_data["complexity"]
        total += 1
        complexity_stats[comp]["total"] += 1

        is_pass, category, details, actual_meta = check_test_case(case_data)

        # Track PATH_A / PATH_B stats
        classes = case_data["expected"].get("classifications", {})
        for _, c_type in classes.items():
            if c_type in path_stats:
                path_stats[c_type]["total"] += 1
                if is_pass:
                    path_stats[c_type]["pass"] += 1
                else:
                    path_stats[c_type]["fail"] += 1

        if is_pass:
            passed += 1
            complexity_stats[comp]["pass"] += 1
        else:
            failed += 1
            complexity_stats[comp]["fail"] += 1
            failure_categories[category] = failure_categories.get(category, 0) + 1

            # Build minimized repro snippet
            def check_cand(cand_code):
                cand_case = dict(case_data)
                cand_case["sas_code"] = cand_code
                p, cat, _, _ = check_test_case(cand_case)
                return (not p), cat

            min_sas = minimize_sas_code(case_data["sas_code"], test_id, check_cand)

            # Save Failure Artifacts
            art_dir = ARTIFACTS_DIR / test_id
            art_dir.mkdir(parents=True, exist_ok=True)
            with open(art_dir / "input.sas", "w", encoding="utf-8") as f:
                f.write(case_data["sas_code"])
            with open(art_dir / "expected.json", "w", encoding="utf-8") as f:
                json.dump(case_data["expected"], f, indent=2)
            with open(art_dir / "actual.json", "w", encoding="utf-8") as f:
                json.dump(actual_meta, f, indent=2)
            with open(art_dir / "generated.R", "w", encoding="utf-8") as f:
                f.write(actual_meta.get("generated_r", ""))
            with open(art_dir / "failure.txt", "w", encoding="utf-8") as f:
                f.write(f"TEST ID: {test_id}\nCATEGORY: {category}\nCOMPLEXITY: {comp}\nDETAILS: {details}\n")
            with open(art_dir / "minimal_repro.sas", "w", encoding="utf-8") as f:
                f.write(min_sas)

            failure_list.append({
                "test_id": test_id,
                "complexity": comp,
                "category": category,
                "details": details,
                "description": case_data["description"],
                "repro_cmd": f"python3 -c 'from test_suite.run_macro_stress_tests import check_test_case; import json; print(check_test_case(json.load(open(\"test_suite/generated_macro_cases/{test_id}.json\"))))'"
            })

    pass_rate = (passed / total * 100) if total > 0 else 0.0

    # ── GENERATE MARKDOWN REPORT ──────────────────────────────────
    report_lines = [
        "# SAS → R Macro Architecture Stress Test Report",
        "",
        f"**Date/Time**: Deterministic Automated Stress Run  ",
        f"**Total Stress Tests**: {total}  ",
        f"**Passed**: {passed}  ",
        f"**Failed**: {failed}  ",
        f"**Pass Rate**: **{pass_rate:.1f}%**  ",
        "",
        "## 1. Complexity Breakdown",
        "",
        "| Complexity | Total | Passed | Failed | Pass Rate |",
        "| :--- | :---: | :---: | :---: | :---: |",
    ]

    for comp, st in complexity_stats.items():
        pr = (st["pass"] / st["total"] * 100) if st["total"] > 0 else 0.0
        report_lines.append(f"| **{comp}** | {st['total']} | {st['pass']} | {st['fail']} | {pr:.1f}% |")

    report_lines.extend([
        "",
        "## 2. Macro Path Classification Results",
        "",
        "| Path Architecture | Total | Passed | Failed | Pass Rate |",
        "| :--- | :---: | :---: | :---: | :---: |",
        f"| **PATH_A (Compile-time Template)** | {path_stats['PATH_A']['total']} | {path_stats['PATH_A']['pass']} | {path_stats['PATH_A']['fail']} | {(path_stats['PATH_A']['pass']/max(1,path_stats['PATH_A']['total'])*100):.1f}% |",
        f"| **PATH_B (Reusable R Utility)** | {path_stats['PATH_B']['total']} | {path_stats['PATH_B']['pass']} | {path_stats['PATH_B']['fail']} | {(path_stats['PATH_B']['pass']/max(1,path_stats['PATH_B']['total'])*100):.1f}% |",
        "",
        "## 3. Failure Categories Summary",
        "",
    ])

    if failure_categories:
        report_lines.append("| Failure Category | Count |")
        report_lines.append("| :--- | :---: |")
        for cat, cnt in sorted(failure_categories.items(), key=lambda x: x[1], reverse=True):
            report_lines.append(f"| `{cat}` | {cnt} |")
    else:
        report_lines.append("🎉 **Zero failures detected across all stress tests!**")

    report_lines.extend([
        "",
        "## 4. Top Failures & Minimized Reproductions",
        ""
    ])

    if failure_list:
        for idx, fl in enumerate(failure_list[:10], 1):
            report_lines.extend([
                f"### {idx}. {fl['test_id']} ({fl['complexity']})",
                f"- **Category**: `{fl['category']}`",
                f"- **Description**: {fl['description']}",
                f"- **Details**: `{fl['details']}`",
                f"- **Reproduction Command**:",
                "  ```bash",
                f"  {fl['repro_cmd']}",
                "  ```",
                f"- **Artifacts Path**: [file://{ARTIFACTS_DIR}/{fl['test_id']}](file://{ARTIFACTS_DIR}/{fl['test_id']})",
                ""
            ])
    else:
        report_lines.append("No failure reproductions required.")

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    print(f"\n✅ Stress Test Report saved to: {REPORT_PATH}")

    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": pass_rate,
        "complexity_stats": complexity_stats,
        "path_stats": path_stats,
        "failure_categories": failure_categories,
        "top_failures": failure_list[:10]
    }


if __name__ == "__main__":
    regression = "--regression" in sys.argv
    results = run_all_stress_tests(regression_mode=regression)
    print("\n" + "=" * 50)
    print(f"TOTAL:      {results['total']}")
    print(f"PASSED:     {results['passed']}")
    print(f"FAILED:     {results['failed']}")
    print(f"PASS RATE:  {results['pass_rate']:.1f}%")
    print("=" * 50)
